# Standard library imports
import re
import json
import copy
import os
import pyzstd

# Local application imports
import assets.returns as returns
import util.const
import util.resource
from web_server._logic import web_server_handler, server_path, web_server_ssl
import web_server.settings_files
import util.versions as versions


CLIENT_SETTINGS_OVERRIDES = {
    # Keep these diagnostics enabled while local_rcc is being brought up on
    # 2026 clients. Without this, ScriptContext often logs only script names.
    "DFFlagNoOutputFromLuau": "False",
    "DFFlagAppendSourceIdToRequireLog": "True",
    "FFlagEnableCoreScriptBacktraceReporting": "True",
    "DFIntReportLocalPlayerMissingStackTraceUserIdPercentage": "100",
    "FLogScriptContext": "6",
    "FLogCoreScripts": "6",
    "FLogScriptPrint": "6",
}


def with_client_settings_overrides(payload: dict) -> dict:
    result = copy.deepcopy(payload)
    settings = result.setdefault('applicationSettings', {})
    settings.update(CLIENT_SETTINGS_OVERRIDES)
    return result


def get_player_settings_dictionary_path(
    self: web_server_handler,
    dictionary_hash: str,
) -> str:
    return util.resource.retr_rōblox_full_path(
        self.game_config.game_setup.roblox_version,
        util.resource.bin_subtype.PLAYER,
        'PlatformContent',
        'pc',
        'shared_compression_dictionaries',
        f'{dictionary_hash}.dict',
    )

@server_path('/rfd/default-user-code')
def _(self: web_server_handler) -> bool:
    result = self.game_config.server_core.retrieve_default_user_code()
    self.send_data(bytes(result, encoding='utf-8'))
    return True


@server_path('/rfd/is-player-allowed')
def _(self: web_server_handler) -> bool:
    database = self.server.storage.players

    id_num = int(self.query['userId'])
    user_code = database.get_player_field_from_index(
        database.player_field.IDEN_NUM,
        id_num,
        database.player_field.USERCODE,
    )

    if user_code is None:
        self.send_data(b'false')
        return True

    # This function was also called during join-data creation.
    # It's called a second time here (potentially) for additional protection.
    if self.game_config.server_core.check_user_allowed.cached_call(
        7, user_code,
        user_code,
    ):
        self.send_data(b'true')
        return True

    self.send_data(b'false')
    return True


@server_path('/rfd/roblox-version')
def _(self: web_server_handler) -> bool:
    '''
    Used by clients to automatically detect which version to run.
    '''
    version = self.game_config.game_setup.roblox_version
    self.send_data(bytes(version.name, encoding='utf-8'))
    return True

@server_path('/rfd/set-proxy-target')
def _(self: web_server_handler) -> bool:
    '''
    Called by the player routine before launching the Roblox client.
    Updates the rbolock.tk reverse proxy target so the client's HTTPS
    traffic is forwarded to the correct remote server IP.
    Has no effect when the proxy is not running (non-rblxhub-cert mode).

    https://github.com/mytailcaughtonfire/RFD-2022/blob/52c5e3f25e3f48c290002b6ae7c01e272eb969cd/Source/web_server/endpoints/setup_player.py#L125
    '''
    host = self.query.get('host', '127.0.0.1')
    port = int(self.query.get('port', str(util.const.RFD_DEFAULT_PORT)))
    proxy = getattr(self.server, 'proxy', None)
    if proxy is not None:
        proxy.set_target(host, port)
    self.send_data(b'ok')
    return True

@server_path("/validate-machine")
@server_path('/game/validate-machine')
def _(self: web_server_handler) -> bool:
    self.send_json({"success": True})
    return True


@server_path('/Setting/QuietGet/StudioAppSettings/')
@server_path('/Setting/QuietGet/ClientAppSettings/')
def _(self: web_server_handler) -> bool:
    self.send_json(CLIENT_SETTINGS_OVERRIDES)
    return True


@server_path('/avatar-thumbnail/json')
def _(self: web_server_handler) -> bool:
    '''
    To simplify the server program, let not there be avatar thumbnail storage.
    '''
    self.send_json({})
    return True


@server_path('/avatar-thumbnail/image')
def _(self: web_server_handler) -> bool:
    '''
    To simplify the server program, let there not be avatar thumbnail images.
    '''
    return True


@server_path('/asset-thumbnail/json')
def _(self: web_server_handler) -> bool:
    '''
    TODO: properly deflect thumbnail generation.
    '''
    self.send_json({
        'Url': f'{self.hostname}/Thumbs/GameIcon.ashx',
        'Final': True,
        'SubstitutionType': 0,
    })
    return True

@server_path('/v1/settings/application')
def _(self: web_server_handler) -> bool:
    if self.query.get('applicationName') == 'AndroidApp':
        self.send_json(
            web_server.settings_files.read_settings_json('android_fflags.json'),
        )
    else:
        self.send_json({'applicationSettings': {}})

    return True

@server_path('/v2/settings/application/PCStudioApp', versions={versions.rōblox.v574})
def _(self: web_server_handler) -> bool:
    self.send_json(
        with_client_settings_overrides(
            web_server.settings_files.read_settings_json(
                'windows_2023_fflags.json',
            ),
        ),
    )
    return True

@server_path(
    '/v2/settings/application/PCStudioApp',
    versions=set(versions.VERSION_MAP.values()) - {versions.VERSION_MAP['v574']},
)
def _(self: web_server_handler) -> bool:
    self.send_json(
        with_client_settings_overrides(
            web_server.settings_files.read_settings_json(
                'windows_2026_fflags.json',
            ),
        ),
    )
    return True


@server_path('/v2/settings-compressed/application/PCDesktopClient.zst')
def _(self: web_server_handler) -> bool:
    self.send_json(
        with_client_settings_overrides(
            web_server.settings_files.read_settings_json(
                'PCDesktopClient.zst',
            ),
        ),
    )
    return True

@server_path('/v2/settings/application/PCDesktopClient')
def _(self: web_server_handler) -> bool:
    self.send_json(
        with_client_settings_overrides(
            web_server.settings_files.read_settings_json(
                'PCDesktopClient.json',
            ),
        ),
    )
    return True

@server_path(
    r'/v2/settings-compressed/application/PCDesktopClient/([0-9a-fA-F]{64})\.dcz',
    regex=True,
    commands={'GET'},
)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    _file_path, payload = web_server.settings_files.read_matching_settings_bytes(
        '*.dcz',
    )
    dictionary_hash = match.group(1)
    dictionary_path = get_player_settings_dictionary_path(
        self,
        dictionary_hash,
    )
    if os.path.isfile(dictionary_path):
        with open(dictionary_path, 'rb') as dictionary_file:
            dictionary_data = dictionary_file.read()
        zstd_dict = pyzstd.ZstdDict(
            dictionary_data,
            is_raw=True,
        )
        decoded = pyzstd.decompress(payload, zstd_dict)
        settings = with_client_settings_overrides(
            json.loads(decoded.decode('utf-8')),
        )
        payload = pyzstd.compress(
            json.dumps(settings, separators=(',', ':')).encode('utf-8'),
            zstd_dict=zstd_dict,
        )

    self.send_data(
        payload,
        content_type='application/octet-stream',
    )
    return True


@server_path('/v2/client-version/WindowsStudio64')
@server_path('/v2/client-version/WindowsPlayer')
def _(self: web_server_handler) -> bool:
    self.send_json({
        "version": "0.712.0.7120919",
        "clientVersionUpload": "version-8764cc9c84a5459a",
        "bootstrapperVersion": "0.712.0.7120919",
        "nextClientVersionUpload": None,
        "nextClientVersion": None
    }, 200)


@server_path('/v1/player-policies-client')
def _(self: web_server_handler) -> bool:
    self.send_json({
        'isSubjectToChinaPolicies': False,
        'arePaidRandomItemsRestricted': False,
        'isPaidItemTradingAllowed': True,
        'areAdsAllowed': True,
    })
    return True


# Stubs
@server_path('/v1/agreements-resolution/Web')
@server_path('/user-agreements/v1/agreements-resolution/Web')
@server_path('/v2/ota-version/WindowsPlayer')
def _(self: web_server_handler) -> bool:
    self.send_json([])
    return True


@server_path('/v2/user-channel', commands={'GET'})
def _(self: web_server_handler) -> bool:
    self.send_json({
        "channelName": "production",
    })
    return True


@server_path(r'/users/(\d+)/canmanage/([\d]+)', regex=True)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    database = self.server.storage.players

    id_num = int(match.group(1))
    user_code = database.get_player_field_from_index(
        database.player_field.IDEN_NUM,
        id_num,
        database.player_field.USERCODE,
    )

    if user_code is None:
        result = False
    else:
        result = self.game_config.server_core.check_user_has_admin.cached_call(
            7, user_code,
            id_num, user_code,
        )

    self.send_json({"Success": True, "CanManage": result})
    return True


@server_path(r'/v1/user/(\d+)/is-admin-developer-console-enabled', regex=True)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    database = self.server.storage.players

    id_num = int(match.group(1))
    user_code = database.get_player_field_from_index(
        database.player_field.IDEN_NUM,
        id_num,
        database.player_field.USERCODE,
    )

    if user_code is None:
        result = False
    else:
        result = self.game_config.server_core.check_user_has_admin.cached_call(
            7, user_code,
            id_num, user_code,
        )

    self.send_json({"isAdminDeveloperConsoleEnabled": result})
    return True


@server_path("/v1/locales/user-localization-locus-supported-locales")
def _(self: web_server_handler) -> bool:
    self.send_json({"signupAndLogin": {"id": 1, "locale": "en_us", "name": "English (United States)",
                                       "nativeName": "English (United States)",
                                       "language": {"id": 41, "name": "English", "nativeName": "English",
                                                    "languageCode": "en", "isRightToLeft": False}},
                    "generalExperience": {"id": 1, "locale": "en_us", "name": "English (United States)",
                                          "nativeName": "English (United States)",
                                          "language": {"id": 41, "name": "English", "nativeName": "English",
                                                       "languageCode": "en", "isRightToLeft": False}},
                    "ugc": {"id": 1, "locale": "en_us", "name": "English (United States)",
                            "nativeName": "English (United States)",
                            "language": {"id": 41, "name": "English", "nativeName": "English", "languageCode": "en",
                                         "isRightToLeft": False}}, "showRobloxTranslations": False})
    return True
