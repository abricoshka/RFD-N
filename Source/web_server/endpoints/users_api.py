import json
import re

import util.auth
from web_server._logic import web_server_handler, server_path


def send_user_details_v1(
    self: web_server_handler,
    user_id: int,
) -> bool:
    user = self.server.storage.user.check_object(user_id)
    if user is None:
        self.send_json({
            "errors": [
                {
                    "code": 3,
                    "message": "The user id is invalid.",
                }
            ]
        }, 404)
        return True

    self.send_json({
        "description": user.description,
        "created": user.created,
        "isBanned": user.accountstatus != 1,
        "externalAppDisplayName": user.username,
        "hasVerifiedBadge": user.is_verified,
        "id": user.id,
        "name": user.username,
        "displayName": user.username,
    })
    return True


def _read_username_lookup_payload(
    self: web_server_handler,
) -> dict[str, object] | None:
    content_type = self.headers.get("Content-Type", "").lower()
    if "application/json" not in content_type:
        self.send_json(
            {"errors": [{"code": 0, "message": "UnsupportedMediaType"}]},
            415,
        )
        return None

    try:
        raw = self.read_content()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}
    return payload


def send_username_users_v1(self: web_server_handler) -> bool:
    payload = _read_username_lookup_payload(self)
    if payload is None:
        return True

    usernames = payload.get("usernames")
    if not isinstance(usernames, list):
        self.send_json({"data": []})
        return True

    if any(not isinstance(username, str) for username in usernames):
        self.send_json({"data": []})
        return True

    exclude_banned_users = payload.get("excludeBannedUsers") is True
    seen_usernames: set[str] = set()
    data: list[dict[str, int | str | bool]] = []
    for requested_username in usernames:
        normalized_username = requested_username.casefold()
        if normalized_username in seen_usernames:
            continue
        seen_usernames.add(normalized_username)

        user = self.server.storage.user.check_object_from_username_casefold(
            requested_username,
        )
        if user is None:
            continue
        if exclude_banned_users and user.accountstatus != 1:
            continue

        data.append({
            "requestedUsername": requested_username,
            "hasVerifiedBadge": user.is_verified,
            "id": user.id,
            "name": user.username,
            "displayName": user.username,
        })

    self.send_json({"data": data})
    return True


@server_path(r'/v1/users/(\d+)', regex=True, commands={'GET'})
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    return send_user_details_v1(self, int(match.group(1)))


@server_path('/v1/usernames/users', commands={'POST'})
def _(self: web_server_handler) -> bool:
    return send_username_users_v1(self)


@server_path('/v1/users/authenticated/roles', commands={'GET'})
@util.auth.authenticated_required_api
def authenticated_roles(self: web_server_handler) -> bool:
    self.send_json({"roles": []})
    return True
