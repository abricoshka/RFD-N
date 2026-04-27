import json
import re
from typing import Any

import util.auth
import util.versions as versions
from web_server._logic import web_server_handler, server_path


@server_path(r'/v1/users/(\d+)/friends', regex=True, versions={versions.rōblox.v463}, commands={'POST', 'GET'})
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    '''
    Dummy endpoint for 2021E.
    Script 'Chat.ChatModules.FriendJoinNotifier', Line 46
    '''
    self.send_json({"data": []})
    return True


@server_path(r'/users/(\d+)', regex=True)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    '''
    GetUsernameFromUserId
    '''
    database = self.server.storage.players

    id_num = match.group(1)
    username = database.get_player_field_from_index(
        database.player_field.IDEN_NUM,
        id_num,
        database.player_field.USERNAME,
    )
    assert username is not None

    self.send_json({'Username': username})
    return True


@server_path("/users/get-by-username")
def _(self: web_server_handler) -> bool:
    database = self.server.storage.players

    username = self.query['username']
    id_num = database.get_player_field_from_index(
        database.player_field.USERNAME,
        username,
        database.player_field.IDEN_NUM,
    )
    assert id_num is not None

    self.send_data(id_num)
    return True


@server_path("/points/get-point-balance")
def _(self: web_server_handler) -> bool:
    # TODO: maybe implement the old player-point sytem.
    self.send_json({"success": True, "pointBalance": 0})
    return True


_PROFILE_COMPONENT_ORDER = (
    "UserProfileHeader",
    "Actions",
    "About",
    "CurrentlyWearing",
    "Store",
    "Experiences",
)


def _send_profile_invalid_request(self: web_server_handler) -> bool:
    self.send_json(
        {"errors": [{"code": 0, "message": "Invalid Request"}]},
        400,
    )
    return True


def _send_profile_parse_error(self: web_server_handler) -> bool:
    self.send_json(
        {"errors": [{"code": 0, "message": "Unable to parse request body."}]},
        400,
    )
    return True


def _parse_profile_request(
    self: web_server_handler,
) -> tuple[int, list[dict[str, Any]], bool] | None:
    raw_body = self.read_content()
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        _send_profile_parse_error(self)
        return None

    if not isinstance(payload, dict):
        _send_profile_invalid_request(self)
        return None

    if payload.get("profileType") != "User":
        _send_profile_invalid_request(self)
        return None

    try:
        profile_id = int(str(payload.get("profileId", "")).strip())
    except ValueError:
        _send_profile_invalid_request(self)
        return None
    if profile_id <= 0:
        _send_profile_invalid_request(self)
        return None

    component_entries = payload.get("components")
    if not isinstance(component_entries, list):
        _send_profile_invalid_request(self)
        return None

    parsed_components: list[dict[str, Any]] = []
    for entry in component_entries:
        if not isinstance(entry, dict):
            _send_profile_invalid_request(self)
            return None

        component_name = entry.get("component")
        if not isinstance(component_name, str) or not component_name:
            _send_profile_invalid_request(self)
            return None

        parsed_components.append(entry)

    return (
        profile_id,
        parsed_components,
        bool(payload.get("includeComponentOrdering")),
    )


def _build_user_profile_header(
    self: web_server_handler,
    profile_user,
    current_user,
) -> dict[str, object]:
    profile_friend_ids = set(
        self.server.storage.friend.list_friend_ids(profile_user.id),
    )
    mutual_friend_count = 0
    if current_user is not None and current_user.id != profile_user.id:
        current_user_friend_ids = set(
            self.server.storage.friend.list_friend_ids(current_user.id),
        )
        mutual_friend_count = len(profile_friend_ids & current_user_friend_ids)
    followers_count = self.server.storage.follow_relationship.count_followers(profile_user.id)
    followings_count = self.server.storage.follow_relationship.count_following(profile_user.id)

    return {
        "userId": profile_user.id,
        "isPremium": profile_user.is_premium,
        "isVerified": profile_user.is_verified,
        "isRobloxAdmin": profile_user.is_roblox_admin,
        "counts": {
            "friendsCount": len(profile_friend_ids),
            "followersCount": followers_count,
            "followingsCount": followings_count,
            "mutualFriendsCount": mutual_friend_count,
            "isFriendsCountEnabled": False,
            "isFollowersCountEnabled": False,
            "isFollowingsCountEnabled": False,
            "isMutualFriendsCountEnabled": False,
        },
        "names": {
            "primaryName": profile_user.username,
            "username": profile_user.username,
            "displayName": profile_user.username,
        },
        "contextualInformation": {
            "context": "None",
        },
        "editName": None,
    }


def _filter_supported_actions(
    requested_component: dict[str, Any],
    actions: list[str],
) -> list[str]:
    supported_actions = requested_component.get("supportedActions")
    if not isinstance(supported_actions, list):
        return actions

    allowed_actions = {
        value
        for value in supported_actions
        if isinstance(value, str) and value
    }
    if not allowed_actions:
        return []
    return [
        action
        for action in actions
        if action in allowed_actions
    ]


def _build_actions_component(
    self: web_server_handler,
    requested_component: dict[str, Any],
    profile_user,
    current_user,
) -> dict[str, object]:
    if current_user is not None and current_user.id == profile_user.id:
        button_actions = _filter_supported_actions(
            requested_component,
            ["EditProfile"],
        )
        contextual_actions = _filter_supported_actions(
            requested_component,
            ["EditAvatar", "CopyLink", "ShareProfile", "ViewFullProfile"],
        )
        return {
            "buttons": [{"type": action} for action in button_actions],
            "contextual": contextual_actions,
        }

    relationship = None
    if current_user is not None:
        relationship = self.server.storage.friend.check_pair(
            current_user.id,
            profile_user.id,
        )

    primary_action = "AddFriend"
    follow_action = "Follow"
    contextual_candidates = [
        "Block",
        "Report",
        "CopyLink",
        "ShareProfile",
        "ViewFullProfile",
    ]
    if current_user is not None and self.server.storage.follow_relationship.is_following(
        current_user.id,
        profile_user.id,
    ):
        follow_action = "Unfollow"
    contextual_candidates.insert(0, follow_action)
    if relationship is not None:
        if relationship.status == 1:
            primary_action = "Unfriend"
            contextual_candidates.insert(0, "Chat")
        elif relationship.requester_id == current_user.id:
            primary_action = "PendingFriendRequest"
        else:
            primary_action = "AcceptFriendRequest"
            contextual_candidates.insert(0, "IgnoreFriendRequest")

    button_actions = _filter_supported_actions(
        requested_component,
        [primary_action],
    )
    contextual_actions = _filter_supported_actions(
        requested_component,
        contextual_candidates,
    )
    return {
        "buttons": [{"type": action} for action in button_actions],
        "contextual": contextual_actions,
    }


def _build_currently_wearing_component(
    self: web_server_handler,
    profile_user,
) -> dict[str, object]:
    asset_ids = self.server.storage.user_asset.list_asset_ids_for_user(
        profile_user.id,
        limit=12,
    )
    return {
        "assets": [{
            "assetId": asset_id,
            "itemType": "Asset",
        } for asset_id in asset_ids],
    }


def _build_experiences_component(
    self: web_server_handler,
    profile_user,
) -> dict[str, object]:
    experience_ids: list[int] = []
    for universe_id in self.server.storage.universe.list_ids_for_creator(
        0,
        profile_user.id,
        limit=18,
    ):
        universe = self.server.storage.universe.check(universe_id)
        if universe is None:
            continue

        place = self.server.storage.place.check_object(int(universe[0]))
        if place is None or not place.is_public or place.assetObj is None:
            continue

        experience_ids.append(universe_id)

    return {
        "experiences": [{
            "universeId": universe_id,
        } for universe_id in experience_ids],
        "previousCursor": None,
        "nextCursor": None,
    }


def _build_store_component(
    self: web_server_handler,
    profile_user,
) -> dict[str, object] | None:
    asset_ids = self.server.storage.user_asset.list_asset_ids_for_user(
        profile_user.id,
        limit=30,
        is_for_sale=True,
    )
    if not asset_ids:
        return None

    return {
        "name": profile_user.username,
        "assets": [{
            "assetId": asset_id,
            "itemType": "Asset",
        } for asset_id in asset_ids],
    }


@server_path("/profile-platform-api/v1/profiles/get", commands={"POST"})
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    request_data = _parse_profile_request(self)
    if request_data is None:
        return True

    profile_id, requested_components, include_component_ordering = request_data
    profile_user = self.server.storage.user.check_object(profile_id)
    if profile_user is None:
        return _send_profile_invalid_request(self)

    current_user = util.auth.GetCurrentUser(self)
    requested_component_map = {
        component["component"]: component
        for component in requested_components
    }

    response_components: dict[str, object] = {}
    if "UserProfileHeader" in requested_component_map:
        response_components["UserProfileHeader"] = _build_user_profile_header(
            self,
            profile_user,
            current_user,
        )
    if "Actions" in requested_component_map:
        response_components["Actions"] = _build_actions_component(
            self,
            requested_component_map["Actions"],
            profile_user,
            current_user,
        )
    if "About" in requested_component_map and profile_user.description:
        response_components["About"] = {
            "description": profile_user.description,
        }
    if "CurrentlyWearing" in requested_component_map:
        response_components["CurrentlyWearing"] = _build_currently_wearing_component(
            self,
            profile_user,
        )
    if "Store" in requested_component_map:
        store_component = _build_store_component(self, profile_user)
        if store_component is not None:
            response_components["Store"] = store_component
    if "Experiences" in requested_component_map:
        response_components["Experiences"] = _build_experiences_component(
            self,
            profile_user,
        )

    payload: dict[str, object] = {
        "profileType": "User",
        "profileId": str(profile_user.id),
        "components": response_components,
        "onlyEssentialComponents": None,
        "gracefulDegradationEnabled": False,
    }
    if include_component_ordering:
        payload["componentOrdering"] = [
            component_name
            for component_name in _PROFILE_COMPONENT_ORDER
            if component_name in response_components
        ]

    self.send_json(payload)
    return True
