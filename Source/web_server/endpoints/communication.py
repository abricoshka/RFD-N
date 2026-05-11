import util.auth
from web_server._logic import web_server_handler, server_path
import urllib.parse
import re


@server_path(r'/game/players/(\d+)/', regex=True)
@server_path(r'/127.0.0.1/game/players/(\d+)/', regex=True)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    self.send_json({"ChatFilter": "blacklist"})
    return True


@server_path("/moderation/v2/filtertext")
def _(self: web_server_handler) -> bool:
    database = self.server.storage.players

    # Manually parsing here since `self.query` isn't automatically populated
    # prior.
    field_data = str(self.read_content(), encoding='utf-8')
    self.query = dict(urllib.parse.parse_qsl(field_data))

    orig_text = self.query['text']
    id_num = int(self.query['userId'])

    user_code = database.get_player_field_from_index(
        database.player_field.IDEN_NUM,
        id_num,
        database.player_field.USERCODE,
    )
    assert user_code is not None

    mod_text = self.game_config.server_core.filter_text(
        orig_text,
        id_num,
        user_code,
    )

    self.send_json({
        "success": True,
        "message": mod_text,
        "data": {
            "AgeUnder13": mod_text,
            "Age13OrOver": mod_text,
        },
    })
    return True


@server_path(
    r'/v1/settings/verify/show-age-verification-overlay/\d+/?',
    regex=True
)
def _(self: web_server_handler, match) -> bool:
    '''
    Voice settings age-check gate probe used by 2022+.
    Mirrors Roblox voice verify payload shape for eligible users. However, this is from 2026.
    '''

    self.send_json({"showAgeVerificationOverlay": False,
                    "inExperienceFaeUpsell": "Disabled",
                    "elegibleToSeeVoiceUpsell": False,
                    "showVoiceOptInOverlay": False,
                    "showVoiceInExperienceUpsell": False,
                    "showVoiceInExperienceUpsellVariant": "",
                    "showAvatarVideoOptInOverlay": False,
                    "showDataConsentToast": False,
                    "showJoinVoiceUpsellTooltip": False,
                    "showM3LikelySpeakingBubbles": False,
                    "isVoiceEnabled": True,
                    "universePlaceVoiceEnabledSettings": {
                        "isUniverseEnabledForVoice": True,
                        "isPlaceEnabledForVoice": True,
                        "isUniverseEnabledForAvatarVideo": True,
                        "isPlaceEnabledForAvatarVideo": True,
                        "isChatGroupsApiEnabled": False,
                    },
                    "voiceSettings": {
                        "isVoiceEnabled": True,
                        "isUserOptIn": True,
                        "isUserEligible": True,
                        "isBanned": False,
                        "banReason": 0,
                        "bannedUntil": None,
                        "canVerifyAgeForVoice": True,
                        "isVerifiedForVoice": True,
                        "denialReason": 0,
                        "isOptInDisabled": False,
                        "hasEverOpted": True,
                        "isAvatarVideoEnabled": False,
                        "isAvatarVideoOptIn": False,
                        "isAvatarVideoOptInDisabled": False,
                        "isAvatarVideoEligible": True,
                        "hasEverOptedAvatarVideo": False,
                        "userHasAvatarCameraAlwaysAvailable": False,
                        "canVerifyPhoneForVoice": False,
                        "seamlessVoiceStatus": 2,
                        "allowVoiceDataUsage": False,
                        "seamlessVoiceVariant": "[]",
                    }
                    })
    return True


@server_path('/v1/settings')
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    self.send_json({"isVoiceEnabled": True})
    return True

@server_path('/v2/rccsettings/user')
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    self.send_json({
      "isVoiceEnabled": True,
      "isUserOptIn": True,
      "isUserEligible": True,
      "isBanned": False,
      "bannedUntil": {
        "Seconds": 0,
        "Nanos": 0
      },
      "canVerifyAgeForVoice": True,
      "isVerifiedForVoice": True,
      "denialReason": 0,
      "isOptInDisabled": True,
      "hasEverOpted": True,
      "isAvatarVideoEnabled": True,
      "isAvatarVideoOptIn": True,
      "isAvatarVideoOptInDisabled": True,
      "isAvatarVideoEligible": True,
      "hasEverOptedAvatarVideo": True
    })
    return True

@server_path(r'/v1/settings/universe/(\d+)', regex=True)
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    self.send_json({
      "isUniverseEnabledForVoice": True,
      "isPlaceEnabledForVoice": True,
      "reasons": [
        "string"
      ],
      "isUniverseEnabledForAvatarVideo": True,
      "isPlaceEnabledForAvatarVideo": True
    })
    return True

@server_path('/v1/settings/user-opt-in')
def _(self: web_server_handler) -> bool:
    self.send_json({"isUserOptIn": True})
    return True

@server_path('/v1/calls/leave')
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    self.send_json({
        "status": "Success"
    })
    return True