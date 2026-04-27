from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any

import util.auth
from web_server._logic import server_path, web_server_handler


def _send_invalid_request(self: web_server_handler) -> None:
    self.send_json(
        {"errors": [{"code": 0, "message": "Invalid Request"}]},
        400,
    )


def _send_invalid_user_id(self: web_server_handler) -> None:
    self.send_json(
        {"errors": [{"code": 1, "message": "Invalid UserId"}]},
        400,
    )


def _read_user_ids(self: web_server_handler) -> list[Any] | None:
    try:
        raw = self.read_content()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        _send_invalid_request(self)
        return None

    if not isinstance(payload, dict):
        _send_invalid_request(self)
        return None

    user_ids = payload.get("userIds")
    if not isinstance(user_ids, list):
        _send_invalid_request(self)
        return None
    if len(user_ids) > 100:
        _send_invalid_request(self)
        return None
    return user_ids


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S.000Z")


@server_path("/v1/presence/users", commands={"POST"})
@util.auth.authenticated_required_api
def multi_get_users_presence(self: web_server_handler) -> bool:
    requested_user_ids = _read_user_ids(self)
    if requested_user_ids is None:
        return True

    storage = self.server.storage
    parsed_user_ids: list[int] = []
    users_by_id = {}
    for value in requested_user_ids:
        try:
            user_id = int(value)
        except (TypeError, ValueError):
            _send_invalid_user_id(self)
            return True

        if user_id <= 0:
            _send_invalid_user_id(self)
            return True

        user = storage.user.check_object(user_id)
        if user is None:
            _send_invalid_user_id(self)
            return True

        parsed_user_ids.append(user_id)
        users_by_id[user_id] = user

    sessions_by_user = storage.ingame_player.get_latest_for_user_ids(parsed_user_ids)
    place_ids_by_server = storage.gameserver.get_place_ids_for_servers(
        sorted({
            row.server_uuid
            for row in sessions_by_user.values()
        }),
    )

    online_cutoff = datetime.now(UTC) - timedelta(minutes=1)
    place_cache = {}
    user_presences = []
    for user_id in parsed_user_ids:
        user = users_by_id[user_id]
        last_online_at = _parse_timestamp(user.lastonline)
        is_online = last_online_at > online_cutoff

        session = sessions_by_user.get(user_id)
        server_uuid = session.server_uuid if session is not None else None
        place_id = (
            place_ids_by_server.get(server_uuid)
            if server_uuid is not None else
            None
        )

        place = None
        if place_id is not None:
            if place_id not in place_cache:
                place_cache[place_id] = storage.place.check_object(place_id)
            place = place_cache[place_id]

        place_asset = (
            place.assetObj
            if place is not None and place.assetObj is not None else
            None
        )
        is_in_game = place_asset is not None

        user_presences.append({
            "userPresenceType": (2 if is_in_game else 1 if is_online else 0),
            "lastLocation": (
                place_asset.name
                if is_in_game else
                "Website"
            ),
            "placeId": (
                place_asset.id
                if is_in_game else
                None
            ),
            "rootPlaceId": (
                place_asset.id
                if is_in_game else
                None
            ),
            "gameId": (
                server_uuid
                if is_in_game else
                None
            ),
            "userId": user_id,
            "lastOnline": _format_timestamp(last_online_at),
        })

    self.send_json({"userPresences": user_presences})
    return True
