# Standard library imports
from datetime import UTC, datetime
import json
import time
import re
import urllib.error
import urllib.parse
import urllib.request

# Local application imports
import util.auth
import util.versions
import web_server.endpoints.join_data as join_data
import web_server.settings_files
from web_server._logic import web_server_handler, server_path


@server_path('/studio/e.png')
def _(self: web_server_handler) -> bool:
    self.send_data(b'')
    return True


@server_path('/login/RequestAuth.ashx')
def _(self: web_server_handler) -> bool:
    self.send_data(self.hostname + '/login/negotiate.ashx')
    return True


@server_path('/Users/1630228')
@server_path('/game/GetCurrentUser.ashx')
def _(self: web_server_handler) -> bool:
    time.sleep(2)  # HACK: Studio 2021E won't work without it.
    user = util.auth.GetCurrentUser(self)
    self.send_json(0 if user is None else user.id)
    return True


@server_path('/users/account-info')
def _(self: web_server_handler) -> bool:
    user = util.auth.GetCurrentUser(self)
    if user is not None:
        user_id = user.id
        has_password_set = bool(user.password)
    else:
        session_raw = self.headers.get('Roblox-Session-Id')
        if session_raw:
            try:
                session = json.loads(session_raw)
                user_id = session.get("UserId", 1)
            except Exception:
                user_id = 1
        else:
            user_id = 1
        has_password_set = False

    funds = self.server.storage.funds.check(user_id)
    body = json.dumps({
        "UserId": user_id,
        "RobuxBalance": funds or 0,
        "HasPasswordSet": has_password_set,
        "AgeBracket": 0,
        "Roles": [],
        "EmailNotificationEnabled": False,
        "PasswordNotifcationEnabled": False
    })

    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(body.encode())))
    self.end_headers()
    self.wfile.write(body.encode())
    self.wfile.flush()
    return True


@server_path('/my/settings/json', commands={'GET'})
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    user = util.auth.GetCurrentUser(self)
    if user is not None:
        user_id = user.id
        username = user.username
        account_age = str(user.created)
    else:
        session_raw = self.headers.get('Roblox-Session-Id')
        if session_raw:
            try:
                session = json.loads(session_raw)
                user_id = session.get("UserId", 1)
            except Exception:
                user_id = 1
        else:
            user_id = 1
        username = "Roblox"
        account_age = 360

    self.send_json({
        'ChangeUsernameEnabled': True,
        'IsAdmin': True,
        'UserId': user_id,
        'Name': username,
        'DisplayName': username,
        'IsEmailOnFile': True,
        'IsEmailVerified': True,
        'IsPhoneFeatureEnabled': True,
        'RobuxRemainingForUsernameChange': 9999999,
        'PreviousUserNames': '',
        'UseSuperSafePrivacyMode': False,
        'IsAppChatSettingEnabled': True,
        'IsGameChatSettingEnabled': True,
        'IsParentalSpendControlsEnabled': True,
        'IsSetPasswordNotificationEnabled': False,
        'ChangePasswordRequiresTwoStepVerification': False,
        'ChangeEmailRequiresTwoStepVerification': False,
        'UserEmail': 'r*********@example.com',
        'UserEmailMasked': True,
        'UserEmailVerified': True,
        'CanHideInventory': True,
        'CanTrade': True,
        'MissingParentEmail': False,
        'IsUpdateEmailSectionShown': True,
        'IsUnder13UpdateEmailMessageSectionShown': False,
        'IsUserConnectedToFacebook': False,
        'IsTwoStepToggleEnabled': False,
        'AgeBracket': 0,
        'UserAbove13': True,
        'ClientIpAddress': self.domain,
        'AccountAgeInDays': account_age,
        'IsPremium': False,
        'IsBcRenewalMembership': False,
        'PremiumFeatureId': None,
        'HasCurrencyOperationError': False,
        'CurrencyOperationErrorMessage': None,
        'Tab': None,
        'ChangePassword': False,
        'IsAccountPinEnabled': False,
        'IsAccountRestrictionsFeatureEnabled': False,
        'IsAccountRestrictionsSettingEnabled': False,
        'IsAccountSettingsSocialNetworksV2Enabled': False,
        'IsUiBootstrapModalV2Enabled': True,
        'IsDateTimeI18nPickerEnabled': True,
        'InApp': False,
        'MyAccountSecurityModel': {
            'IsEmailSet': True,
            'IsEmailVerified': True,
            'IsTwoStepEnabled': False,
            'ShowSignOutFromAllSessions': True,
            'TwoStepVerificationViewModel': {
                'UserId': 1,
                'IsEnabled': False,
                'CodeLength': 0,
                'ValidCodeCharacters': None,
            },
        },
        'ApiProxyDomain': self.hostname,
        'AccountSettingsApiDomain': self.hostname,
        'AuthDomain': self.hostname,
        'IsDisconnectFacebookEnabled': True,
        'IsDisconnectXboxEnabled': True,
        'NotificationSettingsDomain': self.hostname,
        'AllowedNotificationSourceTypes': [
            'Test', 'FriendRequestReceived', 'FriendRequestAccepted',
            'PartyInviteReceived', 'PartyMemberJoined', 'ChatNewMessage',
            'PrivateMessageReceived', 'UserAddedToPrivateServerWhiteList',
            'ConversationUniverseChanged', 'TeamCreateInvite', 'GameUpdate',
            'DeveloperMetricsAvailable', 'GroupJoinRequestAccepted',
            'Sendr', 'ExperienceInvitation',
        ],
        'AllowedReceiverDestinationTypes': ['NotificationStream'],
        'BlacklistedNotificationSourceTypesForMobilePush': [],
        'MinimumChromeVersionForPushNotifications': 50,
        'PushNotificationsEnabledOnFirefox': False,
        'LocaleApiDomain': self.hostname,
        'HasValidPasswordSet': True,
        'IsFastTrackAccessible': False,
        'HasFreeNameChange': False,
        'IsAgeDownEnabled': True,
        'IsDisplayNamesEnabled': True,
        'IsBirthdateLocked': False,
    })
    return True

@server_path('/universal-app-configuration/v1/behaviors/studio/content')
def _(self: web_server_handler) -> bool:
    self.send_json(
        web_server.settings_files.read_settings_json(
            'app_config_studio.json',
        ),
    )
    return True


@server_path("/v1/not-approved")
def _(self: web_server_handler) -> bool:
    self.send_json({"notApproved": False}, 200)
    return True


def _format_studio_datetime(value: str) -> str:
    for parser in (
            datetime.fromisoformat,
            lambda raw: datetime.strptime(raw, "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            date_value = parser(value)
            break
        except ValueError:
            continue
    else:
        return value

    if date_value.tzinfo is None:
        date_value = date_value.replace(tzinfo=UTC)
    else:
        date_value = date_value.astimezone(UTC)
    return date_value.isoformat(timespec="milliseconds")


def _resolve_open_place_context(self: web_server_handler):
    storage = self.server.storage
    query = self.query

    universe_id_str = (
            query.get("universeId") or
            query.get("universeid") or
            query.get("UniverseId")
    )
    if universe_id_str:
        try:
            universe_id = int(universe_id_str)
        except ValueError:
            return None
        universe_obj = storage.universe.check(universe_id)
        if universe_obj is None:
            return None
        root_place_id = universe_obj[0]
        place_obj = storage.place.check_object(root_place_id)
        if place_obj is None or place_obj.assetObj is None:
            return None
        return (universe_id, universe_obj, place_obj)

    place_id_str = (
            query.get("placeId") or
            query.get("placeid") or
            query.get("PlaceId") or
            query.get("assetId") or
            query.get("assetid") or
            query.get("AssetId")
    )
    if place_id_str:
        try:
            place_id = int(place_id_str)
        except ValueError:
            return None
    else:
        place_id = None

    if place_id is None:
        universe_obj = storage.universe.check(1)
        if universe_obj is None:
            return None
        place_id = universe_obj[0]
    else:
        universe_obj = storage.universe.check_from_root_place_id(place_id)
        if universe_obj is None:
            return None

    universe_id = storage.universe.get_id_from_root_place_id(place_id)
    if universe_id is None:
        return None

    place_obj = storage.place.check_object(place_id)
    if place_obj is None or place_obj.assetObj is None:
        return None
    return (universe_id, universe_obj, place_obj)


def _parse_bounded_int(
    raw_value: str | None,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if raw_value is None:
        return default
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed_value))


@server_path(r"/v2/universes/(\d+)/places", regex=True)
def get_universe_places(
    self: web_server_handler,
    match: re.Match[str],
) -> bool:
    universe_id = int(match.group(1))
    universe_obj = self.server.storage.universe.check(universe_id)
    if universe_obj is None:
        self.send_json({
            "previousPageCursor": None,
            "nextPageCursor": None,
            "data": [],
        })
        return True

    limit = _parse_bounded_int(
        self.query.get("limit"),
        default=50,
        minimum=1,
        maximum=100,
    )
    offset = _parse_bounded_int(
        self.query.get("cursor"),
        default=0,
        minimum=0,
        maximum=10_000_000,
    )
    sort_order = self.query.get("SortOrder") or self.query.get("sortOrder") or "Asc"
    root_place_id = universe_obj[0]
    places_page = self.server.storage.place.list_objects_for_universe(
        universe_id,
        root_place_id=root_place_id,
        limit=limit,
        offset=offset,
        sort_order=sort_order,
    )

    response_data: list[dict[str, object]] = []
    for place_obj in places_page.items:
        asset_obj = (
            place_obj.assetObj or
            self.server.storage.asset.resolve_object(place_obj.placeid)
        )
        created_at = universe_obj[3]
        updated_at = universe_obj[4]
        name = ""
        description = ""
        if asset_obj is not None:
            created_at = asset_obj.created_at
            updated_at = asset_obj.updated_at
            name = asset_obj.name
            description = asset_obj.description

        response_data.append({
            "maxPlayerCount": None,
            "socialSlotType": None,
            "customSocialSlotsCount": None,
            "allowCopying": None,
            "currentSavedVersion": None,
            "isAllGenresAllowed": None,
            "allowedGearTypes": None,
            "maxPlayersAllowed": place_obj.maxplayers,
            "created": _format_studio_datetime(created_at),
            "updated": _format_studio_datetime(updated_at),
            "id": place_obj.placeid,
            "universeId": universe_id,
            "name": name,
            "description": description,
            "isRootPlace": place_obj.placeid == root_place_id,
        })

    previous_cursor = None if offset <= 0 else str(max(0, offset - limit))
    next_cursor = None
    if places_page.has_next:
        next_cursor = str(offset + len(places_page.items))

    self.send_json({
        "previousPageCursor": previous_cursor,
        "nextPageCursor": next_cursor,
        "data": response_data,
    })
    return True


@server_path("/studio-open-place/v1/openplace")
def _(self: web_server_handler) -> bool:
    resolved = _resolve_open_place_context(self)
    if resolved is None:
        self.send_json({
            "errors": [{
                "message": "Place not found.",
            }],
        }, 404)
        return True

    universe_id, universe_obj, place_obj = resolved
    asset_obj = place_obj.assetObj
    assert asset_obj is not None

    creator_type_name = join_data.get_creator_type_name(universe_obj[2])
    creator_target_id = universe_obj[1]
    self.send_json({
        "universe": {
            "Id": universe_id,
            "RootPlaceId": place_obj.placeid,
            "Name": asset_obj.name,
            "IsArchived": False,
            "CreatorType": creator_type_name,
            "CreatorTargetId": creator_target_id,
            "PrivacyType": "Public" if universe_obj[11] else "Private",
            "Created": _format_studio_datetime(universe_obj[3]),
            "Updated": _format_studio_datetime(universe_obj[4]),
        },
        "teamCreateEnabled": False,
        "place": {
            "Creator": {
                "CreatorType": creator_type_name,
                "CreatorTargetId": creator_target_id,
            }
        }
    })
    return True


@server_path("/v1/gametemplates")
def _(self: web_server_handler) -> bool:
    query = dict(self.query)
    query.setdefault("limit", "53")
    upstream_url = "https://develop.roblox.com/v1/gametemplates"
    encoded_query = urllib.parse.urlencode(query)
    if encoded_query:
        upstream_url = f"{upstream_url}?{encoded_query}"

    request = urllib.request.Request(
        upstream_url,
        headers={
            "Accept": "application/json",
            "User-Agent": self.headers.get("User-Agent", "RFD/1.0"),
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = response.read()
            content_type = (
                    response.headers.get("Content-Type") or
                    "application/json"
            )
            self.send_data(
                payload,
                status=response.status,
                content_type=content_type,
            )
            return True
    except urllib.error.HTTPError as error:
        error_body = error.read()
        content_type = (
                           error.headers.get("Content-Type")
                           if error.headers is not None
                           else None
                       ) or "application/json"
        self.send_data(
            error_body,
            status=error.code,
            content_type=content_type,
        )
        return True
    except urllib.error.URLError:
        self.send_json(
            {"errors": [{"message": "Failed to reach develop.roblox.com"}]},
            502,
        )
    return True


@server_path("/studio-user-settings/plugin-permissions/v2/plugins")
def _(self: web_server_handler) -> bool:
    self.send_json({
        "data": [],
        "nextPageCursor": None,
        "previousPageCursor": None,
    }, 200)
    return True


# TODO: Proper API handling
@server_path(r'/studio-user-settings/v1/user/studiodata/CloudEditKey_placeId(\d+)', regex=True)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    self.send_json(
        {
            "camera": {
                "data": "PHJvYmxveCGJ/w0KGgoAAAEAAAABAAAAAAAAAAAAAABJTlNUGQAAABcAAAAAAAAA8AgAAAAABgAAAENhbWVyYQABAAAAAAAAAFBST1AiAAAAIAAAAAAAAADwEQAAAAATAAAAQXR0cmlidXRlc1NlcmlhbGl6ZQEAAAAAUFJPUEIAAABAAAAAAAAAAPAxAAAAAAYAAABDRnJhbWUQANfEEr9ME7g91XtQPwAAAIB8dH4/IKrgveW/Ub/FzYC9FeIRv4Kr8aKEPLMIhjtD61BST1AcAAAAGgAAAAAAAADwCwAAAAANAAAAQ2FtZXJhU3ViamVjdBMAAAABUFJPUBkAAAAXAAAAAAAAAPAIAAAAAAoAAABDYW1lcmFUeXBlEgAAAABQUk9QHwAAAB0AAAAAAAAA8A4AAAAADAAAAENhcGFiaWxpdGllcyEAAAAAAAAAAFBST1AfAAAAHQAAAAAAAADwDgAAAAATAAAARGVmaW5lc0NhcGFiaWxpdGllcwIAUFJPUBoAAAAYAAAAAAAAAPAJAAAAAAsAAABGaWVsZE9mVmlldwSFGAAAUFJPUB4AAAAcAAAAAAAAAPANAAAAAA8AAABGaWVsZE9mVmlld01vZGUSAAAAAFBST1AdAAAAGwAAAAAAAADwDAAAAAAFAAAARm9jdXMQAoJ30rSEPnRchjj8Y1BST1AWAAAAFAAAAAAAAADwBQAAAAAKAAAASGVhZExvY2tlZAIBUFJPUBgAAAAWAAAAAAAAAPAHAAAAAAkAAABIZWFkU2NhbGUEfwAAAFBST1AZAAAAFwAAAAAAAADwCAAAAAAEAAAATmFtZQEGAAAAQ2FtZXJhUFJPUCAAAAAeAAAAAAAAAPAPAAAAAA0AAABTb3VyY2VBc3NldElkGwAAAAAAAAABUFJPUBMAAAARAAAAAAAAAPACAAAAAAQAAABUYWdzAQAAAABQUk9QIAAAAB4AAAAAAAAA8A8AAAAAFAAAAFZSVGlsdEFuZFJvbGxFbmFibGVkAgBQUk5UDgAAAA0AAAAAAAAA0AABAAAAAAAAAAAAAAFFTkQAAAAAAAkAAAAAAAAAPC9yb2Jsb3g+"
            }
        },
        200)
    return True


@server_path("/asset-permissions-api/v1/assets/check-permissions")
def _(self: web_server_handler) -> bool:
    self.send_json({"results": [{"value": {"status": "NoPermission"}}]}, 200)
    return True

@server_path('/guac-v2/v1/bundles/studio')
def _(self: web_server_handler) -> bool:
    self.send_json({})
    return True
