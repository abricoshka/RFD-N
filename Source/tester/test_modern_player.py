import io
import json
import re
import unittest
from types import SimpleNamespace
from unittest import mock

from enums.AssetType import AssetType
import logger
import storage
import util.auth
import util.const
import util.versions
import web_server.endpoints  # noqa: F401
from routines.studio_server import obj_type as studio_server_obj
from web_server._logic import SERVER_FUNCS, func_mode


class fake_server:
    def __init__(self, data_storage: storage.storager, game_config) -> None:
        self.storage = data_storage
        self.game_config = game_config


class fake_handler:
    def __init__(
        self,
        data_storage: storage.storager,
        *,
        path: str = '/',
        command: str = 'GET',
        body: bytes = b'',
        query: dict[str, str] | None = None,
        cookie_header: str | None = None,
        game_config=None,
        domain: str = 'gamejoin.rbolock.tk',
    ) -> None:
        self.server = fake_server(data_storage, game_config)
        self.game_config = game_config
        self.command = command
        self._body = body
        self.query = query or {}
        self.query_lists = {
            key: [value]
            for key, value in self.query.items()
        }
        self.headers: dict[str, str] = {}
        if cookie_header is not None:
            self.headers['Cookie'] = cookie_header
        self.client_address = ('127.0.0.1', 12345)
        self.domain = domain
        self.port_num = 2005
        self.hostname = f'https://{domain}'
        self.path = path
        self.url_split = SimpleNamespace(query='')
        self.status_code: int | None = None
        self.response_headers: list[tuple[str, str]] = []
        self.json_body = None
        self.data_body: bytes | None = None
        self.raw_written = io.BytesIO()
        self.wfile = SimpleNamespace(
            write=self.raw_written.write,
            flush=lambda: None,
        )

    def read_content(self) -> bytes:
        return self._body

    def send_response(self, status: int) -> None:
        self.status_code = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return

    def send_json(
        self,
        json_data,
        status: int | None = 200,
        prefix: bytes = b'',
    ) -> None:
        body = prefix + json.dumps(json_data).encode('utf-8')
        self.json_body = json_data
        self.data_body = body
        if status is not None:
            self.status_code = status

    def send_data(
        self,
        text: bytes | str,
        status: int | None = 200,
        content_type: str | None = None,
    ) -> None:
        if isinstance(text, str):
            text = text.encode('utf-8')
        if status is not None:
            self.status_code = status
        if content_type is not None:
            self.response_headers.append(('Content-Type', content_type))
        self.data_body = text


class TestModernPlayer(unittest.TestCase):
    def make_storage(self) -> storage.storager:
        return storage.storager(':memory:', force_init=False)

    def make_game_config(
        self,
        data_storage: storage.storager,
    ):
        return SimpleNamespace(
            storage=data_storage,
            game_setup=SimpleNamespace(
                roblox_version=util.versions.VERSION_MAP['v712'],
            ),
            server_core=SimpleNamespace(
                chat_style=SimpleNamespace(value='Classic'),
                retrieve_default_funds=lambda *_args: 0,
                retrieve_account_age=lambda *_args: 0,
                retrieve_membership_type=lambda *_args: 'None',
                check_user_allowed=SimpleNamespace(
                    cached_call=lambda *_args: True,
                ),
            ),
        )

    @staticmethod
    def call_endpoint(
        path: str,
        handler: fake_handler,
        *,
        command: str = 'GET',
    ) -> bool:
        for key, func in SERVER_FUNCS.items():
            if key.command != command:
                continue
            if key.version != handler.game_config.game_setup.roblox_version:
                continue
            if key.mode == func_mode.STATIC and key.path == path:
                return func(handler)
            if key.mode == func_mode.REGEX:
                match = re.fullmatch(key.path, path)
                if match is not None:
                    return func(handler, match)
        raise AssertionError(f'Endpoint not found: {command} {path}')

    @staticmethod
    def read_raw_json(handler: fake_handler):
        return json.loads(handler.raw_written.getvalue().decode('utf-8'))

    def seed_place_context(
        self,
        data_storage: storage.storager,
        *,
        place_id: int = util.const.PLACE_IDEN_CONST,
        creator_id: int = 998796,
    ) -> int:
        data_storage.user.update(
            username='Templates',
            password='!',
            force_user_id=creator_id,
        )
        data_storage.asset.update(
            force_asset_id=place_id,
            roblox_asset_id=place_id,
            name='Classic Dodge The Teapots of Doom!',
            description='SQLite-backed place',
            asset_type=AssetType.Place,
            creator_type=0,
            creator_id=creator_id,
            moderation_status=0,
            is_for_sale=False,
        )
        universe_id = data_storage.universe.update(
            root_place_id=place_id,
            creator_id=creator_id,
            creator_type=0,
            created_at='2026-04-21T00:00:00+00:00',
            updated_at='2026-04-21T00:00:00+00:00',
            place_year=2020,
            is_public=True,
            moderation_status=0,
        )
        assert universe_id is not None
        data_storage.place.update(
            placeid=place_id,
            is_public=True,
            maxplayers=20,
            placeyear=2020,
            parent_universe_id=universe_id,
        )
        return universe_id

    def test_studio_server_cmd_args_use_sqlite_place_universe_and_port(self) -> None:
        data_storage = self.make_storage()
        universe_id = self.seed_place_context(data_storage)
        game_config = self.make_game_config(data_storage)
        entry = studio_server_obj(
            game_config=game_config,
            logger=logger.PRINT_QUIET,
            rcc_port=2005,
        )

        cmd_args = entry.gen_cmd_args()
        self.assertEqual(cmd_args[cmd_args.index('-placeId') + 1], str(util.const.PLACE_IDEN_CONST))
        self.assertEqual(cmd_args[cmd_args.index('-universeId') + 1], str(universe_id))
        self.assertEqual(cmd_args[cmd_args.index('-creatorId') + 1], '998796')
        self.assertEqual(cmd_args[cmd_args.index('-port') + 1], '2005')

    def test_v1_join_game_uses_sqlite_universe_creator_and_requested_job_id(self) -> None:
        data_storage = self.make_storage()
        universe_id = self.seed_place_context(data_storage)
        user = util.auth.CreateUser(data_storage, 'join_user', 'secret123')
        assert user is not None
        token = util.auth.CreateToken(data_storage, user.id, '127.0.0.1')
        game_config = self.make_game_config(data_storage)
        handler = fake_handler(
            data_storage,
            path='/v1/join-game',
            command='POST',
            body=json.dumps({
                'placeId': util.const.PLACE_IDEN_CONST,
                'gameId': 'job-from-client',
                'browserTrackerId': 12345,
            }).encode('utf-8'),
            game_config=game_config,
            domain='gamejoin.rbolock.tk',
        )
        handler.headers['X-Roblosecurity'] = token

        self.assertTrue(self.call_endpoint('/v1/join-game', handler, command='POST'))
        payload = self.read_raw_json(handler)

        self.assertEqual(payload['jobId'], 'job-from-client')
        self.assertEqual(payload['joinScript']['UniverseId'], universe_id)
        self.assertEqual(payload['joinScript']['CreatorId'], 998796)
        self.assertEqual(payload['joinScript']['CreatorTypeEnum'], 'User')
        self.assertEqual(payload['joinScript']['PlaceId'], util.const.PLACE_IDEN_CONST)
        self.assertEqual(payload['joinScript']['BrowserTrackerId'], 12345)
        self.assertEqual(payload['joinScript']['ServerPort'], 2005)
        self.assertEqual(payload['joinScript']['MachineAddress'], '127.0.0.1')
        self.assertEqual(payload['authenticationTicket'], payload['joinScript']['ClientTicket'])
        self.assertRegex(payload['joinScript']['ClientTicket'], r'^[0-9a-f]{40}$')
        self.assertNotIn('DirectServerReturn', payload['joinScript'])
        self.assertNotIn('UdmuxEndpoints', payload['joinScript'])
        self.assertNotIn('TokenValue', payload['joinScript'])

    def test_place_universe_lookup_returns_sqlite_universe(self) -> None:
        data_storage = self.make_storage()
        universe_id = self.seed_place_context(data_storage)
        handler = fake_handler(
            data_storage,
            game_config=self.make_game_config(data_storage),
            path=f'/universes/v1/places/{util.const.PLACE_IDEN_CONST}/universe',
        )

        self.assertTrue(
            self.call_endpoint(
                f'/universes/v1/places/{util.const.PLACE_IDEN_CONST}/universe',
                handler,
            ),
        )
        self.assertEqual(handler.json_body, {'universeId': universe_id})

    def test_player_shell_endpoints_return_non_404_payloads(self) -> None:
        data_storage = self.make_storage()
        user = util.auth.CreateUser(data_storage, 'shell_user', 'secret123')
        assert user is not None
        token = util.auth.CreateToken(data_storage, user.id, '127.0.0.1')
        game_config = self.make_game_config(data_storage)

        hydration_handler = fake_handler(
            data_storage,
            game_config=game_config,
        )
        hydration_handler.headers['X-Roblosecurity'] = token
        self.assertTrue(
            self.call_endpoint(
                '/player-hydration-service/v1/players/signed',
                hydration_handler,
            ),
        )
        self.assertEqual(hydration_handler.json_body['signedUser']['id'], user.id)

        roles_handler = fake_handler(
            data_storage,
            game_config=game_config,
        )
        roles_handler.headers['X-Roblosecurity'] = token
        self.assertTrue(
            self.call_endpoint('/v1/users/authenticated/roles', roles_handler),
        )
        self.assertEqual(roles_handler.json_body, {'roles': []})

        theme_handler = fake_handler(
            data_storage,
            game_config=game_config,
            path='/v1/themes/User/1',
            domain='accountsettings.rbolock.tk',
        )
        self.assertTrue(self.call_endpoint('/v1/themes/User/1', theme_handler))
        self.assertEqual(theme_handler.json_body, {'themeType': 'Dark'})

        user_channel_handler = fake_handler(
            data_storage,
            game_config=game_config,
            path='/v2/user-channel',
            query={'binaryType': 'WindowsPlayer'},
            domain='clientsettings.rbolock.tk',
        )
        self.assertTrue(self.call_endpoint('/v2/user-channel', user_channel_handler))
        self.assertEqual(user_channel_handler.json_body, {'channelName': 'production'})

        unread_handler = fake_handler(
            data_storage,
            game_config=game_config,
            path='/v1/messages/unread/count',
            domain='privatemessages.rbolock.tk',
        )
        self.assertTrue(
            self.call_endpoint('/v1/messages/unread/count', unread_handler),
        )
        self.assertEqual(unread_handler.json_body, {'count': 0})

        notifications_handler = fake_handler(
            data_storage,
            game_config=game_config,
            path='/v2/stream-notifications/unread-count',
            domain='notifications.rbolock.tk',
        )
        self.assertTrue(
            self.call_endpoint(
                '/v2/stream-notifications/unread-count',
                notifications_handler,
            ),
        )
        self.assertEqual(
            notifications_handler.json_body,
            {'unreadCount': 0},
        )

        localization_handler = fake_handler(
            data_storage,
            game_config=game_config,
            path='/v1/user-localization-settings/player-choice/1',
            domain='gameinternationalization.rbolock.tk',
        )
        self.assertTrue(
            self.call_endpoint(
                '/v1/user-localization-settings/player-choice/1',
                localization_handler,
            ),
        )
        self.assertEqual(
            localization_handler.json_body,
            {
                'supportedLocaleCode': 'en_us',
                'localeCode': 'en_us',
                'source': 'PlayerChoice',
            },
        )

    def test_userhub_websocket_upgrade_returns_switching_protocols(self) -> None:
        data_storage = self.make_storage()
        game_config = self.make_game_config(data_storage)
        handler = fake_handler(
            data_storage,
            game_config=game_config,
            path='/userhub/',
            domain='realtime-signalr.rbolock.tk',
        )
        handler.headers['Upgrade'] = 'websocket'
        handler.headers['Sec-WebSocket-Key'] = 'test-key'

        self.assertTrue(
            self.call_endpoint('/userhub/', handler),
        )
        self.assertEqual(handler.status_code, 101)
        self.assertIn(('Upgrade', 'websocket'), handler.response_headers)
        self.assertIn(('Connection', 'Upgrade'), handler.response_headers)
