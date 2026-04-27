import re

import util.auth
from web_server._logic import server_path, web_server_handler


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


@server_path('/player-hydration-service/v1/players/signed', commands={'GET'})
@util.auth.authenticated_required_api
def player_hydration_signed(self: web_server_handler) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    player_payload = {
        "id": current_user.id,
        "userId": current_user.id,
        "name": current_user.username,
        "displayName": current_user.username,
        "isPremium": current_user.is_premium,
        "hasVerifiedBadge": current_user.is_verified,
        "isUnder13": False,
        "countryCode": "US",
    }
    self.send_json({
        "data": [player_payload],
        "players": [player_payload],
        "signedUser": player_payload,
    })
    return True


@server_path(r'/universes/v1/places/(\d+)/universe', regex=True, commands={'GET'})
def universe_for_place(self: web_server_handler, match: re.Match[str]) -> bool:
    place_id = int(match.group(1))
    universe_id = _resolve_universe_id_for_place(self, place_id)
    if universe_id == 0:
        self.send_json(
            {"errors": [{"code": 0, "message": "Place universe not found."}]},
            404,
        )
        return True

    self.send_json({"universeId": universe_id})
    return True


@server_path('/guac-v2/v1/bundles/app-policy', commands={'GET'})
@server_path('/guac-v2/v1/bundles/intl-auth-compliance', commands={'GET'})
def guac_bundle_stub(self: web_server_handler) -> bool:
    self.send_json({})
    return True


@server_path('/platform-chat-api/v1/get-conversation-metadata', commands={'GET'})
def platform_chat_conversation_metadata(self: web_server_handler) -> bool:
    self.send_json({"data": []})
    return True


@server_path('/platform-chat-api/v1/metadata', commands={'GET'})
def platform_chat_metadata(self: web_server_handler) -> bool:
    self.send_json({
        "isChatEnabled": True,
        "canUserChat": True,
        "notificationsEnabled": False,
    })
    return True


@server_path('/upsellcard/type', commands={'GET'})
def upsellcard_type(self: web_server_handler) -> bool:
    self.send_json({
        "type": None,
    })
    return True


@server_path('/account-security-service/v1/prompt-assignments', commands={'GET'})
def account_security_prompt_assignments(self: web_server_handler) -> bool:
    self.send_json({
        "promptAssignments": [],
        "metadata": {},
    })
    return True


@server_path('/modals-api/v1/modal', commands={'GET'})
def modal_payload(self: web_server_handler) -> bool:
    self.send_json({
        "modalType": None,
        "display": False,
    })
    return True


@server_path(r'/+robuxbadge/v1/robuxbadge', regex=True, commands={'GET'})
def robuxbadge(self: web_server_handler, match: re.Match[str]) -> bool:
    del match
    self.send_json({
        "enabled": False,
        "imageUrl": None,
    })
    return True


@server_path(r'/+v1/catalog/metadata', regex=True, commands={'GET'})
def catalog_metadata(self: web_server_handler, match: re.Match[str]) -> bool:
    del match
    self.send_json({
        "isCatalogEnabled": True,
    })
    return True


@server_path('/v1/reminder', commands={'GET'})
def moderation_reminder(self: web_server_handler) -> bool:
    self.send_json({
        "showReminder": False,
    })
    return True


@server_path('/metrics/v1/performance/measurements', commands={'POST'})
def performance_measurements(self: web_server_handler) -> bool:
    self.send_json({})
    return True


@server_path('/v1/messages/unread/count', commands={'GET'})
def private_message_unread_count(self: web_server_handler) -> bool:
    self.send_json({
        "count": 0,
    })
    return True


@server_path('/v2/stream-notifications/unread-count', commands={'GET'})
def stream_notifications_unread_count(self: web_server_handler) -> bool:
    self.send_json({
        "unreadCount": 0,
    })
    return True


@server_path(
    r'/v1/user-localization-settings/player-choice/(\d+)',
    regex=True,
    commands={'GET'},
)
def gameinternationalization_player_choice(
    self: web_server_handler,
    match: re.Match[str],
) -> bool:
    del match
    self.send_json({
        "supportedLocaleCode": "en_us",
        "localeCode": "en_us",
        "source": "PlayerChoice",
    })
    return True
