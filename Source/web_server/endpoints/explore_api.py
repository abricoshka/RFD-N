from __future__ import annotations

import base64
import copy
from datetime import UTC, datetime, timedelta
import json
import secrets
from typing import Any

import util.auth
from web_server._logic import server_path, web_server_handler

from . import discovery_api


COUNTRIES = [
    {"optionId": "all", "optionDisplayName": "All Locations"},
    {"optionId": "nl", "optionDisplayName": "Netherlands"},
    {"optionId": "af", "optionDisplayName": "Afghanistan"},
    {"optionId": "al", "optionDisplayName": "Albania"},
    {"optionId": "dz", "optionDisplayName": "Algeria"},
    {"optionId": "ad", "optionDisplayName": "Andorra"},
    {"optionId": "ao", "optionDisplayName": "Angola"},
    {"optionId": "ar", "optionDisplayName": "Argentina"},
    {"optionId": "am", "optionDisplayName": "Armenia"},
    {"optionId": "au", "optionDisplayName": "Australia"},
    {"optionId": "at", "optionDisplayName": "Austria"},
    {"optionId": "az", "optionDisplayName": "Azerbaijan"},
    {"optionId": "bd", "optionDisplayName": "Bangladesh"},
    {"optionId": "be", "optionDisplayName": "Belgium"},
    {"optionId": "bo", "optionDisplayName": "Bolivia"},
    {"optionId": "br", "optionDisplayName": "Brazil"},
    {"optionId": "bg", "optionDisplayName": "Bulgaria"},
    {"optionId": "ca", "optionDisplayName": "Canada"},
    {"optionId": "cl", "optionDisplayName": "Chile"},
    {"optionId": "cn", "optionDisplayName": "China"},
    {"optionId": "co", "optionDisplayName": "Colombia"},
    {"optionId": "hr", "optionDisplayName": "Croatia"},
    {"optionId": "cz", "optionDisplayName": "Czech Republic"},
    {"optionId": "dk", "optionDisplayName": "Denmark"},
    {"optionId": "eg", "optionDisplayName": "Egypt"},
    {"optionId": "ee", "optionDisplayName": "Estonia"},
    {"optionId": "fi", "optionDisplayName": "Finland"},
    {"optionId": "fr", "optionDisplayName": "France"},
    {"optionId": "de", "optionDisplayName": "Germany"},
    {"optionId": "gr", "optionDisplayName": "Greece"},
    {"optionId": "in", "optionDisplayName": "India"},
    {"optionId": "id", "optionDisplayName": "Indonesia"},
    {"optionId": "ie", "optionDisplayName": "Ireland"},
    {"optionId": "it", "optionDisplayName": "Italy"},
    {"optionId": "jp", "optionDisplayName": "Japan"},
    {"optionId": "kr", "optionDisplayName": "South Korea"},
    {"optionId": "lv", "optionDisplayName": "Latvia"},
    {"optionId": "lt", "optionDisplayName": "Lithuania"},
    {"optionId": "my", "optionDisplayName": "Malaysia"},
    {"optionId": "mx", "optionDisplayName": "Mexico"},
    {"optionId": "no", "optionDisplayName": "Norway"},
    {"optionId": "ph", "optionDisplayName": "Philippines"},
    {"optionId": "pl", "optionDisplayName": "Poland"},
    {"optionId": "pt", "optionDisplayName": "Portugal"},
    {"optionId": "ro", "optionDisplayName": "Romania"},
    {"optionId": "ru", "optionDisplayName": "Russian Federation"},
    {"optionId": "sg", "optionDisplayName": "Singapore"},
    {"optionId": "sk", "optionDisplayName": "Slovakia"},
    {"optionId": "si", "optionDisplayName": "Slovenia"},
    {"optionId": "za", "optionDisplayName": "South Africa"},
    {"optionId": "es", "optionDisplayName": "Spain"},
    {"optionId": "se", "optionDisplayName": "Sweden"},
    {"optionId": "ch", "optionDisplayName": "Switzerland"},
    {"optionId": "th", "optionDisplayName": "Thailand"},
    {"optionId": "tr", "optionDisplayName": "Turkey"},
    {"optionId": "ua", "optionDisplayName": "Ukraine"},
    {"optionId": "ae", "optionDisplayName": "United Arab Emirates"},
    {"optionId": "gb", "optionDisplayName": "United Kingdom"},
    {"optionId": "us", "optionDisplayName": "United States"},
    {"optionId": "vn", "optionDisplayName": "Vietnam"},
]

DEVICE_OPTIONS = [
    {"optionId": "all", "optionDisplayName": "All Devices"},
    {"optionId": "low_end_phone", "optionDisplayName": "Entry-level Phone"},
    {"optionId": "high_end_phone", "optionDisplayName": "Standard Phone"},
    {"optionId": "low_end_tablet", "optionDisplayName": "Entry-level Tablet"},
    {"optionId": "high_end_tablet", "optionDisplayName": "Standard Tablet"},
    {"optionId": "computer", "optionDisplayName": "Computer"},
    {"optionId": "console", "optionDisplayName": "Console"},
    {"optionId": "vr", "optionDisplayName": "VR"},
]


def _decode_page_token(token: str | None) -> tuple[int, int]:
    if not token:
        return (0, 6)
    try:
        raw = base64.b64decode(token.encode("utf-8"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return (0, 6)
    if not isinstance(payload, dict):
        return (0, 6)

    try:
        start = int(payload.get("start", 0))
        count = int(payload.get("count", 6))
    except (TypeError, ValueError):
        return (0, 6)
    return (max(0, start), max(1, count))


def _encode_page_token(
    start: int,
    count: int,
    session_id: str,
    max_memory: str,
) -> str:
    payload = {
        "start": start,
        "count": count,
        "session_id": session_id,
        "max_memory": max_memory,
        "page_config_name": "with_alpha_location_filter_all",
    }
    return base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8"),
    ).decode("utf-8")


def _filter_block(device: str, country: str) -> dict[str, Any]:
    return {
        "contentType": "Filters",
        "gameSetTypeId": 23,
        "gameSetTargetId": 504,
        "primarySortId": 23,
        "secondarySortId": 504,
        "id": "filters_v4",
        "sortId": "filters",
        "sortDisplayName": "Popular on:",
        "topicLayoutData": [],
        "treatmentType": "Pills",
        "filters": [
            {
                "filterId": "device_filter_v1",
                "filterType": "device",
                "filterDisplayName": "Device",
                "filterOptions": copy.deepcopy(DEVICE_OPTIONS),
                "defaultOptionId": "computer",
                "selectedOptionId": device,
                "filterLayoutData": [],
            },
            {
                "filterId": "country_filter_v3",
                "filterType": "country",
                "filterDisplayName": "Location",
                "filterOptions": copy.deepcopy(COUNTRIES),
                "defaultOptionId": "nl",
                "selectedOptionId": country,
                "filterLayoutData": [],
            },
        ],
    }


def _sort_configs(
    device: str,
    country: str,
    *,
    include_recommended: bool,
) -> list[dict[str, Any]]:
    applied_filters = f"device={device},age=all,country={country}"
    configs: list[dict[str, Any]] = [
        {
            "contentType": "Games",
            "gameSetTypeId": 23,
            "gameSetTargetId": 238,
            "primarySortId": 23,
            "secondarySortId": 238,
            "id": "Top_Trending_V4",
            "sortId": "top-trending",
            "appliedFilters": applied_filters,
            "sortDisplayName": "Top Trending",
            "sortType": "trending",
            "topicLayoutData": {
                "infoText": "Experiences with the largest increase in time spent over the past two weeks, sorted by their number of daily users.",
                "playButtonStyle": "Disabled",
            },
            "treatmentType": "Carousel",
        },
        {
            "contentType": "Games",
            "gameSetTypeId": 23,
            "gameSetTargetId": 239,
            "primarySortId": 23,
            "secondarySortId": 239,
            "id": "Up_And_Coming_V4",
            "sortId": "up-and-coming",
            "appliedFilters": applied_filters,
            "sortDisplayName": "Up-and-Coming",
            "sortType": "up-and-coming",
            "topicLayoutData": {
                "infoText": "New experiences that users spent the most time in, that have the biggest relative increase in time spent over the last 2 weeks.",
                "playButtonStyle": "Disabled",
            },
            "treatmentType": "Carousel",
        },
        {
            "contentType": "Games",
            "gameSetTypeId": 23,
            "gameSetTargetId": 671,
            "primarySortId": 23,
            "secondarySortId": 671,
            "id": "CCU_Based_V1",
            "sortId": "top-playing-now",
            "sortDisplayName": "Top Playing Now",
            "sortType": "playing-now",
            "subtitle": "Results for all devices and locations",
            "topicLayoutData": {
                "infoText": "Top experiences sorted by the number of concurrent users.",
                "playButtonStyle": "Disabled",
            },
            "treatmentType": "Carousel",
        },
        {
            "contentType": "Games",
            "gameSetTypeId": 23,
            "gameSetTargetId": 222,
            "primarySortId": 23,
            "secondarySortId": 222,
            "id": "Fun_With_Friends_V4",
            "sortId": "fun-with-friends",
            "appliedFilters": applied_filters,
            "sortDisplayName": "Fun with Friends",
            "sortType": "fun-with-friends",
            "topicLayoutData": {
                "infoText": "Experiences with at least 5000 users daily, sorted by the proportion of time spent as groups of friends.",
                "playButtonStyle": "Disabled",
            },
            "treatmentType": "Carousel",
        },
        {
            "contentType": "Games",
            "gameSetTypeId": 23,
            "gameSetTargetId": 237,
            "primarySortId": 23,
            "secondarySortId": 237,
            "id": "Top_Revisited_Existing_Users_V4",
            "sortId": "top-revisited",
            "appliedFilters": applied_filters,
            "sortDisplayName": "Top Revisited",
            "sortType": "top-revisited",
            "topicLayoutData": {
                "infoText": "Experiences sorted by the proportion of users who come back after a week.",
                "playButtonStyle": "Disabled",
            },
            "treatmentType": "Carousel",
        },
    ]

    if include_recommended:
        configs.insert(0, {
            "contentType": "Games",
            "gameSetTypeId": 25,
            "gameSetTargetId": 501,
            "primarySortId": 25,
            "secondarySortId": 501,
            "id": "Recommended_For_You_V2",
            "sortId": "recommended-for-you",
            "appliedFilters": applied_filters,
            "sortDisplayName": "Recommended for You",
            "sortType": "recommended",
            "topicLayoutData": {
                "infoText": "Personalized game recommendations based on your play history and preferences.",
                "playButtonStyle": "Disabled",
            },
            "treatmentType": "Carousel",
        })
    return configs


def _pick_games_for_sort(
    sort_type: str,
    candidate_games: list[discovery_api.discovery_game],
    *,
    recommended_games: list[discovery_api.discovery_game],
    friend_games: list[discovery_api.discovery_game],
) -> list[discovery_api.discovery_game]:
    now = datetime.now(UTC)
    if sort_type == "recommended":
        return recommended_games
    if sort_type == "trending":
        return sorted(
            candidate_games,
            key=lambda game: (
                game.visit_count,
                game.player_count,
                discovery_api._parse_timestamp(game.updated_at),
            ),
            reverse=True,
        )
    if sort_type == "up-and-coming":
        recent_cutoff = now - timedelta(days=90)
        return sorted(
            candidate_games,
            key=lambda game: (
                discovery_api._parse_timestamp(game.created_at) >= recent_cutoff,
                discovery_api._parse_timestamp(game.created_at),
                game.visit_count,
            ),
            reverse=True,
        )
    if sort_type == "playing-now":
        return sorted(
            candidate_games,
            key=lambda game: (
                game.player_count,
                game.visit_count,
                discovery_api._parse_timestamp(game.updated_at),
            ),
            reverse=True,
        )
    if sort_type == "fun-with-friends":
        if friend_games:
            return friend_games
        return sorted(
            candidate_games,
            key=lambda game: (
                game.visit_count >= 5000,
                game.player_count,
                game.visit_count,
            ),
            reverse=True,
        )
    if sort_type == "top-revisited":
        return sorted(
            candidate_games,
            key=lambda game: (
                game.visit_count,
                discovery_api._parse_timestamp(game.updated_at),
                discovery_api._parse_timestamp(game.created_at),
            ),
            reverse=True,
    )
    return candidate_games


def _matches_device(
    game: discovery_api.discovery_game,
    device: str,
) -> bool:
    if device == "all":
        return True

    haystack = f"{game.name} {game.description}".lower()
    if device in {"low_end_phone", "high_end_phone", "low_end_tablet", "high_end_tablet"}:
        return (
            "mobile" in haystack or
            "touch" in haystack or
            "tablet" in haystack
        )
    if device == "computer":
        return "mobile only" not in haystack
    if device == "console":
        return "console" in haystack
    if device == "vr":
        return (
            "vr" in haystack or
            "virtual reality" in haystack or
            "oculus" in haystack
        )
    return True


def _format_game(game: discovery_api.discovery_game) -> dict[str, Any]:
    minimum_age = max(5, game.minimum_age)
    _, age_display = discovery_api._content_maturity(minimum_age)
    return {
        "universeId": game.universe_id,
        "rootPlaceId": game.root_place_id,
        "name": game.name,
        "playerCount": game.player_count,
        "totalUpVotes": game.total_up_votes,
        "totalDownVotes": game.total_down_votes,
        "isSponsored": False,
        "nativeAdData": "",
        "isShowSponsoredLabel": False,
        "price": None,
        "analyticsIdentifier": None,
        "gameDescription": game.description,
        "genre": "All",
        "minimumAge": minimum_age,
        "ageRecommendationDisplayName": age_display,
        "serverPlaceId": None,
        "visits": game.visit_count,
        "created": game.created_at,
        "updated": game.updated_at,
    }


@server_path('/explore-api/v1/get-sorts', commands={'GET'})
def _(self: web_server_handler) -> bool:
    session_id = self.query.get("sessionId") or secrets.token_hex(16)
    device = self.query.get("device") or "computer"
    country = self.query.get("country") or "all"
    max_memory = self.query.get("maxMemory") or "8192"
    current_start, current_count = _decode_page_token(self.query.get("sortsPageToken"))

    current_user = util.auth.GetCurrentUser(self)
    favorite_place_ids: set[int] = set()
    friend_games: list[discovery_api.discovery_game] = []
    friend_counts_by_place: dict[int, int] = {}

    if current_user is not None:
        favorite_place_ids = set(
            self.server.storage.asset_favorite.list_asset_ids_for_user(
                current_user.id,
                limit=40,
            ),
        )
        friend_games, friend_counts_by_place = discovery_api._get_friend_games(
            self,
            current_user.id,
        )

    candidate_games = discovery_api._load_games(
        self,
        discovery_api._collect_candidate_universe_ids(self),
    )
    candidate_games = [
        game
        for game in candidate_games
        if _matches_device(game, device)
    ]
    recommended_games = sorted(
        candidate_games,
        key=lambda game: (
            discovery_api._recommendation_score(
                game,
                favorite_place_ids,
                friend_counts_by_place,
            ),
            game.visit_count,
            game.player_count,
        ),
        reverse=True,
    )

    sort_configs = _sort_configs(
        device,
        country,
        include_recommended=(current_user is not None),
    )
    total_sorts = len(sort_configs)
    end_index = min(current_start + current_count, total_sorts)

    sorts: list[dict[str, Any]] = []
    if current_start == 0:
        sorts.append(_filter_block(device, country))

    for index in range(current_start, end_index):
        sort_config = dict(sort_configs[index])
        sort_type = str(sort_config.pop("sortType"))
        selected_games = _pick_games_for_sort(
            sort_type,
            candidate_games,
            recommended_games=recommended_games,
            friend_games=friend_games,
        )
        sort_config["games"] = [
            _format_game(game)
            for game in selected_games[:40]
        ]
        sorts.append(sort_config)

    next_token = None
    if end_index < total_sorts:
        next_token = _encode_page_token(
            end_index,
            current_count,
            session_id,
            str(max_memory),
        )

    self.send_json({
        "sorts": sorts,
        "nextSortsPageToken": next_token,
    })
    return True
