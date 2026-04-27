from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import re
from typing import Any

import util.auth
from web_server._logic import server_path, web_server_handler


FRIENDS_LIMIT = 200


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _get_user(self: web_server_handler, user_id: int):
    return self.server.storage.user.check_object(user_id)


def _send_invalid_target_user(self: web_server_handler) -> bool:
    self.send_json(
        {"errors": [{"code": 1, "message": "The target user is invalid or does not exist"}]},
        400,
    )
    return True


def _send_invalid_request(self: web_server_handler) -> bool:
    self.send_json(
        {"success": False, "message": "Invalid request"},
        400,
    )
    return True


def _format_friend_payload(self: web_server_handler, user) -> dict[str, object]:
    is_online = _parse_timestamp(user.lastonline) > (datetime.now(UTC) - timedelta(minutes=1))
    return {
        "isOnline": is_online,
        "isDeleted": False,
        "friendFrequentScore": 0,
        "friendFrequentRank": 1,
        "hasVerifiedBadge": user.is_verified,
        "description": user.description,
        "created": user.created,
        "isBanned": user.accountstatus != 1,
        "externalAppDisplayName": None,
        "id": user.id,
        "name": user.username,
        "displayName": user.username,
    }


def _resolve_universe_id_for_place(
    self: web_server_handler,
    place_id: int,
) -> int:
    universe_id = self.server.storage.universe.get_id_from_root_place_id(place_id)
    if universe_id is not None:
        return int(universe_id)

    place_obj = self.server.storage.place.check_object(place_id)
    if place_obj is not None and place_obj.parent_universe_id is not None:
        return int(place_obj.parent_universe_id)
    return 0


def _list_online_friend_payloads(
    self: web_server_handler,
    user_id: int,
    *,
    limit: int,
) -> list[dict[str, object]]:
    storage = self.server.storage
    friend_ids = storage.friend.list_friend_ids(user_id, limit=limit)
    latest_rows = storage.ingame_player.get_latest_for_user_ids(friend_ids)
    if not latest_rows:
        return []

    place_by_server_uuid = storage.gameserver.get_place_ids_for_servers(
        list({row.server_uuid for row in latest_rows.values()}),
    )
    data: list[dict[str, object]] = []
    for friend_id in friend_ids:
        latest_row = latest_rows.get(friend_id)
        if latest_row is None:
            continue

        place_id = place_by_server_uuid.get(latest_row.server_uuid)
        if place_id is None:
            continue

        friend_user = _get_user(self, friend_id)
        if friend_user is None:
            continue

        place_obj = storage.place.check_object(place_id)
        place_name = (
            place_obj.assetObj.name
            if place_obj is not None and place_obj.assetObj is not None else
            ""
        )
        data.append({
            "id": friend_user.id,
            "userId": friend_user.id,
            "name": friend_user.username,
            "displayName": friend_user.username,
            "placeId": place_id,
            "rootPlaceId": place_id,
            "gameId": latest_row.server_uuid,
            "universeId": _resolve_universe_id_for_place(self, place_id),
            "presenceType": 2,
            "isOnline": True,
            "lastLocation": place_name,
            "lastOnline": friend_user.lastonline,
            "hasVerifiedBadge": friend_user.is_verified,
        })
    return data


def _read_target_user_ids(self: web_server_handler) -> list[Any] | None:
    try:
        raw = self.read_content()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        self.send_json(
            {"errors": [{"code": 0, "message": "An invalid userId was passed in."}]},
            400,
        )
        return None

    if not isinstance(payload, dict):
        self.send_json(
            {"errors": [{"code": 0, "message": "An invalid userId was passed in."}]},
            400,
        )
        return None

    target_user_ids = payload.get("targetUserIds")
    if not isinstance(target_user_ids, list) or len(target_user_ids) > 100:
        self.send_json(
            {"errors": [{"code": 0, "message": "An invalid userId was passed in."}]},
            400,
        )
        return None
    return target_user_ids


@server_path("/v1/my/friends/count", commands={"GET"})
@util.auth.authenticated_required_api
def my_friends_count(self: web_server_handler) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.send_json({"count": self.server.storage.friend.count_friends(current_user.id)})
    return True


@server_path(r"/v1/users/(\d+)/friends/count", regex=True, commands={"GET"})
def user_friends_count(self: web_server_handler, match: re.Match[str]) -> bool:
    user = _get_user(self, int(match.group(1)))
    if user is None:
        self.send_json({"errors": [{"code": 1, "message": "User not found"}]}, 404)
        return True

    self.send_json({"count": self.server.storage.friend.count_friends(user.id)})
    return True


@server_path("/v1/user/friend-requests/count", commands={"GET"})
@util.auth.authenticated_required_api
def my_friend_requests_count(self: web_server_handler) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.send_json({
        "count": self.server.storage.friend.count_pending_requests(current_user.id),
    })
    return True


@server_path(r"/v1/users/(\d+)/friends", regex=True, commands={"GET", "POST"})
def user_friends(self: web_server_handler, match: re.Match[str]) -> bool:
    user = _get_user(self, int(match.group(1)))
    if user is None:
        return _send_invalid_request(self)

    friend_list = []
    for friend_id in self.server.storage.friend.list_friend_ids(user.id):
        friend_user = _get_user(self, friend_id)
        if friend_user is None:
            continue
        friend_list.append(_format_friend_payload(self, friend_user))

    self.send_json({"data": friend_list})
    return True


@server_path("/v1/user/friend-requests/decline-all", commands={"POST"})
@util.auth.authenticated_required_api
def decline_all_friend_requests(self: web_server_handler) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.server.storage.friend.decline_all_requests(current_user.id)
    self.send_json({})
    return True


@server_path(r"/v1/users/(\d+)/unfriend", regex=True, commands={"POST"})
@util.auth.authenticated_required_api
def unfriend_user(self: web_server_handler, match: re.Match[str]) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    target_user = _get_user(self, int(match.group(1)))
    if target_user is None:
        return _send_invalid_target_user(self)

    self.server.storage.friend.remove_friendship(current_user.id, target_user.id)
    self.send_json({})
    return True


@server_path(r"/v1/users/(\d+)/request-friendship", regex=True, commands={"POST"})
@util.auth.authenticated_required_api
def request_friendship(self: web_server_handler, match: re.Match[str]) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    target_user = _get_user(self, int(match.group(1)))
    if target_user is None:
        return _send_invalid_target_user(self)
    if target_user.id == current_user.id:
        self.send_json(
            {"errors": [{"code": 7, "message": "The user cannot be friends with itself."}]},
            400,
        )
        return True
    if self.server.storage.friend.count_friends(current_user.id) >= FRIENDS_LIMIT:
        self.send_json(
            {"errors": [{"code": 31, "message": "User with max friends sent friend request."}]},
            400,
        )
        return True
    if self.server.storage.friend.has_friendship(current_user.id, target_user.id):
        self.send_json(
            {"errors": [{"code": 5, "message": "The target user is already a friend."}]},
            400,
        )
        return True

    if self.server.storage.friend.has_pending_request(target_user.id, current_user.id):
        if self.server.storage.friend.count_friends(target_user.id) >= FRIENDS_LIMIT:
            self.send_json(
                {"errors": [{"code": 12, "message": "The target users friends limit has been exceeded."}]},
                400,
            )
            return True

        self.server.storage.friend.accept_request(target_user.id, current_user.id)
        self.send_json({"success": True})
        return True

    if not self.server.storage.friend.has_pending_request(current_user.id, target_user.id):
        self.server.storage.friend.create_request(current_user.id, target_user.id)

    self.send_json({"success": True})
    return True


@server_path(r"/v1/users/(\d+)/accept-friend-request", regex=True, commands={"POST"})
@util.auth.authenticated_required_api
def accept_friend_request(self: web_server_handler, match: re.Match[str]) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    target_user = _get_user(self, int(match.group(1)))
    if target_user is None:
        return _send_invalid_target_user(self)
    if not self.server.storage.friend.has_pending_request(target_user.id, current_user.id):
        self.send_json(
            {"errors": [{"code": 10, "message": "The friend request does not exist."}]},
            400,
        )
        return True
    if self.server.storage.friend.count_friends(current_user.id) >= FRIENDS_LIMIT:
        self.send_json(
            {"errors": [{"code": 11, "message": "The current users friends limit has been exceeded."}]},
            400,
        )
        return True
    if self.server.storage.friend.count_friends(target_user.id) >= FRIENDS_LIMIT:
        self.send_json(
            {"errors": [{"code": 12, "message": "The target users friends limit has been exceeded."}]},
            400,
        )
        return True

    self.server.storage.friend.accept_request(target_user.id, current_user.id)
    self.send_json({})
    return True


@server_path(r"/v1/users/(\d+)/decline-friend-request", regex=True, commands={"POST"})
@util.auth.authenticated_required_api
def decline_friend_request(self: web_server_handler, match: re.Match[str]) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    target_user = _get_user(self, int(match.group(1)))
    if target_user is None:
        return _send_invalid_target_user(self)
    if not self.server.storage.friend.has_pending_request(target_user.id, current_user.id):
        self.send_json(
            {"errors": [{"code": 10, "message": "The friend request does not exist."}]},
            400,
        )
        return True

    self.server.storage.friend.decline_request(target_user.id, current_user.id)
    self.send_json({})
    return True


@server_path(r"/v1/users/(\d+)/followers/count", regex=True, commands={"GET"})
def user_followers_count(self: web_server_handler, match: re.Match[str]) -> bool:
    user = _get_user(self, int(match.group(1)))
    if user is None:
        return _send_invalid_request(self)

    self.send_json({"count": self.server.storage.follow_relationship.count_followers(user.id)})
    return True


@server_path(r"/v1/users/(\d+)/followings/count", regex=True, commands={"GET"})
def user_followings_count(self: web_server_handler, match: re.Match[str]) -> bool:
    user = _get_user(self, int(match.group(1)))
    if user is None:
        return _send_invalid_request(self)

    self.send_json({"count": self.server.storage.follow_relationship.count_following(user.id)})
    return True


@server_path("/v1/user/following-exists", commands={"POST"})
@util.auth.authenticated_required_api
def following_exists(self: web_server_handler) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    target_user_ids = _read_target_user_ids(self)
    if target_user_ids is None:
        return True

    response_list = []
    for value in target_user_ids:
        try:
            target_user_id = int(value)
        except (TypeError, ValueError):
            self.send_json(
                {"errors": [{"code": 0, "message": "An invalid userId was passed in."}]},
                400,
            )
            return True
        if target_user_id < 1:
            self.send_json(
                {"errors": [{"code": 0, "message": "An invalid userId was passed in."}]},
                400,
            )
            return True

        target_user = _get_user(self, target_user_id)
        if target_user is None:
            self.send_json(
                {"errors": [{"code": 0, "message": "An invalid userId was passed in."}]},
                400,
            )
            return True

        response_list.append({
            "isFollowing": self.server.storage.follow_relationship.is_following(
                current_user.id,
                target_user_id,
            ),
            "isFollowed": self.server.storage.follow_relationship.is_following(
                target_user_id,
                current_user.id,
            ),
            "userId": target_user_id,
        })

    self.send_json({"followings": response_list})
    return True


@server_path(r"/v1/users/(\d+)/unfollow", regex=True, commands={"POST"})
@util.auth.authenticated_required_api
def unfollow_user(self: web_server_handler, match: re.Match[str]) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    target_user = _get_user(self, int(match.group(1)))
    if target_user is None:
        return _send_invalid_target_user(self)

    self.server.storage.follow_relationship.delete(current_user.id, target_user.id)
    self.send_json({})
    return True


@server_path(r"/v1/users/(\d+)/follow", regex=True, commands={"POST"})
@util.auth.authenticated_required_api
def follow_user(self: web_server_handler, match: re.Match[str]) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    target_user = _get_user(self, int(match.group(1)))
    if target_user is None:
        return _send_invalid_target_user(self)
    if target_user.id == current_user.id:
        self.send_json(
            {"errors": [{"code": 8, "message": "The user cannot follow itself."}]},
            400,
        )
        return True

    self.server.storage.follow_relationship.update(current_user.id, target_user.id)
    self.send_json({"success": True})
    return True


@server_path(r"/v1/users/(\d+)/friends/online", regex=True, commands={"GET"})
def user_friends_online(self: web_server_handler, match: re.Match[str]) -> bool:
    user = _get_user(self, int(match.group(1)))
    if user is None:
        self.send_json({"data": []})
        return True

    try:
        limit = int(self.query.get("limit") or 20)
    except ValueError:
        limit = 20
    limit = max(0, min(limit, 100))
    self.send_json({
        "data": _list_online_friend_payloads(
            self,
            user.id,
            limit=limit,
        ),
    })
    return True


@server_path(r"/v1/users/(\d+)/friends/find", regex=True, commands={"GET"})
def user_friends_find(self: web_server_handler, match: re.Match[str]) -> bool:
    user = _get_user(self, int(match.group(1)))
    if user is None:
        return _send_invalid_request(self)

    try:
        limit = int(self.query.get("limit") or 20)
    except ValueError:
        limit = 20
    limit = max(0, min(limit, 100))

    page_items = []
    for friend_id in self.server.storage.friend.list_friend_ids(user.id, limit=limit):
        friend_user = _get_user(self, friend_id)
        if friend_user is None:
            continue
        page_items.append(_format_friend_payload(self, friend_user))

    self.send_json({
        "data": page_items,
        "PageItems": page_items,
        "TotalCount": len(page_items),
        "PageType": "Friends",
        "NextCursor": None,
        "PreviousCursor": None,
    })
    return True
