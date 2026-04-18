import gzip
import json
import os
import re
import shutil
import tempfile
import unittest
from types import SimpleNamespace

import assets
import storage
import util.const
import util.versions
import web_server._logic as web_logic
import web_server.endpoints.image as image_endpoints  # noqa: F401


TEST_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02L\x01\x00;"
)


class fake_server:
    def __init__(self, data_storage: storage.storager, game_config) -> None:
        self.storage = data_storage
        self.game_config = game_config


class fake_handler:
    def __init__(
        self,
        data_storage: storage.storager,
        game_config,
        *,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        query: dict[str, str | list[str]] | None = None,
        command: str = "GET",
        is_privileged: bool = True,
    ) -> None:
        self.server = fake_server(data_storage, game_config)
        self.game_config = game_config
        self._body = body
        self.headers = dict(headers or {})
        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = str(len(body))
        self.query_lists = {
            key: value if isinstance(value, list) else [value]
            for key, value in (query or {}).items()
        }
        self.query = {
            key: value[0]
            for key, value in self.query_lists.items()
        }
        self.command = command
        self.hostname = "https://localhost:2005"
        self.domain = "localhost"
        self.port_num = 2005
        self.is_privileged = is_privileged
        self.url_split = SimpleNamespace(query="")
        self.client_address = ("127.0.0.1", 12345)
        self.status_code: int | None = None
        self.response_headers: list[tuple[str, str]] = []
        self.json_body = None
        self.data_body: bytes | None = None
        self.error_args: tuple[int, str | None, str | None] | None = None

    def read_content(self) -> bytes:
        return self._body

    def send_response(self, status: int) -> None:
        self.status_code = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        self.status_code = code
        self.error_args = (code, message, explain)

    def send_json(
        self,
        json_data,
        status: int | None = 200,
        prefix: bytes = b"",
    ) -> None:
        assert isinstance(prefix, bytes)
        if status is not None:
            self.status_code = status
        self.json_body = json_data

    def send_data(
        self,
        text: bytes | str,
        status: int | None = 200,
        content_type: str | None = None,
    ) -> None:
        if isinstance(text, str):
            text = text.encode("utf-8")
        if status is not None:
            self.status_code = status
        if content_type is not None:
            self.response_headers.append(("Content-Type", content_type))
        self.data_body = text


class TestImageApi(unittest.TestCase):
    def make_storage_and_config(self) -> tuple[storage.storager, SimpleNamespace]:
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir, True)

        data_storage = storage.storager(
            os.path.join(temp_dir, "test.sqlite"),
            force_init=False,
        )
        asset_cache = assets.asseter(
            dir_path=os.path.join(temp_dir, "AssetCache"),
            redirect_func=lambda *_args, **_kwargs: None,
            asset_name_func=lambda asset_id: str(asset_id),
            clear_on_start=False,
        )
        asset_cache.add_asset(util.const.THUMBNAIL_ID_CONST, TEST_GIF)
        game_config = SimpleNamespace(
            asset_cache=asset_cache,
            game_setup=SimpleNamespace(
                roblox_version=util.versions.VERSION_MAP["v463"],
            ),
        )
        return data_storage, game_config

    @staticmethod
    def call_endpoint(
        path: str,
        handler: fake_handler,
        *,
        command: str = "GET",
    ) -> bool:
        handler.command = command
        for key, func in web_logic.SERVER_FUNCS.items():
            if key.command != command:
                continue
            if key.mode == web_logic.func_mode.STATIC and key.path == path:
                return func(handler)
            if key.mode == web_logic.func_mode.REGEX:
                match = re.fullmatch(key.path, path)
                if match is not None:
                    return func(handler, match)
        raise AssertionError(f"Endpoint not found: {command} {path}")

    def test_place_icon_upload_updates_db_and_cdn_serves_bytes(self) -> None:
        data_storage, game_config = self.make_storage_and_config()
        upload_handler = fake_handler(
            data_storage,
            game_config,
            body=TEST_GIF,
            headers={"Content-Type": "image/gif"},
            command="POST",
        )

        self.assertTrue(
            self.call_endpoint(
                "/rfd/image-upload/v1/places/310/icon",
                upload_handler,
                command="POST",
            ),
        )

        self.assertEqual(upload_handler.status_code, 201)
        assert upload_handler.json_body is not None
        content_hash = upload_handler.json_body["contentHash"]
        self.assertEqual(data_storage.placeicon.check(310)[0], content_hash)

        image_cache_root = image_endpoints._image_cache_root(upload_handler)
        self.assertTrue(os.path.isdir(image_cache_root))

        cdn_handler = fake_handler(
            data_storage,
            game_config,
            command="GET",
        )
        self.assertTrue(
            self.call_endpoint(
                f"/rfd/image-cdn/v1/{content_hash}",
                cdn_handler,
            ),
        )

        self.assertEqual(cdn_handler.status_code, 200)
        self.assertEqual(cdn_handler.data_body, TEST_GIF)
        self.assertIn(("Content-Type", "image/gif"), cdn_handler.response_headers)

    def test_games_icons_use_uploaded_place_icon_for_universe(self) -> None:
        data_storage, game_config = self.make_storage_and_config()
        data_storage.asset.update(
            force_asset_id=310,
            name="Pizza Place",
            description="A game",
            creator_id=1,
            creator_type=0,
            moderation_status=0,
        )
        data_storage.place.update(
            placeid=310,
            visitcount=123,
            is_public=True,
            parent_universe_id=None,
        )
        universe_id = data_storage.universe.update(
            root_place_id=310,
            creator_id=1,
            creator_type=0,
            is_public=True,
            moderation_status=0,
            visit_count=123,
        )
        assert universe_id is not None

        upload_handler = fake_handler(
            data_storage,
            game_config,
            body=TEST_GIF,
            headers={"Content-Type": "image/gif"},
            command="POST",
        )
        self.call_endpoint(
            "/rfd/image-upload/v1/places/310/icon",
            upload_handler,
            command="POST",
        )

        icons_handler = fake_handler(
            data_storage,
            game_config,
            query={"universeIds": str(universe_id), "size": "51x51"},
            command="GET",
        )
        self.assertTrue(
            self.call_endpoint("/v1/games/icons", icons_handler),
        )

        self.assertEqual(icons_handler.status_code, 200)
        assert icons_handler.json_body is not None
        self.assertEqual(icons_handler.json_body["data"][0]["targetId"], universe_id)
        self.assertIn("assetId=310", icons_handler.json_body["data"][0]["imageUrl"])
        self.assertIn("x=50", icons_handler.json_body["data"][0]["imageUrl"])
        self.assertIn("y=50", icons_handler.json_body["data"][0]["imageUrl"])

    def test_batch_image_request_handles_gzip_and_user_thumbnail(self) -> None:
        data_storage, game_config = self.make_storage_and_config()
        user_id = data_storage.user.update("Builder", "password123")
        data_storage.userthumbnail.update(
            userid=user_id,
            full_contenthash=None,
            headshot_contenthash=None,
            updated_at="2026-04-18T00:00:00+00:00",
        )

        upload_handler = fake_handler(
            data_storage,
            game_config,
            body=TEST_GIF,
            headers={"Content-Type": "image/gif"},
            command="POST",
        )
        self.call_endpoint(
            f"/rfd/image-upload/v1/users/{user_id}/thumbnail",
            upload_handler,
            command="POST",
        )

        batch_payload = json.dumps([
            {
                "requestId": f"type=AvatarHeadShot&id={user_id}&w=128&h=128&filters=",
                "targetId": user_id,
                "type": "AvatarHeadShot",
                "size": "127x129",
                "isCircular": False,
            },
        ]).encode("utf-8")
        batch_handler = fake_handler(
            data_storage,
            game_config,
            body=gzip.compress(batch_payload),
            headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
            command="POST",
        )

        self.assertTrue(
            self.call_endpoint("/v1/batch", batch_handler, command="POST"),
        )

        self.assertEqual(batch_handler.status_code, 200)
        assert batch_handler.json_body is not None
        self.assertEqual(len(batch_handler.json_body["data"]), 1)
        self.assertIn(
            f"/headshot-thumbnail/image?userId={user_id}&x=128&y=128",
            batch_handler.json_body["data"][0]["imageUrl"],
        )

    def test_avatar_thumbnail_json_route_uses_image_endpoint(self) -> None:
        data_storage, game_config = self.make_storage_and_config()
        user_id = data_storage.user.update("Painter", "password123")
        data_storage.userthumbnail.update(
            userid=user_id,
            full_contenthash="manual-hash",
            headshot_contenthash="manual-hash",
            updated_at="2026-04-18T00:00:00+00:00",
        )
        game_config.asset_cache.add_asset("manual-hash", TEST_GIF)

        handler = fake_handler(
            data_storage,
            game_config,
            query={"userId": str(user_id), "width": "49", "height": "49"},
            command="GET",
        )

        self.assertTrue(
            self.call_endpoint("/avatar-thumbnail/json", handler),
        )

        self.assertEqual(handler.status_code, 200)
        assert handler.json_body is not None
        self.assertTrue(handler.json_body["Final"])
        self.assertIn(
            f"/avatar-thumbnail/image?userId={user_id}&x=48&y=48",
            handler.json_body["Url"],
        )

    def test_game_icon_without_place_icon_uses_static_placeholder(self) -> None:
        data_storage, game_config = self.make_storage_and_config()
        data_storage.asset.update(
            force_asset_id=500,
            name="No Icon Game",
            description="Missing icon",
            creator_id=1,
            creator_type=0,
            moderation_status=0,
        )
        data_storage.place.update(
            placeid=500,
            is_public=True,
        )

        handler = fake_handler(
            data_storage,
            game_config,
            query={"assetId": "500", "x": "50", "y": "50"},
            command="GET",
        )

        self.assertTrue(
            self.call_endpoint("/Thumbs/GameIcon.ashx", handler),
        )

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(
            handler.data_body,
            image_endpoints._read_static_file(
                image_endpoints.GAME_ICON_PLACEHOLDER_REL_PATH,
            ),
        )
        self.assertNotEqual(handler.data_body, TEST_GIF)

    def test_headshot_without_generated_thumbnail_uses_static_placeholder(self) -> None:
        data_storage, game_config = self.make_storage_and_config()
        user_id = data_storage.user.update("NoHeadshotYet", "password123")

        handler = fake_handler(
            data_storage,
            game_config,
            query={"userId": str(user_id), "x": "48", "y": "48"},
            command="GET",
        )

        self.assertTrue(
            self.call_endpoint("/headshot-thumbnail/image", handler),
        )

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(
            handler.data_body,
            image_endpoints._read_static_file(
                image_endpoints.USER_HEADSHOT_PLACEHOLDER_REL_PATH,
            ),
        )
        self.assertNotEqual(handler.data_body, TEST_GIF)

    def test_thumbnail_asset_without_image_uses_banner_placeholder(self) -> None:
        data_storage, game_config = self.make_storage_and_config()
        handler = fake_handler(
            data_storage,
            game_config,
            query={"aid": "999", "fmt": "png", "wd": "768", "ht": "432"},
            command="GET",
        )

        self.assertTrue(
            self.call_endpoint("/Game/Tools/ThumbnailAsset.ashx", handler),
        )

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(
            handler.data_body,
            image_endpoints._read_static_file(
                image_endpoints.GAME_BANNER_PLACEHOLDER_REL_PATH,
            ),
        )
        self.assertNotEqual(handler.data_body, TEST_GIF)
