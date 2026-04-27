import json
import os
import re
import shutil
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace

import storage
import util.auth
import web_server._logic as web_logic
import web_server.endpoints.player_info  # noqa: F401
import web_server.endpoints.friend_api  # noqa: F401


class fake_server:
    def __init__(self, data_storage: storage.storager) -> None:
        self.storage = data_storage
        self.game_config = None


class fake_handler:
    def __init__(
        self,
        data_storage: storage.storager,
        *,
        body: bytes = b"",
        cookie_header: str | None = None,
        command: str = "GET",
    ) -> None:
        self.server = fake_server(data_storage)
        self._body = body
        self.command = command
        self.headers: dict[str, str] = {}
        if cookie_header is not None:
            self.headers["Cookie"] = cookie_header
        self.client_address = ("127.0.0.1", 12345)
        self.domain = "friends.rbolock.tk"
        self.hostname = "https://friends.rbolock.tk"
        self.port_num = 443
        self.query_lists: dict[str, list[str]] = {}
        self.query: dict[str, str] = {}
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

    def send_json(
        self,
        json_data,
        status: int | None = 200,
        prefix: bytes = b"",
    ) -> None:
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


class TestFriendApi(unittest.TestCase):
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
        command: str,
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
        username: str,
        *,
        body: bytes = b"",
        command: str = "GET",
    ) -> tuple[object, fake_handler]:
        user = util.auth.CreateUser(data_storage, username, "secret123")
        assert user is not None
        token = util.auth.CreateToken(data_storage, user.id, "127.0.0.1")
        return (
            user,
            fake_handler(
                data_storage,
                body=body,
                cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={token}",
                command=command,
            ),
        )

    def test_request_accept_and_friends_list_flow(self) -> None:
        data_storage = self.make_storage()
        alice = util.auth.CreateUser(data_storage, "Alice", "secret123")
        bob = util.auth.CreateUser(data_storage, "Bob", "secret123")
        self.assertIsNotNone(alice)
        self.assertIsNotNone(bob)
        assert alice is not None
        assert bob is not None

        alice_token = util.auth.CreateToken(data_storage, alice.id, "127.0.0.1")
        request_handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={alice_token}",
            command="POST",
        )

        self.assertTrue(
            self.call_endpoint(
                f"/v1/users/{bob.id}/request-friendship",
                request_handler,
                command="POST",
            ),
        )
        self.assertEqual(request_handler.status_code, 200)
        self.assertEqual(request_handler.json_body, {"success": True})
        self.assertTrue(data_storage.friend.has_pending_request(alice.id, bob.id))

        bob_token = util.auth.CreateToken(data_storage, bob.id, "127.0.0.1")
        count_handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={bob_token}",
            command="GET",
        )
        self.assertTrue(
            self.call_endpoint("/v1/user/friend-requests/count", count_handler, command="GET"),
        )
        self.assertEqual(count_handler.json_body, {"count": 1})

        accept_handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={bob_token}",
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint(
                f"/v1/users/{alice.id}/accept-friend-request",
                accept_handler,
                command="POST",
            ),
        )
        self.assertEqual(accept_handler.status_code, 200)
        self.assertEqual(accept_handler.json_body, {})
        self.assertTrue(data_storage.friend.has_friendship(alice.id, bob.id))

        friends_handler = fake_handler(data_storage, command="GET")
        self.assertTrue(
            self.call_endpoint(f"/v1/users/{alice.id}/friends", friends_handler, command="GET"),
        )
        self.assertEqual(friends_handler.status_code, 200)
        self.assertEqual(len(friends_handler.json_body["data"]), 1)
        self.assertEqual(friends_handler.json_body["data"][0]["id"], bob.id)
        self.assertEqual(friends_handler.json_body["data"][0]["name"], "Bob")

        friends_count_handler = fake_handler(data_storage, command="GET")
        self.assertTrue(
            self.call_endpoint(
                f"/v1/users/{alice.id}/friends/count",
                friends_count_handler,
                command="GET",
            ),
        )
        self.assertEqual(friends_count_handler.json_body, {"count": 1})

    def test_reciprocal_request_auto_accepts(self) -> None:
        data_storage = self.make_storage()
        alice = util.auth.CreateUser(data_storage, "Alice", "secret123")
        bob = util.auth.CreateUser(data_storage, "Bob", "secret123")
        self.assertIsNotNone(alice)
        self.assertIsNotNone(bob)
        assert alice is not None
        assert bob is not None

        data_storage.friend.create_request(alice.id, bob.id)

        bob_token = util.auth.CreateToken(data_storage, bob.id, "127.0.0.1")
        handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={bob_token}",
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint(
                f"/v1/users/{alice.id}/request-friendship",
                handler,
                command="POST",
            ),
        )

        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.json_body, {"success": True})
        self.assertTrue(data_storage.friend.has_friendship(alice.id, bob.id))
        self.assertFalse(data_storage.friend.has_pending_request(alice.id, bob.id))
        self.assertFalse(data_storage.friend.has_pending_request(bob.id, alice.id))

    def test_decline_all_and_unfriend(self) -> None:
        data_storage = self.make_storage()
        alice = util.auth.CreateUser(data_storage, "Alice", "secret123")
        bob = util.auth.CreateUser(data_storage, "Bob", "secret123")
        carol = util.auth.CreateUser(data_storage, "Carol", "secret123")
        self.assertIsNotNone(alice)
        self.assertIsNotNone(bob)
        self.assertIsNotNone(carol)
        assert alice is not None
        assert bob is not None
        assert carol is not None

        data_storage.friend.create_request(alice.id, bob.id)
        data_storage.friend.create_request(carol.id, bob.id)

        bob_token = util.auth.CreateToken(data_storage, bob.id, "127.0.0.1")
        decline_all_handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={bob_token}",
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint(
                "/v1/user/friend-requests/decline-all",
                decline_all_handler,
                command="POST",
            ),
        )
        self.assertEqual(decline_all_handler.json_body, {})
        self.assertEqual(data_storage.friend.count_pending_requests(bob.id), 0)

        data_storage.friend.accept_request(alice.id, bob.id)
        unfriend_handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={bob_token}",
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint(
                f"/v1/users/{alice.id}/unfriend",
                unfriend_handler,
                command="POST",
            ),
        )
        self.assertEqual(unfriend_handler.json_body, {})
        self.assertFalse(data_storage.friend.has_friendship(alice.id, bob.id))

    def test_follow_unfollow_and_following_exists(self) -> None:
        data_storage = self.make_storage()
        alice = util.auth.CreateUser(data_storage, "Alice", "secret123")
        bob = util.auth.CreateUser(data_storage, "Bob", "secret123")
        self.assertIsNotNone(alice)
        self.assertIsNotNone(bob)
        assert alice is not None
        assert bob is not None

        alice_token = util.auth.CreateToken(data_storage, alice.id, "127.0.0.1")
        follow_handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={alice_token}",
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint(f"/v1/users/{bob.id}/follow", follow_handler, command="POST"),
        )
        self.assertEqual(follow_handler.json_body, {"success": True})
        self.assertTrue(data_storage.follow_relationship.is_following(alice.id, bob.id))

        followers_count_handler = fake_handler(data_storage, command="GET")
        self.assertTrue(
            self.call_endpoint(
                f"/v1/users/{bob.id}/followers/count",
                followers_count_handler,
                command="GET",
            ),
        )
        self.assertEqual(followers_count_handler.json_body, {"count": 1})

        followings_count_handler = fake_handler(data_storage, command="GET")
        self.assertTrue(
            self.call_endpoint(
                f"/v1/users/{alice.id}/followings/count",
                followings_count_handler,
                command="GET",
            ),
        )
        self.assertEqual(followings_count_handler.json_body, {"count": 1})

        following_exists_handler = fake_handler(
            data_storage,
            body=json.dumps({"targetUserIds": [bob.id]}).encode("utf-8"),
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={alice_token}",
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint(
                "/v1/user/following-exists",
                following_exists_handler,
                command="POST",
            ),
        )
        self.assertEqual(
            following_exists_handler.json_body,
            {
                "followings": [{
                    "isFollowing": True,
                    "isFollowed": False,
                    "userId": bob.id,
                }],
            },
        )

        unfollow_handler = fake_handler(
            data_storage,
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={alice_token}",
            command="POST",
        )
        self.assertTrue(
            self.call_endpoint(f"/v1/users/{bob.id}/unfollow", unfollow_handler, command="POST"),
        )
        self.assertEqual(unfollow_handler.json_body, {})
        self.assertFalse(data_storage.follow_relationship.is_following(alice.id, bob.id))

    def test_legacy_friend_table_migrates_into_new_relationship_tables(self) -> None:
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir, True)
        sqlite_path = os.path.join(temp_dir, "legacy.sqlite")
        connection = sqlite3.connect(sqlite_path)
        try:
            connection.execute(
                """
                CREATE TABLE "friend" (
                    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    "requester_id" INTEGER NOT NULL,
                    "requestee_id" INTEGER NOT NULL,
                    "status" INTEGER NOT NULL DEFAULT 0,
                    "created_at" DATETIME NOT NULL,
                    UNIQUE ("requester_id", "requestee_id") ON CONFLICT REPLACE
                );
                """,
            )
            connection.execute(
                """
                INSERT INTO "friend"
                ("requester_id", "requestee_id", "status", "created_at")
                VALUES
                (1, 2, 1, '2026-01-01T00:00:00+00:00'),
                (3, 2, 0, '2026-01-01T00:01:00+00:00')
                """,
            )
            connection.commit()
        finally:
            connection.close()

        data_storage = storage.storager(sqlite_path, force_init=False)
        self.assertTrue(data_storage.friend.has_friendship(1, 2))
        self.assertTrue(data_storage.friend.has_pending_request(3, 2))
        self.assertEqual(data_storage.friend.count_friends(2), 1)
        self.assertEqual(data_storage.friend.count_pending_requests(2), 1)
