from __future__ import annotations

from collections import defaultdict
import dataclasses
from datetime import UTC, datetime
import json
import secrets
import uuid

from enums.AssetType import AssetType
from web_server._logic import web_server_handler, server_path

import util.auth


@dataclasses.dataclass
class discovery_game:
    universe_id: int
    root_place_id: int
    name: str
    description: str
    creator_id: int
    creator_type: int
    creator_name: str
    created_at: str
    updated_at: str
    minimum_age: int
    visit_count: int
    player_count: int
    total_up_votes: int
    total_down_votes: int
    favorite_count: int
    is_featured: bool


def _read_json_body(self: web_server_handler) -> dict[str, object] | None:
    try:
        raw = self.read_content()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        self.send_json({"error": "Invalid request format"}, 400)
        return None

    if not isinstance(payload, dict):
        self.send_json({"error": "Invalid request format"}, 400)
        return None
    return payload


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _pick_treatment_type(
    supported: list[str],
    *preferred: str,
) -> str:
    for value in preferred:
        if not supported or value in supported:
            return value
    return supported[0] if supported else preferred[0]


def _content_maturity(minimum_age: int) -> tuple[str, str]:
    if minimum_age >= 13:
        return ("moderate", f"Maturity: Moderate - Ages {minimum_age}+")
    if minimum_age >= 9:
        return ("mild", f"Maturity: Mild - Ages {minimum_age}+")
    return ("minimal", "Maturity: Minimal - Ages 5+")


def _creator_name(self: web_server_handler, creator_type: int, creator_id: int) -> str:
    if creator_type == 0:
        user = self.server.storage.user.check_object(creator_id)
        if user is not None:
            return user.username

        username = self.server.storage.players.get_player_field_from_index(
            index=self.server.storage.players.player_field.IDEN_NUM,
            value=creator_id,
            field=self.server.storage.players.player_field.USERNAME,
        )
        if isinstance(username, str) and username:
            return username
        return str(creator_id)

    group = self.server.storage.group.check_object(creator_id)
    if group is not None:
        return group.name
    return str(creator_id)


def _collect_candidate_universe_ids(self: web_server_handler) -> list[int]:
    seen: set[int] = set()
    candidate_ids: list[int] = []
    for sort_token, max_rows in (
        ("MostPopular", 100),
        ("Featured", 40),
        ("RecentlyUpdated", 40),
    ):
        page = self.server.storage.universe.list_for_games_api(
            sort_token=sort_token,
            start_rows=0,
            max_rows=max_rows,
        )
        for item in page.items:
            if item.universe_id in seen:
                continue
            seen.add(item.universe_id)
            candidate_ids.append(item.universe_id)
    return candidate_ids


def _load_games(
    self: web_server_handler,
    universe_ids: list[int],
) -> list[discovery_game]:
    storage = self.server.storage
    universe_rows: list[tuple[int, tuple, object]] = []
    place_ids: list[int] = []
    for universe_id in universe_ids:
        universe_row = storage.universe.check(universe_id)
        if universe_row is None:
            continue
        root_place_id = int(universe_row[0])
        place = storage.place.check_object(root_place_id)
        if place is None or not place.is_public or place.assetObj is None:
            continue
        if place.assetObj.asset_type != AssetType.Place:
            continue
        if not bool(universe_row[11]):
            continue
        universe_rows.append((universe_id, universe_row, place))
        place_ids.append(root_place_id)

    vote_totals = storage.asset_vote.get_totals_for_assets(place_ids)
    favorite_totals = storage.asset_favorite.get_totals_for_assets(place_ids)
    player_totals = _get_live_player_counts(self, place_ids)

    results: list[discovery_game] = []
    for universe_id, universe_row, place in universe_rows:
        root_place_id = int(universe_row[0])
        up_votes, down_votes = vote_totals.get(root_place_id, (0, 0))
        results.append(discovery_game(
            universe_id=universe_id,
            root_place_id=root_place_id,
            name=place.assetObj.name,
            description=place.assetObj.description,
            creator_id=int(universe_row[1]),
            creator_type=int(universe_row[2]),
            creator_name=_creator_name(self, int(universe_row[2]), int(universe_row[1])),
            created_at=str(universe_row[3]),
            updated_at=str(universe_row[4]),
            minimum_age=max(int(universe_row[8]), int(place.min_account_age)),
            visit_count=max(int(universe_row[13]), int(place.visitcount)),
            player_count=int(player_totals.get(root_place_id, 0)),
            total_up_votes=up_votes,
            total_down_votes=down_votes,
            favorite_count=int(favorite_totals.get(root_place_id, 0)),
            is_featured=bool(universe_row[7]) or bool(place.featured),
        ))
    return results


def _get_live_player_counts(
    self: web_server_handler,
    place_ids: list[int],
) -> dict[int, int]:
    if not place_ids:
        return {}

    storage = self.server.storage
    live_totals: dict[int, int] = defaultdict(int)
    live_servers = storage.gameserver.list_online_servers_for_places(place_ids)
    if live_servers:
        place_by_server_uuid = {
            server.server_uuid: server.place_id
            for server in live_servers
        }
        live_players = storage.ingame_player.list_for_server_uuids(
            list(place_by_server_uuid.keys()),
        )
        for player in live_players:
            place_id = place_by_server_uuid.get(player.server_uuid)
            if place_id is None:
                continue
            live_totals[place_id] += 1

    stored_totals = storage.gameserver.get_player_counts_for_places(place_ids)
    for place_id, player_count in stored_totals.items():
        live_totals.setdefault(place_id, player_count)
    return dict(live_totals)


def _get_friend_games(
    self: web_server_handler,
    user_id: int,
) -> tuple[list[discovery_game], dict[int, int]]:
    storage = self.server.storage
    friend_ids = storage.friend.list_friend_ids(user_id)
    if not friend_ids:
        return ([], {})

    friend_rows = storage.ingame_player.list_for_user_ids(friend_ids)
    if not friend_rows:
        return ([], {})

    place_by_server_uuid = storage.gameserver.get_place_ids_for_servers(
        sorted({
            row.server_uuid
            for row in friend_rows
        }),
    )
    if not place_by_server_uuid:
        return ([], {})

    friend_counts_by_place: dict[int, int] = defaultdict(int)
    seen_pairs: set[tuple[int, int]] = set()
    for row in friend_rows:
        place_id = place_by_server_uuid.get(row.server_uuid)
        if place_id is None:
            continue
        pair = (place_id, row.user_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        friend_counts_by_place[place_id] += 1

    friend_universe_ids = [
        universe_id
        for place_id in friend_counts_by_place
        for universe_id in [storage.universe.get_id_from_root_place_id(place_id)]
        if universe_id is not None
    ]
    friend_games = _load_games(self, friend_universe_ids)
    friend_games.sort(
        key=lambda game: (
            friend_counts_by_place.get(game.root_place_id, 0),
            game.player_count,
            game.visit_count,
            _parse_timestamp(game.updated_at),
        ),
        reverse=True,
    )
    return (friend_games, dict(friend_counts_by_place))


def _empty_game_metadata(universe_id: int) -> dict[str, object]:
    return {
        "totalUpVotes": 0,
        "totalDownVotes": 0,
        "universeId": universe_id,
        "name": "Unknown Place",
        "rootPlaceId": 0,
        "description": None,
        "playerCount": 0,
        "primaryMediaAsset": {},
        "under9": False,
        "under13": False,
        "minimumAge": 0,
        "contentMaturity": "unrated",
        "ageRecommendationDisplayName": "Maturity: Unknown - Ages 13+",
        "friendVisits": [],
        "friendVisitedString": "",
        "layoutDataBySort": {},
    }


def _game_metadata(game: discovery_game) -> dict[str, object]:
    content_maturity, age_display = _content_maturity(game.minimum_age)
    return {
        "totalUpVotes": game.total_up_votes,
        "totalDownVotes": game.total_down_votes,
        "universeId": game.universe_id,
        "name": game.name,
        "rootPlaceId": game.root_place_id,
        "description": game.description,
        "playerCount": game.player_count,
        "primaryMediaAsset": {},
        "under9": game.minimum_age <= 9,
        "under13": game.minimum_age <= 13,
        "minimumAge": game.minimum_age,
        "contentMaturity": content_maturity,
        "ageRecommendationDisplayName": age_display,
        "friendVisits": [],
        "friendVisitedString": "",
        "layoutDataBySort": {},
    }


def _recommendation_score(
    game: discovery_game,
    favorite_place_ids: set[int],
    friend_counts_by_place: dict[int, int],
) -> float:
    total_votes = game.total_up_votes + game.total_down_votes
    like_ratio = (
        game.total_up_votes / total_votes
        if total_votes else
        0.5
    )
    updated_at = _parse_timestamp(game.updated_at)
    recency_days = max(0.0, (datetime.now(UTC) - updated_at).total_seconds() / 86400.0)
    recency_bonus = max(0.0, 30.0 - recency_days) / 30.0

    score = (
        game.visit_count * 0.01 +
        game.player_count * 10.0 +
        game.favorite_count * 1.5 +
        like_ratio * 100.0 +
        recency_bonus * 15.0
    )
    if game.is_featured:
        score += 30.0
    if game.root_place_id in favorite_place_ids:
        score += 40.0
    score += friend_counts_by_place.get(game.root_place_id, 0) * 50.0
    return score


def _score_metadata(score: float) -> dict[str, float]:
    normalized = max(0.000001, min(score / 1000.0, 0.999999))
    return {"Score": round(normalized, 6)}


def _game_recommendation(game: discovery_game, score: float) -> dict[str, object]:
    return {
        "contentType": "Game",
        "contentId": game.universe_id,
        "contentStringId": "",
        "contentMetadata": _score_metadata(score),
    }


def _sponsored_recommendation(game: discovery_game) -> dict[str, object]:
    return {
        "contentType": "Game",
        "contentId": game.universe_id,
        "contentStringId": "",
        "contentMetadata": {
            "EncryptedAdTrackingData": secrets.token_urlsafe(48),
            "ad_id": str(uuid.uuid4()),
        },
    }


def _merge_metadata(
    metadata: dict[int, dict[str, object]],
    games: list[discovery_game],
) -> None:
    for game in games:
        metadata[game.universe_id] = _game_metadata(game)


def _games_by_universe_id(
    games: list[discovery_game],
) -> dict[int, discovery_game]:
    return {
        game.universe_id: game
        for game in games
    }


def _recommendation_response(self: web_server_handler, payload: dict[str, object]) -> dict[str, object]:
    page_type = str(payload.get("pageType") or "Home")
    if page_type != "Home":
        return {"error": "Unsupported page type"}

    raw_supported_types = payload.get("supportedTreatmentTypes", [])
    supported_types = (
        [
            item
            for item in raw_supported_types
            if isinstance(item, str)
        ]
        if isinstance(raw_supported_types, list) else
        []
    )

    current_user = util.auth.GetCurrentUser(self)
    favorite_place_ids: set[int] = set()
    favorite_games: list[discovery_game] = []
    friend_games: list[discovery_game] = []
    friend_counts_by_place: dict[int, int] = {}
    candidate_games = _load_games(self, _collect_candidate_universe_ids(self))

    if current_user is not None:
        favorite_place_id_list = self.server.storage.asset_favorite.list_asset_ids_for_user(
            current_user.id,
            limit=20,
        )
        favorite_place_ids = set(favorite_place_id_list)
        favorite_universe_ids = [
            universe_id
            for place_id in favorite_place_id_list
            for universe_id in [self.server.storage.universe.get_id_from_root_place_id(place_id)]
            if universe_id is not None
        ]
        favorite_games = _load_games(self, favorite_universe_ids)
        friend_games, friend_counts_by_place = _get_friend_games(self, current_user.id)

    scored_games = sorted(
        candidate_games,
        key=lambda game: (
            _recommendation_score(game, favorite_place_ids, friend_counts_by_place),
            game.visit_count,
            game.player_count,
        ),
        reverse=True,
    )
    sponsored_games = sorted(
        candidate_games,
        key=lambda game: (
            game.is_featured,
            game.visit_count,
            game.player_count,
            _parse_timestamp(game.updated_at),
        ),
        reverse=True,
    )[:3]

    metadata: dict[int, dict[str, object]] = {}
    _merge_metadata(metadata, friend_games)
    _merge_metadata(metadata, scored_games[:10])
    _merge_metadata(metadata, sponsored_games)
    _merge_metadata(metadata, favorite_games)

    friends_treatment = _pick_treatment_type(
        supported_types,
        "FriendCarousel",
        "Carousel",
        "SortlessGrid",
    )
    grid_treatment = _pick_treatment_type(
        supported_types,
        "SortlessGrid",
        "Carousel",
    )
    carousel_treatment = _pick_treatment_type(
        supported_types,
        "Carousel",
        "SortlessGrid",
    )

    response = {
        "pageType": "Home",
        "requestId": str(uuid.uuid4()),
        "sorts": [
            {
                "topic": "Friends",
                "topicId": 600000000,
                "treatmentType": friends_treatment,
                "recommendationList": [
                    _game_recommendation(
                        game,
                        float(friend_counts_by_place.get(game.root_place_id, 0)),
                    )
                    for game in friend_games[:5]
                ],
                "nextPageTokenForTopic": None,
                "numberOfRows": 1,
                "topicLayoutData": {},
            },
            {
                "topic": "Recommended For You",
                "topicId": 100000000,
                "treatmentType": grid_treatment,
                "recommendationList": [
                    _game_recommendation(
                        game,
                        _recommendation_score(game, favorite_place_ids, friend_counts_by_place),
                    )
                    for game in scored_games[:10]
                ],
                "nextPageTokenForTopic": None,
                "numberOfRows": 1,
                "topicLayoutData": {},
            },
            {
                "topic": "Recommended For You",
                "topicId": 100000000,
                "treatmentType": grid_treatment,
                "recommendationList": None,
                "nextPageTokenForTopic": None,
                "numberOfRows": 4,
                "topicLayoutData": {
                    "componentType": "GridTile",
                    "playButtonStyle": "Disabled",
                },
            },
            {
                "topic": "Sponsored",
                "topicId": 400000000,
                "treatmentType": carousel_treatment,
                "recommendationList": [
                    _sponsored_recommendation(game)
                    for game in sponsored_games
                ],
                "nextPageTokenForTopic": None,
                "numberOfRows": 1,
                "topicLayoutData": {
                    "componentType": "GridTile",
                    "playButtonStyle": "Disabled",
                },
            },
            {
                "topic": "Recommended For You",
                "topicId": 100000000,
                "treatmentType": grid_treatment,
                "recommendationList": None,
                "nextPageTokenForTopic": None,
                "numberOfRows": -1,
                "topicLayoutData": {
                    "componentType": "GridTile",
                    "playButtonStyle": "Disabled",
                },
            },
        ],
        "sortsRefreshInterval": 10800,
        "contentMetadata": {
            "Game": metadata,
            "RecommendedFriend": {},
            "GameCoPlay": {},
            "CatalogAsset": {},
            "CatalogBundle": {},
        },
        "contentMetadataByStringId": {
            "RecommendedFriend": {},
            "CatalogAvatar": {},
        },
        "nextPageToken": "",
        "isSessionExpired": False,
        "globalLayoutData": {},
        "isPartialFeed": False,
        "DebugInfoGroups": None,
        "sdui": None,
    }

    if favorite_games:
        response["sorts"].append({
            "topic": "Favorites",
            "topicId": 100000001,
            "treatmentType": carousel_treatment,
            "recommendationList": [
                _game_recommendation(
                        game,
                        _recommendation_score(game, favorite_place_ids, friend_counts_by_place),
                    )
                    for game in favorite_games
                ],
            "nextPageTokenForTopic": None,
            "numberOfRows": 1,
            "topicLayoutData": {},
        })

    return response


def _method_not_allowed(self: web_server_handler) -> bool:
    self.send_json({"error": "Method Not Allowed"}, 405)
    return True


@server_path('/discovery-api/omni-recommendation', commands={'GET'})
def _(self: web_server_handler) -> bool:
    return _method_not_allowed(self)


@server_path('/discovery-api/omni-recommendation', commands={'POST'})
def _(self: web_server_handler) -> bool:
    payload = _read_json_body(self)
    if payload is None:
        return True

    response = _recommendation_response(self, payload)
    if "error" in response:
        self.send_json(response, 400)
        return True

    self.send_json(response)
    return True


@server_path('/discovery-api/omni-recommendation-metadata', commands={'GET'})
def _(self: web_server_handler) -> bool:
    return _method_not_allowed(self)


@server_path('/discovery-api/omni-recommendation-metadata', commands={'POST'})
def _(self: web_server_handler) -> bool:
    payload = _read_json_body(self)
    if payload is None:
        return True

    contents = payload.get("contents")
    if not isinstance(contents, list):
        self.send_json({"error": "Invalid request format"}, 400)
        return True

    requested_universe_ids: list[int] = []
    for content in contents:
        if not isinstance(content, dict):
            continue
        if content.get("contentType") != "Game":
            continue
        try:
            requested_universe_ids.append(int(content.get("contentId")))
        except (TypeError, ValueError):
            continue

    games = _games_by_universe_id(_load_games(self, requested_universe_ids))
    metadata = {
        universe_id: _game_metadata(game)
        for universe_id, game in games.items()
    }
    for universe_id in requested_universe_ids:
        metadata.setdefault(universe_id, _empty_game_metadata(universe_id))

    self.send_json({
        "contentMetadata": {
            "Game": metadata,
            "CatalogAsset": {},
            "CatalogBundle": {},
            "RecommendedFriend": {},
        }
    })
    return True
