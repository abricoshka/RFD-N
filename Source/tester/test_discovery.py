import base64
import json
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace

from enums.AssetType import AssetType
from enums.PlaceYear import PlaceYear
import storage
import util.auth
import web_server._logic as web_logic
import web_server.endpoints.discovery_api  # noqa: F401
import web_server.endpoints.explore_api  # noqa: F401


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
        query: dict[str, str | list[str]] | None = None,
        cookie_header: str | None = None,
        command: str = "POST",
    ) -> None:
        self.server = fake_server(data_storage)
        self._body = body
        self.command = command
        self.headers: dict[str, str] = {}
        if cookie_header is not None:
            self.headers["Cookie"] = cookie_header
        self.client_address = ("127.0.0.1", 12345)
        self.domain = "apis.rbolock.tk"
        self.hostname = "https://apis.rbolock.tk"
        self.port_num = 443
        raw_query = query or {}
        self.query_lists = {
            key: (
                value
                if isinstance(value, list) else
                [value]
            )
            for key, value in raw_query.items()
        }
        self.query = {
            key: value[0]
            for key, value in self.query_lists.items()
        }
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
        if isinstance(text, str):
            text = text.encode("utf-8")
        if status is not None:
            self.status_code = status
        if content_type is not None:
            self.response_headers.append(("Content-Type", content_type))
        self.data_body = text


class TestDiscoveryApi(unittest.TestCase):
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
        command: str = "POST",
    ) -> bool:
        for key, func in web_logic.SERVER_FUNCS.items():
            if (
                key.mode == web_logic.func_mode.STATIC and
                key.path == path and
                key.command == command
            ):
                return func(handler)
        raise AssertionError(f"Endpoint not found: {command} {path}")

    @staticmethod
    def seed_game(
        data_storage: storage.storager,
        *,
        place_id: int,
        creator_id: int,
        creator_type: int,
        name: str,
        description: str,
        visit_count: int,
        player_count: int = 0,
        online_user_ids: list[int] | None = None,
        featured: bool = False,
        likes: int = 0,
        dislikes: int = 0,
    ) -> int:
        data_storage.asset.update(
            force_asset_id=place_id,
            name=name,
            description=description,
            asset_type=AssetType.Place,
            creator_id=creator_id,
            creator_type=creator_type,
        )
        data_storage.place.update(
            placeid=place_id,
            visitcount=visit_count,
            is_public=True,
            placeyear=PlaceYear.Twenty,
            featured=featured,
        )
        universe_id = data_storage.universe.update(
            root_place_id=place_id,
            creator_id=creator_id,
            creator_type=creator_type,
            place_year=PlaceYear.Twenty,
            is_featured=featured,
            is_public=True,
            visit_count=visit_count,
        )
        assert universe_id is not None

        if player_count or online_user_ids:
            server_uuid = f"server-{place_id}"
            data_storage.gameserver.update(
                server_uuid=server_uuid,
                server_name=f"Server {place_id}",
                place_id=place_id,
                player_count=player_count,
            )
            for user_id in online_user_ids or []:
                data_storage.ingame_player.update(
                    server_uuid,
                    user_id,
                )

        for offset in range(likes):
            data_storage.asset_vote.update(
                place_id,
                100000 + place_id + offset,
                True,
            )
        for offset in range(dislikes):
            data_storage.asset_vote.update(
                place_id,
                200000 + place_id + offset,
                False,
            )

        return universe_id

    def test_omni_recommendation_returns_real_game_data(self) -> None:
        data_storage = self.make_storage()
        current_user = util.auth.CreateUser(data_storage, "Viewer", "secret123")
        creator_user = util.auth.CreateUser(data_storage, "Builder", "secret123")
        self.assertIsNotNone(current_user)
        self.assertIsNotNone(creator_user)
        assert current_user is not None
        assert creator_user is not None

        data_storage.group.update(
            9001,
            "Builders Guild",
            "Group creator",
        )

        universe_one = self.seed_game(
            data_storage,
            place_id=101,
            creator_id=creator_user.id,
            creator_type=0,
            name="Castle Siege",
            description="Defend the castle.",
            visit_count=4200,
            player_count=12,
            likes=3,
            dislikes=1,
        )
        universe_two = self.seed_game(
            data_storage,
            place_id=202,
            creator_id=9001,
            creator_type=1,
            name="Space Tycoon",
            description="Build a station.",
            visit_count=8800,
            player_count=4,
            featured=True,
            likes=5,
            dislikes=0,
        )

        data_storage.asset_favorite.update(101, current_user.id)
        token = util.auth.CreateToken(data_storage, current_user.id, "127.0.0.1")
        handler = fake_handler(
            data_storage,
            body=json.dumps({
                "pageType": "Home",
                "sessionId": "test-session",
                "supportedTreatmentTypes": [
                    "SortlessGrid",
                    "Carousel",
                    "FriendCarousel",
                ],
                "sduiTreatmentTypes": ["Carousel", "HeroUnit"],
            }).encode("utf-8"),
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={token}",
        )

        self.assertTrue(
            self.call_endpoint('/discovery-api/omni-recommendation', handler),
        )
        self.assertEqual(handler.status_code, 200)
        self.assertEqual(handler.json_body["pageType"], "Home")

        sorts = handler.json_body["sorts"]
        topics = [sort["topic"] for sort in sorts]
        self.assertIn("Recommended For You", topics)
        self.assertIn("Sponsored", topics)
        self.assertIn("Favorites", topics)

        game_metadata = handler.json_body["contentMetadata"]["Game"]
        self.assertEqual(game_metadata[universe_one]["name"], "Castle Siege")
        self.assertEqual(game_metadata[universe_one]["rootPlaceId"], 101)
        self.assertEqual(game_metadata[universe_one]["playerCount"], 12)
        self.assertEqual(game_metadata[universe_one]["totalUpVotes"], 3)
        self.assertEqual(game_metadata[universe_one]["totalDownVotes"], 1)
        self.assertEqual(game_metadata[universe_two]["name"], "Space Tycoon")
        self.assertEqual(game_metadata[universe_two]["rootPlaceId"], 202)

        favorites_sort = next(
            sort
            for sort in sorts
            if sort["topic"] == "Favorites"
        )
        self.assertEqual(
            favorites_sort["recommendationList"][0]["contentId"],
            universe_one,
        )

    def test_omni_recommendation_returns_live_friend_games(self) -> None:
        data_storage = self.make_storage()
        viewer = util.auth.CreateUser(data_storage, "Viewer", "secret123")
        creator = util.auth.CreateUser(data_storage, "Builder", "secret123")
        friend_user = util.auth.CreateUser(data_storage, "FriendOne", "secret123")
        stranger_user = util.auth.CreateUser(data_storage, "RandomUser", "secret123")
        self.assertIsNotNone(viewer)
        self.assertIsNotNone(creator)
        self.assertIsNotNone(friend_user)
        self.assertIsNotNone(stranger_user)
        assert viewer is not None
        assert creator is not None
        assert friend_user is not None
        assert stranger_user is not None

        data_storage.friend.update(
            viewer.id,
            friend_user.id,
            status=1,
        )

        friend_universe = self.seed_game(
            data_storage,
            place_id=404,
            creator_id=creator.id,
            creator_type=0,
            name="Friends Hangout",
            description="Join your friends here.",
            visit_count=2500,
            player_count=0,
            online_user_ids=[friend_user.id, stranger_user.id],
            likes=4,
        )
        self.seed_game(
            data_storage,
            place_id=505,
            creator_id=creator.id,
            creator_type=0,
            name="Solo Arena",
            description="No friends inside.",
            visit_count=3300,
            player_count=7,
            likes=2,
        )

        token = util.auth.CreateToken(data_storage, viewer.id, "127.0.0.1")
        handler = fake_handler(
            data_storage,
            body=json.dumps({
                "pageType": "Home",
                "sessionId": "friend-session",
                "supportedTreatmentTypes": [
                    "SortlessGrid",
                    "Carousel",
                    "FriendCarousel",
                ],
            }).encode("utf-8"),
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={token}",
        )

        self.assertTrue(
            self.call_endpoint('/discovery-api/omni-recommendation', handler),
        )
        self.assertEqual(handler.status_code, 200)

        friends_sort = next(
            sort
            for sort in handler.json_body["sorts"]
            if sort["topic"] == "Friends"
        )
        self.assertEqual(len(friends_sort["recommendationList"]), 1)
        self.assertEqual(
            friends_sort["recommendationList"][0]["contentId"],
            friend_universe,
        )

        game_metadata = handler.json_body["contentMetadata"]["Game"]
        self.assertEqual(game_metadata[friend_universe]["playerCount"], 2)

    def test_omni_recommendation_metadata_returns_known_and_unknown_games(self) -> None:
        data_storage = self.make_storage()
        creator_user = util.auth.CreateUser(data_storage, "Builder", "secret123")
        self.assertIsNotNone(creator_user)
        assert creator_user is not None

        universe_id = self.seed_game(
            data_storage,
            place_id=303,
            creator_id=creator_user.id,
            creator_type=0,
            name="Obby World",
            description="Jump through stages.",
            visit_count=1500,
            player_count=9,
            likes=2,
            dislikes=1,
        )

        handler = fake_handler(
            data_storage,
            body=json.dumps({
                "sessionId": "test-session",
                "contents": [
                    {"contentType": "Game", "contentId": universe_id},
                    {"contentType": "Game", "contentId": 999999},
                ],
            }).encode("utf-8"),
        )

        self.assertTrue(
            self.call_endpoint(
                '/discovery-api/omni-recommendation-metadata',
                handler,
            ),
        )
        self.assertEqual(handler.status_code, 200)
        game_metadata = handler.json_body["contentMetadata"]["Game"]
        self.assertEqual(game_metadata[universe_id]["name"], "Obby World")
        self.assertEqual(game_metadata[universe_id]["rootPlaceId"], 303)
        self.assertEqual(game_metadata[universe_id]["totalUpVotes"], 2)
        self.assertEqual(game_metadata[999999]["name"], "Unknown Place")
        self.assertEqual(game_metadata[999999]["rootPlaceId"], 0)

    def test_explore_get_sorts_returns_filters_and_public_sorts(self) -> None:
        data_storage = self.make_storage()
        creator_user = util.auth.CreateUser(data_storage, "Builder", "secret123")
        self.assertIsNotNone(creator_user)
        assert creator_user is not None

        self.seed_game(
            data_storage,
            place_id=606,
            creator_id=creator_user.id,
            creator_type=0,
            name="Traffic Rush",
            description="Fast multiplayer driving.",
            visit_count=6000,
            player_count=9,
            likes=6,
            dislikes=1,
        )
        self.seed_game(
            data_storage,
            place_id=707,
            creator_id=creator_user.id,
            creator_type=0,
            name="Castle Escape",
            description="Adventure obby.",
            visit_count=2400,
            player_count=3,
            likes=3,
        )

        handler = fake_handler(
            data_storage,
            query={
                "sessionId": "explore-session",
                "device": "computer",
                "country": "us",
            },
            command="GET",
        )

        self.assertTrue(
            self.call_endpoint('/explore-api/v1/get-sorts', handler, command="GET"),
        )
        self.assertEqual(handler.status_code, 200)
        self.assertIsNone(handler.json_body["nextSortsPageToken"])

        sorts = handler.json_body["sorts"]
        self.assertEqual(sorts[0]["contentType"], "Filters")
        self.assertEqual(sorts[0]["filters"][0]["selectedOptionId"], "computer")
        self.assertEqual(sorts[0]["filters"][1]["selectedOptionId"], "us")

        sort_ids = [sort["sortId"] for sort in sorts[1:]]
        self.assertEqual(sort_ids, [
            "top-trending",
            "up-and-coming",
            "top-playing-now",
            "fun-with-friends",
            "top-revisited",
        ])

        playing_now = next(
            sort
            for sort in sorts
            if sort.get("sortId") == "top-playing-now"
        )
        self.assertEqual(playing_now["games"][0]["rootPlaceId"], 606)
        self.assertEqual(playing_now["games"][0]["playerCount"], 9)

    def test_explore_get_sorts_includes_recommended_for_authenticated_user(self) -> None:
        data_storage = self.make_storage()
        viewer = util.auth.CreateUser(data_storage, "Viewer", "secret123")
        creator = util.auth.CreateUser(data_storage, "Builder", "secret123")
        friend_user = util.auth.CreateUser(data_storage, "FriendOne", "secret123")
        self.assertIsNotNone(viewer)
        self.assertIsNotNone(creator)
        self.assertIsNotNone(friend_user)
        assert viewer is not None
        assert creator is not None
        assert friend_user is not None

        data_storage.friend.update(viewer.id, friend_user.id, status=1)
        self.seed_game(
            data_storage,
            place_id=808,
            creator_id=creator.id,
            creator_type=0,
            name="Recommended World",
            description="Friends are here.",
            visit_count=7200,
            player_count=0,
            online_user_ids=[friend_user.id],
            likes=5,
        )

        token = util.auth.CreateToken(data_storage, viewer.id, "127.0.0.1")
        handler = fake_handler(
            data_storage,
            query={"sessionId": "auth-explore"},
            cookie_header=f"{util.auth.AUTH_COOKIE_NAME}={token}",
            command="GET",
        )

        self.assertTrue(
            self.call_endpoint('/explore-api/v1/get-sorts', handler, command="GET"),
        )
        self.assertEqual(handler.status_code, 200)

        sort_ids = [sort["sortId"] for sort in handler.json_body["sorts"][1:]]
        self.assertEqual(sort_ids[0], "recommended-for-you")

        recommended = next(
            sort
            for sort in handler.json_body["sorts"]
            if sort.get("sortId") == "recommended-for-you"
        )
        self.assertEqual(recommended["games"][0]["rootPlaceId"], 808)
        self.assertEqual(recommended["games"][0]["playerCount"], 1)

    def test_explore_get_sorts_supports_page_token(self) -> None:
        data_storage = self.make_storage()
        creator_user = util.auth.CreateUser(data_storage, "Builder", "secret123")
        self.assertIsNotNone(creator_user)
        assert creator_user is not None

        for place_id, visits in ((901, 1000), (902, 2000), (903, 3000)):
            self.seed_game(
                data_storage,
                place_id=place_id,
                creator_id=creator_user.id,
                creator_type=0,
                name=f"Game {place_id}",
                description="Explore sort test.",
                visit_count=visits,
                player_count=place_id - 900,
            )

        token_payload = base64.b64encode(
            json.dumps({
                "start": 2,
                "count": 2,
            }).encode("utf-8"),
        ).decode("utf-8")
        handler = fake_handler(
            data_storage,
            query={"sortsPageToken": token_payload},
            command="GET",
        )

        self.assertTrue(
            self.call_endpoint('/explore-api/v1/get-sorts', handler, command="GET"),
        )
        self.assertEqual(handler.status_code, 200)
        self.assertEqual(
            [sort["sortId"] for sort in handler.json_body["sorts"]],
            ["top-playing-now", "fun-with-friends"],
        )
        self.assertIsNotNone(handler.json_body["nextSortsPageToken"])

    def test_discovery_and_explore_include_post_2020_universes(self) -> None:
        data_storage = self.make_storage()
        creator_user = util.auth.CreateUser(data_storage, "Builder", "secret123")
        self.assertIsNotNone(creator_user)
        assert creator_user is not None

        universe_one = self.seed_game(
            data_storage,
            place_id=1001,
            creator_id=creator_user.id,
            creator_type=0,
            name="Twenty One Game",
            description="Visible in discovery.",
            visit_count=500,
            player_count=2,
        )
        data_storage.place.update(
            placeid=1001,
            visitcount=500,
            is_public=True,
            placeyear=PlaceYear.TwentyOne,
            featured=False,
        )
        data_storage.universe.update(
            root_place_id=1001,
            creator_id=creator_user.id,
            creator_type=0,
            place_year=PlaceYear.TwentyOne,
            is_public=True,
            visit_count=500,
        )

        universe_two = self.seed_game(
            data_storage,
            place_id=1002,
            creator_id=creator_user.id,
            creator_type=0,
            name="Twenty Five Game",
            description="Visible in explore.",
            visit_count=700,
            player_count=4,
        )
        data_storage.place.update(
            placeid=1002,
            visitcount=700,
            is_public=True,
            placeyear=PlaceYear.TwentyFive,
            featured=False,
        )
        data_storage.universe.update(
            root_place_id=1002,
            creator_id=creator_user.id,
            creator_type=0,
            place_year=PlaceYear.TwentyFive,
            is_public=True,
            visit_count=700,
        )

        discovery_handler = fake_handler(
            data_storage,
            body=json.dumps({
                "pageType": "Home",
                "sessionId": "future-years",
                "supportedTreatmentTypes": ["SortlessGrid", "Carousel"],
            }).encode("utf-8"),
        )
        self.assertTrue(
            self.call_endpoint('/discovery-api/omni-recommendation', discovery_handler),
        )
        self.assertEqual(discovery_handler.status_code, 200)
        recommended = next(
            sort
            for sort in discovery_handler.json_body["sorts"]
            if sort["topic"] == "Recommended For You" and sort["recommendationList"] is not None
        )
        recommended_ids = {
            item["contentId"]
            for item in recommended["recommendationList"]
        }
        self.assertIn(universe_one, recommended_ids)
        self.assertIn(universe_two, recommended_ids)

        explore_handler = fake_handler(
            data_storage,
            query={"sessionId": "future-years"},
            command="GET",
        )
        self.assertTrue(
            self.call_endpoint('/explore-api/v1/get-sorts', explore_handler, command="GET"),
        )
        self.assertEqual(explore_handler.status_code, 200)
        playing_now = next(
            sort
            for sort in explore_handler.json_body["sorts"]
            if sort.get("sortId") == "top-playing-now"
        )
        place_ids = {
            item["rootPlaceId"]
            for item in playing_now["games"]
        }
        self.assertIn(1001, place_ids)
        self.assertIn(1002, place_ids)
