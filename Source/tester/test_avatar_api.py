import json
import os
import re
import shutil
import tempfile
import unittest
from types import SimpleNamespace

from enums.AssetType import AssetType
from enums.PlaceRigChoice import PlaceRigChoice
import storage
import util.auth
import util.versions
import web_server._logic as web_logic
import web_server.endpoints.avatar  # noqa: F401


class fake_server:
    def __init__(self, data_storage: storage.storager, game_config) -> None:
        self.storage = data_storage
        self.game_config = game_config


class fake_handler:
    def __init__(
        self,
        data_storage: storage.storager,
        *,
        body: bytes = b"",
        cookie_header: str | None = None,
        query: dict[str, str] | None = None,
        command: str = "GET",
        game_config=None,
    ) -> None:
        if game_config is None:
            game_config = SimpleNamespace(
                game_setup=SimpleNamespace(
                    roblox_version=util.versions.VERSION_MAP["v535"],
                ),
            )
        self.server = fake_server(data_storage, game_config)
        self.game_config = game_config
        self._body = body
        self.command = command
        self.headers: dict[str, str] = {}
        if cookie_header is not None:
            self.headers["Cookie"] = cookie_header
        self.client_address = ("127.0.0.1", 12345)
        self.domain = "avatar.rbolock.tk"
        self.hostname = "https://avatar.rbolock.tk"
        self.port_num = 443
        raw_query = query or {}
        self.query_lists = {key: [value] for key, value in raw_query.items()}
        self.query = dict(raw_query)
        self.url_split = SimpleNamespace(query="")
        self.response_headers: list[tuple[str, str]] = []
        self.status_code: int | None = None
        self.json_body = None
        self.data_body: bytes | None = None

    def read_content(self) -> bytes:
        return self._body

    def send_response(self, status: int) -> None:
        self.status_code = status

    def send_header(self, key: str, value: str) -> None:
        self.response_headers.append((key, value))

    def end_headers(self) -> None:
        return

    def send_error(self, status: int) -> None:
        self.status_code = status

    def send_json(self, json_data, status: int | None = 200, prefix: bytes = b"") -> None:
        del prefix
        if status is not None:
            self.status_code = status
        self.json_body = json_data

    def send_data(
        self,
        text: bytes | str,
        status: int | None = 200,
        content_type: str | None = None,
    ) -> None:
        del content_type
        if isinstance(text, str):
            text = text.encode("utf-8")
        if status is not None:
            self.status_code = status
        self.data_body = text


class TestAvatarApi(unittest.TestCase):
    def make_storage(self) -> storage.storager:
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir, True)
        return storage.storager(
            os.path.join(temp_dir, "test.sqlite"),
            force_init=False,
        )

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

    @staticmethod
    def make_authenticated_handler(
        data_storage: storage.storager,
        user_id: int,
        *,
        body: bytes = b"",
        query: dict[str, str] | None = None,
        command: str = "GET",
    ) -> fake_handler:
        token = util.auth.CreateToken(data_storage, user_id, "127.0.0.1")
        return fake_handler(
            data_storage,
            body=body,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={token}",
            query=query,
            command=command,
        )

    def test_v1_avatar_returns_sqlite_backed_avatar_payload(self) -> None:
        data_storage = self.make_storage()
        user = util.auth.CreateUser(data_storage, "AvatarOwner", "secret123")
        self.assertIsNotNone(user)
        assert user is not None

        data_storage.user_avatar.update(
            user.id,
            head_color_id=1003,
            torso_color_id=1030,
            right_arm_color_id=1030,
            left_arm_color_id=1030,
            right_leg_color_id=1030,
            left_leg_color_id=1030,
            r15=True,
            height_scale=1.05,
            width_scale=0.7,
            head_scale=1.0,
            depth_scale=0.85,
            proportion_scale=0.0,
            body_type_scale=0.0,
        )

        data_storage.asset.update(
            force_asset_id=7001,
            name="Cool Shirt",
            asset_type=AssetType.Shirt,
            creator_id=user.id,
            creator_type=0,
            moderation_status=0,
        )
        data_storage.asset.update(
            force_asset_id=7002,
            name="Cartoony Run",
            asset_type=AssetType.RunAnimation,
            creator_id=user.id,
            creator_type=0,
            moderation_status=0,
        )
        data_storage.user_asset.update(user.id, 7001)
        data_storage.user_asset.update(user.id, 7002)
        data_storage.user_avatar_asset.update(user.id, 7001)
        data_storage.user_avatar_asset.update(user.id, 7002)

        handler = self.make_authenticated_handler(data_storage, user.id)
        self.assertTrue(self.call_endpoint("/v1/avatar", handler, command="GET"))

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.json_body["playerAvatarType"], "R15")
        self.assertEqual(handler.json_body["scales"]["depth"], 0.85)
        self.assertEqual(handler.json_body["bodyColors"]["headColorId"], 1003)
        self.assertEqual([item["id"] for item in handler.json_body["assets"]], [7001, 7002])
        self.assertFalse(handler.json_body["defaultShirtApplied"])
        self.assertTrue(handler.json_body["defaultPantsApplied"])
        self.assertEqual(len(handler.json_body["emotes"]), 8)

    def test_v2_avatar_avatar_returns_body_color3s(self) -> None:
        data_storage = self.make_storage()
        user = util.auth.CreateUser(data_storage, "AvatarOwner", "secret123")
        self.assertIsNotNone(user)
        assert user is not None

        data_storage.user_avatar.update(
            user.id,
            head_color_id=1003,
            torso_color_id=1030,
            right_arm_color_id=1030,
            left_arm_color_id=1030,
            right_leg_color_id=1001,
            left_leg_color_id=1002,
            r15=True,
        )

        handler = self.make_authenticated_handler(data_storage, user.id)
        self.assertTrue(self.call_endpoint("/v2/avatar/avatar", handler, command="GET"))

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.json_body["bodyColor3s"]["headColor3"], "111111")
        self.assertEqual(handler.json_body["bodyColor3s"]["torsoColor3"], "FFCC99")
        self.assertEqual(handler.json_body["bodyColor3s"]["rightLegColor3"], "F8F8F8")
        self.assertNotIn("bodyColors", handler.json_body)

    def test_set_wearing_assets_uses_owned_assets_and_marks_invalid(self) -> None:
        data_storage = self.make_storage()
        user = util.auth.CreateUser(data_storage, "AvatarOwner", "secret123")
        self.assertIsNotNone(user)
        assert user is not None

        data_storage.asset.update(
            force_asset_id=7101,
            name="Owned Hat",
            asset_type=AssetType.Hat,
            creator_id=user.id,
            creator_type=0,
            moderation_status=0,
        )
        data_storage.asset.update(
            force_asset_id=7102,
            name="Unowned Hat",
            asset_type=AssetType.Hat,
            creator_id=user.id,
            creator_type=0,
            moderation_status=0,
        )
        data_storage.asset.update(
            force_asset_id=7103,
            name="Moderated Hat",
            asset_type=AssetType.Hat,
            creator_id=user.id,
            creator_type=0,
            moderation_status=1,
        )
        data_storage.user_asset.update(user.id, 7101)
        data_storage.user_asset.update(user.id, 7103)

        handler = self.make_authenticated_handler(
            data_storage,
            user.id,
            body=json.dumps({"assetIds": [7101, 7102, 7103]}).encode("utf-8"),
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint("/v1/avatar/set-wearing-assets", handler, command="POST"),
        )

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.json_body["success"], True)
        self.assertEqual(handler.json_body["invalidAssetIds"], [7102, 7103])
        self.assertEqual(
            data_storage.user_avatar_asset.list_asset_ids_for_user(user.id),
            [7101],
        )
        thumbnail_row = data_storage.userthumbnail.check(user.id)
        self.assertIsNotNone(thumbnail_row)
        assert thumbnail_row is not None
        self.assertIsNotNone(thumbnail_row[2])

    def test_v1_avatar_query_mode_returns_fetch_payload_with_place_override(self) -> None:
        data_storage = self.make_storage()
        user = util.auth.CreateUser(data_storage, "AvatarOwner", "secret123")
        self.assertIsNotNone(user)
        assert user is not None

        data_storage.user_avatar.update(user.id, r15=True, head_color_id=1003)
        data_storage.asset.update(
            force_asset_id=7201,
            name="Avatar Hat",
            asset_type=AssetType.Hat,
            creator_id=user.id,
            creator_type=0,
            moderation_status=0,
        )
        data_storage.user_asset.update(user.id, 7201)
        data_storage.user_avatar_asset.update(user.id, 7201)
        data_storage.place.update(placeid=9001, rig_choice=PlaceRigChoice.ForceR6)

        handler = fake_handler(
            data_storage,
            query={"userId": str(user.id), "placeId": "9001"},
            command="GET",
        )
        self.assertTrue(self.call_endpoint("/v1/avatar", handler, command="GET"))

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.json_body["resolvedAvatarType"], "R6")
        self.assertEqual(handler.json_body["assetAndAssetTypeIds"][0]["assetId"], 7201)
        self.assertEqual(handler.json_body["assetAndAssetTypeIds"][0]["assetTypeId"], 8)
        self.assertEqual(handler.json_body["bodyColors"]["HeadColor"], 1003)
        self.assertEqual(handler.json_body["bodyColors"]["headColorId"], 1003)
