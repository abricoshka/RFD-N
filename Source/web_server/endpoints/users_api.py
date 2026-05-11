import json
import re
import urllib

import util.auth
from web_server._logic import web_server_handler, server_path

def _read_json_body(self: web_server_handler) ->  dict[str, str] | None:
    try:
        raw = self.read_content()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        self.send_json(
            {"errors": [{"code": 0, "message": "Malformed JSON body"}]},
            400,
        )
        return None

    if not isinstance(payload, dict):
        self.send_json(
            {"errors": [{"code": 0, "message": "Malformed JSON body"}]},
            400,
        )
        return None
    return payload

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


@server_path('/user-profile-api/v1/user/profiles/get-profiles', commands={'POST'})
def _(self: web_server_handler) -> bool:
    payload = _read_json_body(self)

    user_ids_raw: str = str(payload.get('userIds'))
    if user_ids_raw is None:
        self.send_json({"errors": [{"code": 4, "message": "The requested Ids are invalid, of an invalid type or missing."}]}, 400)
        return True

    user_ids = user_ids_raw.split(",")
    if len(user_ids) > 100:
        self.send_json({"errors": [{"code": 1, "message": "There are too many requested Ids."}]}, 400)
        return True

    processed_requests = []
    for user_id in user_ids:
        try:
            user_id_num = int(user_id)
            print(user_id_num)
        except ValueError:
            continue
        user = self.server.storage.user.check_object(user_id_num)
        if user is None:
            processed_requests.append({
                "userId": user_id_num,
                "names": {
                    "alias": None,
                    "username": None,
                    "displayName": None,
                    "contactName": None,
                    "combinedName": None,
                    "platformName": None
                },
                "platformProfileId": None,
                "isVerified": False
            })
            continue

        processed_requests.append({
            "userId": user.id,
            "names": {
                "alias": None,
                "username": user.username,
                "displayName": user.username,
                "contactName": None,
                "combinedName": user.username,
                "platformName": None
            },
            "platformProfileId": None,
            "isVerified": user.is_verified
        })

    self.send_json({
        "profileDetails": processed_requests,
        "errors": []
    })
    return True