from collections import defaultdict
from datetime import datetime
import re

import util.auth
from web_server._logic import web_server_handler, server_path


def _format_api_datetime(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except ValueError:
        return value


def _get_creator_name(
    self: web_server_handler,
    creator_type: int,
    creator_id: int,
) -> str:
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


@server_path('/maintenance-status/v1/alerts/alert-info', commands={'GET'})
@server_path('/alerts/alert-info', commands={'GET'})
def _(self: web_server_handler) -> bool:
    self.send_json({
        "IsVisible": True,
        "Text": "RFD btw.",
        "LinkText": "",
        "LinkUrl": "",
    })
    return True


@server_path('/v1/games/list', commands={'GET'})
def _(self: web_server_handler) -> bool:
    sort_token = self.query.get("sort_token") or "MostPopular"
    try:
        start_rows = int(self.query.get("startRows") or 0)
        max_rows = int(self.query.get("maxRows") or 40)
    except ValueError:
        self.send_json(
            {"errors": [{"code": 0, "message": "Invalid pagination arguments."}]},
            400,
        )
        return False

    if sort_token not in ["MostPopular", "Featured", "RecentlyUpdated"]:
        self.send_json(
            {"errors": [{"code": 0, "message": "Invalid sort token."}]},
            400,
        )
        return False
    if start_rows < 0:
        self.send_json(
            {"errors": [{"code": 0, "message": "Invalid start rows."}]},
            400,
        )
        return False
    if max_rows > 100 or max_rows < 0:
        self.send_json(
            {"errors": [{"code": 0, "message": "Max rows must be between 0-40"}]},
            400,
        )
        return False

    universe_page = self.server.storage.universe.list_for_games_api(
        sort_token=sort_token,
        start_rows=start_rows,
        max_rows=max_rows,
    )

    storage = self.server.storage
    place_ids = [item.root_place_id for item in universe_page.items]
    vote_totals = storage.asset_vote.get_totals_for_assets(place_ids)
    favorite_totals = storage.asset_favorite.get_totals_for_assets(place_ids)
    player_totals = _get_live_player_counts(self, place_ids)

    game_list = []
    for universe_obj in universe_page.items:
        place_obj = storage.place.check_object(universe_obj.root_place_id)
        if place_obj is None or place_obj.assetObj is None:
            continue

        asset_obj = place_obj.assetObj
        creator_name = _get_creator_name(
            self,
            universe_obj.creator_type,
            universe_obj.creator_id,
        )
        up_votes, down_votes = vote_totals.get(place_obj.placeid, (0, 0))
        player_count = int(player_totals.get(place_obj.placeid, 0))
        minimum_age = max(
            universe_obj.minimum_account_age,
            place_obj.min_account_age,
        )

        game_list.append({
            "creatorId": universe_obj.creator_id,
            "creatorName": creator_name,
            "creatorType": "User" if universe_obj.creator_type == 0 else "Group",
            "creatorHasVerifiedBadge": False,
            "upVotes": up_votes,
            "downVotes": down_votes,
            "totalUpVotes": up_votes,
            "totalDownVotes": down_votes,
            "universeId": universe_obj.universe_id,
            "name": asset_obj.name,
            "placeId": place_obj.placeid,
            "playerCount": player_count,
            "imageToken": "",
            "isSponsored": False,
            "nativeAdData": "",
            "isShowSponsoredLabel": False,
            "price": asset_obj.price_robux if asset_obj.is_for_sale else 0,
            "analyticsIdentifier": "",
            "gameDescription": asset_obj.description,
            "genre": "All",
            "minimumAge": minimum_age,
            "totalFavorites": int(favorite_totals.get(place_obj.placeid, 0)),
        })

    self.send_json({
        "games": game_list,
        "suggestedKeyword": "",
        "correctedKeyword": "",
        "filteredKeyword": "",
        "hasMoreRows": universe_page.has_next,
        "nextPageExclusiveStartId": (
            start_rows + max_rows
            if universe_page.has_next else
            0
        ),
        "featuredSearchUniverseId": 0,
        "emphasis": False,
        "cutOffIndex": 0,
        "algorithm": "",
        "algorithmQueryType": "",
        "suggestionAlgorithm": "",
        "relatedGames": [],
    })
    return True


@server_path(r'/v1/games/sorts', commands={'GET'})
def _(self: web_server_handler) -> bool:
    self.send_json({
        "sorts": [
            {
                "token": "MostPopular",
                "name": "most_popular",
                "displayName": "Popular",
                "gameSetTypeId": 1,
                "gameSetTargetId": 90,
                "timeOptionsAvailable": False,
                "genreOptionsAvailable": False,
                "numberOfRows": 2,
                "numberOfGames": 0,
                "isDefaultSort": True,
                "contextUniverseId": None,
                "contextCountryRegionId": 1,
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "Featured",
                "name": "featured",
                "displayName": "Featured",
                "gameSetTypeId": 2,
                "gameSetTargetId": 91,
                "timeOptionsAvailable": False,
                "genreOptionsAvailable": False,
                "numberOfRows": 1,
                "numberOfGames": 0,
                "isDefaultSort": True,
                "contextUniverseId": None,
                "contextCountryRegionId": 1,
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "RecentlyUpdated",
                "name": "recently_updated",
                "displayName": "Recently Updated",
                "gameSetTypeId": 3,
                "gameSetTargetId": 93,
                "timeOptionsAvailable": False,
                "genreOptionsAvailable": False,
                "numberOfRows": 1,
                "numberOfGames": 0,
                "isDefaultSort": True,
                "contextUniverseId": None,
                "contextCountryRegionId": 1,
                "tokenExpiryInSeconds": 3600,
            },
        ],
        "timeFilters": [
            {
                "token": "Now",
                "name": "Now",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "PastDay",
                "name": "PastDay",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "PastWeek",
                "name": "PastWeek",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "PastMonth",
                "name": "PastMonth",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "AllTime",
                "name": "AllTime",
                "tokenExpiryInSeconds": 3600,
            },
        ],
        "genreFilters": [
            {
                "token": "T638364961735517991_1_89de",
                "name": "All",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518009_19_3d2",
                "name": "Building",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518045_11_3de6",
                "name": "Horror",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518062_7_558c",
                "name": "Town and City",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518076_17_c371",
                "name": "Military",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518094_15_2056",
                "name": "Comedy",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518107_8_6d4f",
                "name": "Medieval",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518120_13_c168",
                "name": "Adventure",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518134_9_e6aa",
                "name": "Sci-Fi",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518156_12_13fb",
                "name": "Naval",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518169_20_46a",
                "name": "FPS",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518183_21_4bbf",
                "name": "RPG",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518192_14_efc6",
                "name": "Sports",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518205_10_fa83",
                "name": "Fighting",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518223_16_5d38",
                "name": "Western",
                "tokenExpiryInSeconds": 3600,
            },
        ],
        "gameFilters": [
            {
                "token": "T638364961735518263_Any_56d2",
                "name": "Any",
                "tokenExpiryInSeconds": 3600,
            },
            {
                "token": "T638364961735518277_Classic_a1f4",
                "name": "Classic",
                "tokenExpiryInSeconds": 3600,
            },
        ],
        "pageContext": {
            "pageId": "f5b1510e-3810-42ab-8135-8ffa5ef221ba",
            "isSeeAllPage": None,
        },
        "gameSortStyle": None,
    })
    return True


@server_path(r'/v1/games/recommendations/game/(\d+)/?', regex=True)
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    universe_id = int(match.group(1))
    universe = self.server.storage.universe.check(universe_id)
    if universe is None:
        self.send_json({
            "errors": [{"code": 2, "message": "The requested universe does not exist."}],
        }, 404)
        return True

    self.send_json({
        "games": [],
        "nextPaginationKey": None,
    })
    return True


@server_path('/v1/games/multiget-playability-status')
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    universe_ids_raw = self.query.get('universeIds')
    universe_ids = universe_ids_raw.split(',')

    response_items = []
    for universe_id in universe_ids:
        del universe_id
        break

    self.send_json(response_items)
    return True


@server_path('/v1/private-servers/enabled-in-universe/')
def _(self: web_server_handler) -> bool:
    self.send_json({"privateServersEnabled": True})
    return True


@server_path(r'/v1/games/(\d+)/game-passes', regex=True)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    universe_id = int(match.group(1))
    universe = self.server.storage.universe.check(universe_id)
    if universe is None:
        self.send_json({
            "errors": [{"code": 2, "message": "The requested universe does not exist."}],
        }, 404)
        return True

    self.send_json({
        "previousPageCursor": None,
        "nextPageCursor": None,
        "data": [],
    })
    return True


@server_path(r'/v2/games/(\d+)/media', regex=True)
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    universe_id = int(match.group(1))
    universe = self.server.storage.universe.check(universe_id)
    if universe is None:
        self.send_json({
            "errors": [{"code": 2, "message": "The requested universe does not exist."}],
        }, 404)
        return True

    self.send_json({"data": []})
    return True
