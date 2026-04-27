from __future__ import annotations

import json
from typing import Any

from enums.AssetType import AssetType
from enums.PlaceRigChoice import PlaceRigChoice
import util.auth
import util.thumbnailer
from storage.user_avatar import user_avatar_item
from web_server._logic import server_path, web_server_handler


AVATAR_METADATA = {
    "enableDefaultClothingMessage": False,
    "isAvatarScaleEmbeddedInTab": True,
    "isBodyTypeScaleOutOfTab": True,
    "scaleHeightIncrement": 0.05,
    "scaleWidthIncrement": 0.05,
    "scaleHeadIncrement": 0.05,
    "scaleProportionIncrement": 0.05,
    "scaleBodyTypeIncrement": 0.05,
    "supportProportionAndBodyType": True,
    "showDefaultClothingMessageOnPageLoad": False,
    "areThreeDeeThumbsEnabled": False,
    "isAvatarWearingApiCallsLockingOnFrontendEnabled": True,
    "isOutfitHandlingOnFrontendEnabled": True,
    "isJustinUiChangesEnabled": True,
    "isCategoryReorgEnabled": True,
    "LCEnabledInEditorAndCatalog": True,
    "isLCCompletelyEnabled": True,
}

WEARABLE_ASSET_TYPES = [
    {"maxNumber": 1, "id": 18, "name": "Face"},
    {"maxNumber": 1, "id": 19, "name": "Gear"},
    {"maxNumber": 1, "id": 17, "name": "Head"},
    {"maxNumber": 1, "id": 29, "name": "Left Arm"},
    {"maxNumber": 1, "id": 30, "name": "Left Leg"},
    {"maxNumber": 1, "id": 12, "name": "Pants"},
    {"maxNumber": 1, "id": 28, "name": "Right Arm"},
    {"maxNumber": 1, "id": 31, "name": "Right Leg"},
    {"maxNumber": 1, "id": 11, "name": "Shirt"},
    {"maxNumber": 1, "id": 2, "name": "T-Shirt"},
    {"maxNumber": 1, "id": 27, "name": "Torso"},
    {"maxNumber": 1, "id": 48, "name": "Climb Animation"},
    {"maxNumber": 1, "id": 49, "name": "Death Animation"},
    {"maxNumber": 1, "id": 50, "name": "Fall Animation"},
    {"maxNumber": 1, "id": 51, "name": "Idle Animation"},
    {"maxNumber": 1, "id": 52, "name": "Jump Animation"},
    {"maxNumber": 1, "id": 53, "name": "Run Animation"},
    {"maxNumber": 1, "id": 54, "name": "Swim Animation"},
    {"maxNumber": 1, "id": 55, "name": "Walk Animation"},
    {"maxNumber": 1, "id": 56, "name": "Pose Animation"},
    {"maxNumber": 3, "id": 8, "name": "Hat"},
    {"maxNumber": 5, "id": 41, "name": "Hair Accessory"},
    {"maxNumber": 5, "id": 42, "name": "Face Accessory"},
    {"maxNumber": 1, "id": 43, "name": "Neck Accessory"},
    {"maxNumber": 1, "id": 44, "name": "Shoulder Accessory"},
    {"maxNumber": 1, "id": 45, "name": "Front Accessory"},
    {"maxNumber": 1, "id": 46, "name": "Back Accessory"},
    {"maxNumber": 1, "id": 47, "name": "Waist Accessory"},
    {"maxNumber": 1, "id": 72, "name": "Dress Skirt Accessory"},
    {"maxNumber": 1, "id": 67, "name": "Jacket Accessory"},
    {"maxNumber": 1, "id": 70, "name": "Left Shoe Accessory"},
    {"maxNumber": 1, "id": 71, "name": "Right Shoe Accessory"},
    {"maxNumber": 1, "id": 66, "name": "Pants Accessory"},
    {"maxNumber": 1, "id": 65, "name": "Shirt Accessory"},
    {"maxNumber": 1, "id": 69, "name": "Shorts Accessory"},
    {"maxNumber": 1, "id": 68, "name": "Sweater Accessory"},
    {"maxNumber": 1, "id": 64, "name": "T-Shirt Accessory"},
    {"maxNumber": 1, "id": 76, "name": "Eyebrow Accessory"},
    {"maxNumber": 1, "id": 77, "name": "Eyelash Accessory"},
    {"maxNumber": 1, "id": 78, "name": "Mood Animation"},
    {"maxNumber": 1, "id": 79, "name": "Dynamic Head"},
]

BODY_COLOR_HEX_BY_ID = {
    1: "F2F3F3",
    5: "D7C59A",
    9: "E8BAC8",
    11: "80BBDC",
    18: "CC8E69",
    21: "C4281C",
    23: "0D69AC",
    24: "F5CD30",
    26: "1B2A35",
    28: "287F47",
    29: "A1C48C",
    37: "4B974B",
    38: "A05F35",
    45: "B4D2E4",
    101: "DA867A",
    102: "6E99CA",
    104: "6B327C",
    105: "E29B40",
    106: "DA8541",
    107: "008F9C",
    119: "A4BD47",
    125: "EAB892",
    133: "D5733D",
    135: "74869D",
    141: "27462D",
    151: "789082",
    153: "957977",
    192: "694028",
    194: "A3A2A5",
    199: "635F62",
    208: "E5E4DF",
    217: "7C5C46",
    226: "FDEA8D",
    305: "527CAE",
    310: "5B9A4C",
    317: "7C9C6B",
    321: "A75E9B",
    330: "FF98DC",
    334: "F8D96D",
    351: "BC9B5D",
    352: "C7AC78",
    359: "AF9483",
    361: "564236",
    364: "5A4C42",
    1001: "F8F8F8",
    1002: "CDCDCD",
    1003: "111111",
    1004: "FF0000",
    1006: "B480FF",
    1007: "A34B4B",
    1008: "C1BE42",
    1009: "FFFF00",
    1010: "0000FF",
    1011: "002060",
    1012: "2154B9",
    1013: "04AFEC",
    1014: "AA5500",
    1015: "AA00AA",
    1016: "FF66CC",
    1017: "FFAF00",
    1018: "12EED4",
    1019: "00FFFF",
    1020: "00FF00",
    1021: "3A7D15",
    1022: "7F8E64",
    1023: "8C5B9F",
    1024: "AFDDFF",
    1025: "FFC9C9",
    1026: "B1A7FF",
    1027: "9FF3E9",
    1028: "CCFFCC",
    1029: "FFFFCC",
    1030: "FFCC99",
    1031: "6225D1",
    1032: "FF00BF",
}

BODY_COLORS_PALETTE = [
    {"brickColorId": color_id, "hexColor": f"#{hex_color}", "name": str(color_id)}
    for color_id, hex_color in sorted(BODY_COLOR_HEX_BY_ID.items())
]
ALLOWED_BODY_COLOR_IDS = set(BODY_COLOR_HEX_BY_ID)
WEARABLE_ASSET_TYPE_LIMITS = {
    int(item["id"]): int(item["maxNumber"])
    for item in WEARABLE_ASSET_TYPES
}
ANIMATION_ASSET_FIELD_NAMES = {
    AssetType.ClimbAnimation: "climb",
    AssetType.DeathAnimation: "death",
    AssetType.FallAnimation: "fall",
    AssetType.IdleAnimation: "idle",
    AssetType.JumpAnimation: "jump",
    AssetType.RunAnimation: "run",
    AssetType.SwimAnimation: "swim",
    AssetType.WalkAnimation: "walk",
    AssetType.PoseAnimation: "pose",
    AssetType.MoodAnimation: "mood",
}
SHIRT_ASSET_TYPES = {
    AssetType.Shirt,
    AssetType.TShirt,
    AssetType.ShirtAccessory,
    AssetType.TShirtAccessory,
    AssetType.SweaterAccessory,
    AssetType.JacketAccessory,
}
PANTS_ASSET_TYPES = {
    AssetType.Pants,
    AssetType.PantsAccessory,
    AssetType.ShortsAccessory,
}
EMOTE_PLACEHOLDER = [
    {"assetId": 3696763549, "assetName": "Heisman Pose", "position": 1},
    {"assetId": 3360692915, "assetName": "Tilt", "position": 2},
    {"assetId": 3696761354, "assetName": "Air Guitar", "position": 3},
    {"assetId": 3576968026, "assetName": "Shrug", "position": 4},
    {"assetId": 3576686446, "assetName": "Hello", "position": 5},
    {"assetId": 3696759798, "assetName": "Superhero Reveal", "position": 6},
    {"assetId": 3360689775, "assetName": "Salute", "position": 7},
    {"assetId": 3360686498, "assetName": "Stadium", "position": 8},
]

AVATAR_RULES = {
    "playerAvatarTypes": ["R6", "R15"],
    "scales": {
        "height": {"min": 0.9, "max": 1.05, "increment": 0.01},
        "width": {"min": 0.7, "max": 1, "increment": 0.01},
        "head": {"min": 0.95, "max": 1, "increment": 0.01},
        "proportion": {"min": 0, "max": 1, "increment": 0.01},
        "bodyType": {"min": 0, "max": 1, "increment": 0.01},
    },
    "wearableAssetTypes": WEARABLE_ASSET_TYPES,
    "bodyColorsPalette": BODY_COLORS_PALETTE,
    "basicBodyColorsPalette": BODY_COLORS_PALETTE[:30],
    "minimumDeltaEBodyColorDifference": 11.4,
    "proportionsAndBodyTypeEnabledForUser": True,
    "defaultClothingAssetLists": {
        "defaultShirtAssetIds": [855776103, 855760101, 855766176, 855777286],
        "defaultPantAssetIds": [855783877, 855780360, 855781078, 855782781],
    },
    "bundlesEnabledForUser": False,
    "emotesEnabledForUser": False,
}


def _send_invalid_json(self: web_server_handler) -> bool:
    self.send_json({"errors": [{"code": 0, "message": "Invalid JSON"}]}, 400)
    return True


def _read_json_object(self: web_server_handler) -> dict[str, Any] | None:
    raw_body = self.read_content()
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        _send_invalid_json(self)
        return None
    if not isinstance(payload, dict):
        _send_invalid_json(self)
        return None
    return payload


def _require_authenticated_user(self: web_server_handler):
    token = util.auth.GetRequestToken(self)
    if token is None:
        util.auth._send_api_auth_error(self, message="You are not logged in")
        return None
    if not util.auth.ValidateToken(self.server.storage, token):
        util.auth._send_api_auth_error(
            self,
            message="You are not logged in",
            clear_cookie=True,
        )
        return None
    user = util.auth.GetCurrentUser(self)
    if user is None:
        util.auth._send_api_auth_error(self, message="You are not logged in")
        return None
    return user


def _get_or_create_avatar(self: web_server_handler, user_id: int) -> user_avatar_item:
    return self.server.storage.user_avatar.ensure(user_id)


def _save_avatar(self: web_server_handler, avatar: user_avatar_item) -> None:
    self.server.storage.user_avatar.update(
        avatar.user_id,
        content_hash=avatar.content_hash,
        avatar_type=avatar.avatar_type,
        head_color_id=avatar.head_color_id,
        torso_color_id=avatar.torso_color_id,
        right_arm_color_id=avatar.right_arm_color_id,
        left_arm_color_id=avatar.left_arm_color_id,
        right_leg_color_id=avatar.right_leg_color_id,
        left_leg_color_id=avatar.left_leg_color_id,
        r15=avatar.r15,
        height_scale=avatar.height_scale,
        width_scale=avatar.width_scale,
        head_scale=avatar.head_scale,
        depth_scale=avatar.depth_scale,
        proportion_scale=avatar.proportion_scale,
        body_type_scale=avatar.body_type_scale,
    )


def _resolve_avatar_type(
    self: web_server_handler,
    avatar: user_avatar_item,
    place_id: int | None,
) -> str:
    resolved_avatar_type = "R15" if avatar.r15 else "R6"
    if place_id is None:
        return resolved_avatar_type

    place = self.server.storage.place.check_object(place_id)
    if place is None:
        return resolved_avatar_type
    if place.rig_choice == PlaceRigChoice.ForceR6:
        return "R6"
    if place.rig_choice == PlaceRigChoice.ForceR15:
        return "R15"
    return resolved_avatar_type


def _build_asset_payload(asset) -> dict[str, object]:
    return {
        "id": asset.id,
        "name": asset.name,
        "assetType": {
            "id": asset.asset_type.value,
            "name": asset.asset_type.name,
        },
        "currentVersionId": asset.id,
    }


def _collect_equipped_assets(
    self: web_server_handler,
    user_id: int,
) -> tuple[
    list[dict[str, object]],
    list[int],
    list[int],
    list[dict[str, int]],
    dict[str, int],
]:
    assets: list[dict[str, object]] = []
    accessory_ids: list[int] = []
    gear_ids: list[int] = []
    asset_and_type_ids: list[dict[str, int]] = []
    animation_asset_ids: dict[str, int] = {}

    for asset_id in self.server.storage.user_avatar_asset.list_asset_ids_for_user(user_id):
        asset = self.server.storage.asset.resolve_object(asset_id)
        if asset is None or asset.moderation_status != 0:
            continue
        if asset.asset_type == AssetType.Gear:
            gear_ids.append(asset.id)
            continue

        assets.append(_build_asset_payload(asset))
        accessory_ids.append(asset.id)
        asset_and_type_ids.append({"assetId": asset.id, "assetTypeId": asset.asset_type.value})

        animation_key = ANIMATION_ASSET_FIELD_NAMES.get(asset.asset_type)
        if animation_key is not None:
            animation_asset_ids[animation_key] = asset.id

    return assets, accessory_ids, gear_ids, asset_and_type_ids, animation_asset_ids


def _build_body_colors_payload(avatar: user_avatar_item) -> dict[str, int]:
    return {
        "headColorId": avatar.head_color_id,
        "torsoColorId": avatar.torso_color_id,
        "rightArmColorId": avatar.right_arm_color_id,
        "leftArmColorId": avatar.left_arm_color_id,
        "rightLegColorId": avatar.right_leg_color_id,
        "leftLegColorId": avatar.left_leg_color_id,
    }


def _build_body_color3s_payload(avatar: user_avatar_item) -> dict[str, str]:
    return {
        "headColor3": BODY_COLOR_HEX_BY_ID.get(avatar.head_color_id, "F8F8F8"),
        "torsoColor3": BODY_COLOR_HEX_BY_ID.get(avatar.torso_color_id, "F8F8F8"),
        "rightArmColor3": BODY_COLOR_HEX_BY_ID.get(avatar.right_arm_color_id, "F8F8F8"),
        "leftArmColor3": BODY_COLOR_HEX_BY_ID.get(avatar.left_arm_color_id, "F8F8F8"),
        "rightLegColor3": BODY_COLOR_HEX_BY_ID.get(avatar.right_leg_color_id, "F8F8F8"),
        "leftLegColor3": BODY_COLOR_HEX_BY_ID.get(avatar.left_leg_color_id, "F8F8F8"),
    }


def _build_fetch_body_colors_payload(avatar: user_avatar_item) -> dict[str, int]:
    return {
        "HeadColor": avatar.head_color_id,
        "LeftArmColor": avatar.left_arm_color_id,
        "LeftLegColor": avatar.left_leg_color_id,
        "RightArmColor": avatar.right_arm_color_id,
        "RightLegColor": avatar.right_leg_color_id,
        "TorsoColor": avatar.torso_color_id,
        **_build_body_colors_payload(avatar),
    }


def _build_scales_payload(avatar: user_avatar_item) -> dict[str, float]:
    return {
        "height": avatar.height_scale,
        "width": avatar.width_scale,
        "head": avatar.head_scale,
        "depth": avatar.depth_scale,
        "proportion": avatar.proportion_scale,
        "bodyType": avatar.body_type_scale,
    }


def _build_legacy_scales_payload(avatar: user_avatar_item) -> dict[str, float]:
    return {
        "Height": avatar.height_scale,
        "Width": avatar.width_scale,
        "Head": avatar.head_scale,
        "Depth": avatar.depth_scale,
        "Proportion": avatar.proportion_scale,
        "BodyType": avatar.body_type_scale,
    }


def _build_modern_avatar_payload(
    self: web_server_handler,
    user_id: int,
    *,
    include_color3s: bool,
) -> dict[str, object]:
    avatar = _get_or_create_avatar(self, user_id)
    assets, _accessory_ids, _gear_ids, _asset_and_type_ids, _animation_asset_ids = _collect_equipped_assets(
        self,
        user_id,
    )

    has_shirt = any(
        item["assetType"]["id"] in {asset_type.value for asset_type in SHIRT_ASSET_TYPES}
        for item in assets
    )
    has_pants = any(
        item["assetType"]["id"] in {asset_type.value for asset_type in PANTS_ASSET_TYPES}
        for item in assets
    )

    payload = {
        "scales": _build_scales_payload(avatar),
        "playerAvatarType": "R15" if avatar.r15 else "R6",
        "assets": assets,
        "defaultShirtApplied": not has_shirt,
        "defaultPantsApplied": not has_pants,
        "emotes": EMOTE_PLACEHOLDER,
    }
    if include_color3s:
        payload["bodyColor3s"] = _build_body_color3s_payload(avatar)
    else:
        payload["bodyColors"] = _build_body_colors_payload(avatar)
    return payload


def _build_avatar_fetch_payload(
    self: web_server_handler,
    user_id: int,
    *,
    place_id: int | None,
    legacy_v11: bool,
) -> dict[str, object] | None:
    if self.server.storage.user.check_object(user_id) is None:
        self.send_json({"success": False, "error": "Invalid request"}, 400)
        return None

    avatar = _get_or_create_avatar(self, user_id)
    assets, accessory_ids, gear_ids, asset_and_type_ids, animation_asset_ids = _collect_equipped_assets(
        self,
        user_id,
    )
    del assets

    resolved_avatar_type = _resolve_avatar_type(self, avatar, place_id)
    if legacy_v11:
        return {
            "resolvedAvatarType": resolved_avatar_type,
            "accessoryVersionIds": accessory_ids,
            "equippedGearVersionIds": gear_ids,
            "backpackGearVersionIds": gear_ids,
            "assetAndAssetTypeIds": asset_and_type_ids,
            "bodyColors": _build_fetch_body_colors_payload(avatar),
            "animations": {},
            "scales": _build_legacy_scales_payload(avatar),
            "bodyColorsUrl": f"{self.hostname}/Asset/BodyColors.ashx?userId={user_id}",
            "emotes": [],
        }

    return {
        "resolvedAvatarType": resolved_avatar_type,
        "equippedGearVersionIds": gear_ids,
        "backpackGearVersionIds": gear_ids,
        "accessoryVersionIds": accessory_ids,
        "assetAndAssetTypeIds": asset_and_type_ids,
        "animationAssetIds": animation_asset_ids,
        "bodyColors": _build_fetch_body_colors_payload(avatar),
        "scales": _build_scales_payload(avatar),
        "emotes": EMOTE_PLACEHOLDER,
    }


def _parse_user_id(self: web_server_handler, key: str = "userId") -> int | None:
    raw_user_id = self.query.get(key)
    if raw_user_id is None:
        return None
    try:
        user_id = int(raw_user_id)
    except ValueError:
        return None
    return user_id if user_id > 0 else None


def _parse_place_id(self: web_server_handler) -> int | None:
    raw_place_id = self.query.get("placeId")
    if raw_place_id is None:
        return None
    try:
        place_id = int(raw_place_id)
    except ValueError:
        return None
    return place_id if place_id > 0 else None


def _get_game_start_info_payload(self: web_server_handler) -> dict[str, object]:
    version = getattr(getattr(self.game_config, "game_setup", None), "roblox_version", None)
    version_number = version.get_number() if version is not None else 712
    if version_number <= 463:
        return {
            "gameAvatarType": "PlayerChoice",
            "allowCustomAnimations": True,
            "universeAvatarCollisionType": "OuterBox",
            "universeAvatarBodyType": "Standard",
            "jointPositioningType": "ArtistIntent",
            "universeAvatarMinScales": {
                "height": -1e17,
                "width": -1e17,
                "head": -1e17,
                "depth": -1e17,
                "proportion": -1e17,
                "bodyType": -1e17,
            },
            "universeAvatarMaxScales": {
                "height": 1e17,
                "width": 1e17,
                "head": 1e17,
                "depth": 1e17,
                "proportion": 1e17,
                "bodyType": 1e17,
            },
            "universeAvatarAssetOverrides": [],
            "moderationStatus": None,
        }

    return {
        "gameAvatarType": "PlayerChoice",
        "allowCustomAnimations": "True",
        "universeAvatarCollisionType": "OuterBox",
        "universeAvatarBodyType": "Standard",
        "jointPositioningType": "ArtistIntent",
        "message": "",
        "universeAvatarMinScales": {
            "height": 0.9,
            "width": 0.7,
            "head": 0.95,
            "depth": 0,
            "proportion": 0,
            "bodyType": 0,
        },
        "universeAvatarMaxScales": {
            "height": 1.05,
            "width": 1,
            "head": 1,
            "depth": 1,
            "proportion": 1,
            "bodyType": 1,
        },
        "universeAvatarAssetOverrides": [],
        "moderationStatus": None,
    }


@server_path("/v1/avatar", commands={"GET"})
@server_path("/v1/avatar/", commands={"GET"})
def get_avatar(self: web_server_handler) -> bool:
    user_id = _parse_user_id(self)
    if user_id is not None:
        payload = _build_avatar_fetch_payload(
            self,
            user_id,
            place_id=_parse_place_id(self),
            legacy_v11=False,
        )
        if payload is None:
            return True
        self.send_json(payload)
        return True

    current_user = _require_authenticated_user(self)
    if current_user is None:
        return True
    self.send_json(_build_modern_avatar_payload(self, current_user.id, include_color3s=False))
    return True


@server_path("/v2/avatar/avatar", commands={"GET"})
@util.auth.authenticated_required_api
def get_avatar_v2(self: web_server_handler) -> bool:
    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.send_json(_build_modern_avatar_payload(self, current_user.id, include_color3s=True))
    return True


@server_path("/v1/avatar/metadata", commands={"GET"})
@util.auth.authenticated_required_api
def get_avatar_metadata(self: web_server_handler) -> bool:
    self.send_json(AVATAR_METADATA)
    return True


@server_path("/v1/avatar-rules", commands={"GET"})
@util.auth.authenticated_required_api
def get_avatar_rules(self: web_server_handler) -> bool:
    self.send_json(AVATAR_RULES)
    return True


@server_path("/v1/avatar/set-player-avatar-type", commands={"POST"})
@util.auth.authenticated_required_api
def set_player_avatar_type(self: web_server_handler) -> bool:
    payload = _read_json_object(self)
    if payload is None:
        return True

    player_avatar_type = payload.get("playerAvatarType")
    if player_avatar_type not in {"R6", "R15"}:
        return _send_invalid_json(self)

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    avatar = _get_or_create_avatar(self, current_user.id)
    avatar.r15 = player_avatar_type == "R15"
    _save_avatar(self, avatar)
    util.thumbnailer.TakeUserThumbnail(self.server.storage, current_user.id)
    self.send_json({"success": True})
    return True


@server_path("/v1/avatar/set-scales", commands={"POST"})
@util.auth.authenticated_required_api
def set_player_avatar_scales(self: web_server_handler) -> bool:
    payload = _read_json_object(self)
    if payload is None:
        return True

    required_fields = ("height", "width", "head", "proportion", "bodyType")
    if any(field_name not in payload for field_name in required_fields):
        return _send_invalid_json(self)

    try:
        height = float(payload["height"])
        width = float(payload["width"])
        head = float(payload["head"])
        proportion = float(payload["proportion"])
        body_type = float(payload["bodyType"])
        depth = float(payload.get("depth", 1.0))
    except (TypeError, ValueError):
        return _send_invalid_json(self)

    if not (
        0.9 <= height <= 1.05 and
        0.7 <= width <= 1 and
        0.95 <= head <= 1 and
        0 <= proportion <= 1 and
        0 <= body_type <= 1 and
        0 <= depth <= 1
    ):
        return _send_invalid_json(self)

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    avatar = _get_or_create_avatar(self, current_user.id)
    avatar.height_scale = height
    avatar.width_scale = width
    avatar.head_scale = head
    avatar.depth_scale = depth
    avatar.proportion_scale = proportion
    avatar.body_type_scale = body_type
    _save_avatar(self, avatar)
    util.thumbnailer.TakeUserThumbnail(self.server.storage, current_user.id)
    self.send_json({"success": True})
    return True


@server_path("/v1/avatar/set-body-colors", commands={"POST"})
@util.auth.authenticated_required_api
def set_player_avatar_body_colors(self: web_server_handler) -> bool:
    payload = _read_json_object(self)
    if payload is None:
        return True

    required_fields = (
        "headColorId",
        "torsoColorId",
        "rightArmColorId",
        "leftArmColorId",
        "rightLegColorId",
        "leftLegColorId",
    )
    if any(field_name not in payload for field_name in required_fields):
        return _send_invalid_json(self)

    try:
        head_color_id = int(payload["headColorId"])
        torso_color_id = int(payload["torsoColorId"])
        right_arm_color_id = int(payload["rightArmColorId"])
        left_arm_color_id = int(payload["leftArmColorId"])
        right_leg_color_id = int(payload["rightLegColorId"])
        left_leg_color_id = int(payload["leftLegColorId"])
    except (TypeError, ValueError):
        return _send_invalid_json(self)

    if any(
        body_color_id not in ALLOWED_BODY_COLOR_IDS
        for body_color_id in (
            head_color_id,
            torso_color_id,
            right_arm_color_id,
            left_arm_color_id,
            right_leg_color_id,
            left_leg_color_id,
        )
    ):
        return _send_invalid_json(self)

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    avatar = _get_or_create_avatar(self, current_user.id)
    avatar.head_color_id = head_color_id
    avatar.torso_color_id = torso_color_id
    avatar.right_arm_color_id = right_arm_color_id
    avatar.left_arm_color_id = left_arm_color_id
    avatar.right_leg_color_id = right_leg_color_id
    avatar.left_leg_color_id = left_leg_color_id
    _save_avatar(self, avatar)
    util.thumbnailer.TakeUserThumbnail(self.server.storage, current_user.id)
    self.send_json({"success": True})
    return True


@server_path("/v1/avatar/set-wearing-assets", commands={"POST"})
@util.auth.authenticated_required_api
def set_player_avatar_wearing_assets(self: web_server_handler) -> bool:
    payload = _read_json_object(self)
    if payload is None:
        return True

    asset_ids_payload = payload.get("assetIds")
    if not isinstance(asset_ids_payload, list):
        return _send_invalid_json(self)

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None

    invalid_asset_ids: list[int] = []
    allowed_asset_ids: list[int] = []
    asset_type_counter: dict[int, int] = {}

    for raw_asset_id in asset_ids_payload:
        try:
            requested_asset_id = int(raw_asset_id)
        except (TypeError, ValueError):
            return _send_invalid_json(self)

        if requested_asset_id in invalid_asset_ids or requested_asset_id in allowed_asset_ids:
            continue

        asset = self.server.storage.asset.resolve_object(requested_asset_id)
        if asset is None:
            invalid_asset_ids.append(requested_asset_id)
            continue
        if self.server.storage.user_asset.check(current_user.id, asset.id) is None:
            invalid_asset_ids.append(requested_asset_id)
            continue
        if asset.moderation_status != 0:
            invalid_asset_ids.append(requested_asset_id)
            continue

        max_items = WEARABLE_ASSET_TYPE_LIMITS.get(asset.asset_type.value)
        if max_items is None or max_items <= 0:
            self.send_json({"errors": [{"code": 3, "message": "Invalid AssetId"}]}, 400)
            return True

        current_count = asset_type_counter.get(asset.asset_type.value, 0)
        if current_count >= max_items:
            self.send_json({"errors": [{"code": 3, "message": "Invalid AssetId"}]}, 400)
            return True

        asset_type_counter[asset.asset_type.value] = current_count + 1
        allowed_asset_ids.append(asset.id)

    self.server.storage.user_avatar_asset.replace_for_user(current_user.id, allowed_asset_ids)
    util.thumbnailer.TakeUserThumbnail(self.server.storage, current_user.id)
    self.send_json({"invalidAssetIds": invalid_asset_ids, "success": True})
    return True


@server_path("/v1/avatar-fetch", commands={"GET"})
@server_path("/v1/avatar-fetch/", commands={"GET"})
def get_avatar_fetch(self: web_server_handler) -> bool:
    user_id = _parse_user_id(self)
    if user_id is None:
        self.send_json({"success": False, "error": "Invalid request"}, 400)
        return True

    payload = _build_avatar_fetch_payload(
        self,
        user_id,
        place_id=_parse_place_id(self),
        legacy_v11=False,
    )
    if payload is None:
        return True
    self.send_json(payload)
    return True


@server_path("/v1.1/avatar-fetch", commands={"GET"})
@server_path("/v1.1/avatar-fetch/", commands={"GET"})
def get_avatar_fetch_v11(self: web_server_handler) -> bool:
    user_id = _parse_user_id(self)
    if user_id is None:
        self.send_json({"success": False, "error": "Invalid request"}, 400)
        return True

    payload = _build_avatar_fetch_payload(
        self,
        user_id,
        place_id=_parse_place_id(self),
        legacy_v11=True,
    )
    if payload is None:
        return True
    self.send_json(payload)
    return True


@server_path("/v1/game-start-info", commands={"GET"})
@server_path("/v1.1/game-start-info", commands={"GET"})
def get_game_start_info(self: web_server_handler) -> bool:
    self.send_json(_get_game_start_info_payload(self))
    return True
