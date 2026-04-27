import json
import re

from enums.AssetType import AssetType
import util.auth
from web_server._logic import server_path, web_server_handler

OWNERSHIP_REQUIRED_VOTE_TYPES = {
    AssetType.GamePass,
    AssetType.Shirt,
    AssetType.TShirt,
    AssetType.Pants,
    AssetType.Hat,
    AssetType.Gear,
    AssetType.Plugin,
    AssetType.HairAccessory,
    AssetType.FaceAccessory,
    AssetType.NeckAccessory,
    AssetType.ShoulderAccessory,
    AssetType.FrontAccessory,
    AssetType.BackAccessory,
    AssetType.WaistAccessory,
    AssetType.EarAccessory,
    AssetType.EyeAccessory,
    AssetType.TShirtAccessory,
    AssetType.ShirtAccessory,
    AssetType.PantsAccessory,
    AssetType.JacketAccessory,
    AssetType.Package,
}


def _read_json_body(self: web_server_handler) -> dict[str, object] | None:
    try:
        raw = self.read_content()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        self.send_json(
            {"errors": [{"code": 0, "message": "Malformed JSON body"}]},
            400,
        )
        return None

    if not isinstance(payload, dict):
        self.send_json(
            {"errors": [{"code": 0, "message": "Malformed JSON body"}]},
            400,
        )
        return None
    return payload


def _resolve_place_from_game_identifier(
        self: web_server_handler,
        game_id: int,
):
    storage = self.server.storage
    universe = storage.universe.check(game_id)
    if universe is not None:
        place = storage.place.check_object(int(universe[0]))
        if (
                place is not None and
                place.assetObj is not None and
                place.assetObj.asset_type == AssetType.Place
        ):
            return place

    place = storage.place.check_object(game_id)
    if (
            place is not None and
            place.assetObj is not None and
            place.assetObj.asset_type == AssetType.Place
    ):
        return place

    asset = storage.asset.resolve_object(game_id)
    if asset is not None and asset.asset_type == AssetType.Place:
        return storage.place.check_object(asset.id)
    return None


def _resolve_rate_asset(
        self: web_server_handler,
        asset_id: int,
):
    asset = self.server.storage.asset.resolve_object(asset_id)
    if asset is not None:
        return asset

    place = _resolve_place_from_game_identifier(self, asset_id)
    if place is None:
        return None
    return place.assetObj


def GetAssetLikesAndDislikes(
        self: web_server_handler,
        asset_id: int,
) -> tuple[int, int]:
    return self.server.storage.asset_vote.get_totals_for_assets([asset_id]).get(
        asset_id,
        (0, 0),
    )


def GetUserVoteStatus(
        self: web_server_handler,
        asset_id: int,
        user_id: int,
) -> int:
    vote = self.server.storage.asset_vote.get_user_vote(asset_id, user_id)
    if vote is None:
        return 0
    if vote:
        return 1
    return 2


def GetAssetVotePercentage(
        self: web_server_handler,
        asset_id: int,
) -> int:
    likes, dislikes = GetAssetLikesAndDislikes(self, asset_id)
    total_votes = likes + dislikes
    if total_votes <= 0:
        return 50
    return int((likes / total_votes) * 100)


def GetAssetFavoriteCount(
        self: web_server_handler,
        asset_id: int,
) -> int:
    return int(
        self.server.storage.asset_favorite.get_totals_for_assets([asset_id]).get(
            asset_id,
            0,
        )
    )


def GetUserFavoriteStatus(
        self: web_server_handler,
        asset_id: int,
        user_id: int,
) -> bool:
    return self.server.storage.asset_favorite.check(asset_id, user_id) is not None


def _can_user_rate_asset(
        self: web_server_handler,
        asset_obj,
        user_id: int,
) -> tuple[bool, str]:
    if asset_obj.asset_type == AssetType.Place:
        if self.server.storage.previously_played.check(user_id, asset_obj.id) is None:
            return (False, "You can only vote on games you have played")
        return (True, "")

    if asset_obj.asset_type in OWNERSHIP_REQUIRED_VOTE_TYPES:
        if self.server.storage.user_asset.check(user_id, asset_obj.id) is None:
            return (False, "You can only vote on items you own")
        return (True, "")

    return (True, "")


def _parse_toggle_favorite_value(payload: dict[str, object]) -> bool | None:
    if "favorite" in payload:
        value = payload["favorite"]
    elif "isFavorited" in payload:
        value = payload["isFavorited"]
    else:
        return True

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1"}:
            return True
        if lowered in {"false", "0"}:
            return False
    return None


def _parse_vote_status(payload: dict[str, object]) -> int | None:
    if "vote" not in payload:
        return None

    value = payload["vote"]
    if isinstance(value, bool):
        return 1 if value else 2
    if value is None:
        return 0
    if isinstance(value, int) and value in (0, 1, 2):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"like", "up", "upvote", "true", "1"}:
            return 1
        if lowered in {"dislike", "down", "downvote", "false", "2"}:
            return 2
        if lowered in {"none", "clear", "remove", "0", ""}:
            return 0
    return None


def _set_asset_vote(
        self: web_server_handler,
        *,
        asset_id: int,
        user_id: int,
        status: int,
) -> None:
    if status == 0:
        self.server.storage.asset_vote.delete(asset_id, user_id)
        return
    self.server.storage.asset_vote.update(
        asset_id,
        user_id,
        status == 1,
    )


@server_path(r'/v1/games/(\d+)/votes/user', regex=True, commands={'GET'})
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    game_id = int(match.group(1))
    place = _resolve_place_from_game_identifier(self, game_id)
    if place is None or place.assetObj is None:
        self.send_json({"errors": [{"code": 0, "message": "Invalid placeId."}]}, 404)
        return True

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    can_vote, reason = _can_user_rate_asset(
        self,
        place.assetObj,
        current_user.id,
    )
    user_vote_status = GetUserVoteStatus(
        self,
        place.placeid,
        current_user.id,
    )
    self.send_json({
        "canVote": can_vote,
        "userVote": user_vote_status == 1,
        "userVoteStatus": user_vote_status,
        "reasonForNotVoteable": reason if not can_vote else "",
    })
    return True


@server_path(r'/v1/games/(\d+)/votes', regex=True, commands={'GET'})
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    game_id = int(match.group(1))
    place = _resolve_place_from_game_identifier(self, game_id)
    if place is None:
        self.send_json({"errors": [{"code": 0, "message": "Invalid placeId."}]}, 404)
        return True

    up_votes, down_votes = GetAssetLikesAndDislikes(
        self,
        place.placeid,
    )
    self.send_json({
        "id": game_id,
        "upVotes": up_votes,
        "downVotes": down_votes,
        "votePercentage": GetAssetVotePercentage(self, place.placeid),
    })
    return True


@server_path('/v1/games/votes', commands={'GET'})
def _(self: web_server_handler) -> bool:
    raw_universe_ids = self.query.get("universeIds", "").strip()
    if not raw_universe_ids:
        self.send_json({"data": []})
        return True

    data = []
    for raw_universe_id in raw_universe_ids.split(','):
        raw_universe_id = raw_universe_id.strip()
        if not raw_universe_id:
            continue

        try:
            universe_id = int(raw_universe_id)
        except ValueError:
            continue

        place = _resolve_place_from_game_identifier(self, universe_id)
        if place is None:
            data.append({
                "id": universe_id,
                "upVotes": 0,
                "downVotes": 0,
            })
            continue

        up_votes, down_votes = GetAssetLikesAndDislikes(
            self,
            place.placeid,
        )
        data.append({
            "id": universe_id,
            "upVotes": up_votes,
            "downVotes": down_votes,
        })

    self.send_json({"data": data})
    return True


@server_path(r'/v1/games/(\d+)/user-votes', regex=True, commands={'PATCH'})
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    payload = _read_json_body(self)
    if payload is None:
        return True

    status = _parse_vote_status(payload)
    if status is None:
        self.send_json(
            {"errors": [{"code": 0, "message": "Invalid vote value."}]},
            400,
        )
        return True

    game_id = int(match.group(1))
    place = _resolve_place_from_game_identifier(self, game_id)
    if place is None or place.assetObj is None:
        self.send_json({"errors": [{"code": 0, "message": "Invalid universeId."}]}, 404)
        return True

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    can_vote, reason = _can_user_rate_asset(
        self,
        place.assetObj,
        current_user.id,
    )
    if not can_vote:
        self.send_json(
            {"errors": [{"code": 0, "message": reason}]},
            400,
        )
        return True

    _set_asset_vote(
        self,
        asset_id=place.placeid,
        user_id=current_user.id,
        status=status,
    )
    self.send_json({"success": True})
    return True


@server_path(r'/v1/games/(\d+)/favorites/count', regex=True, commands={'GET'})
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    game_id = int(match.group(1))
    place = _resolve_place_from_game_identifier(self, game_id)
    if place is None:
        self.send_json({"errors": [{"code": 0, "message": "Invalid universeId."}]}, 404)
        return True

    self.send_json({
        "favoritesCount": GetAssetFavoriteCount(self, place.placeid),
    })
    return True


@server_path(r'/v1/games/(\d+)/favorites', regex=True, commands={'GET'})
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    game_id = int(match.group(1))
    place = _resolve_place_from_game_identifier(self, game_id)
    if place is None:
        self.send_json({"errors": [{"code": 0, "message": "Invalid universeId."}]}, 404)
        return True

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.send_json({
        "isFavorited": GetUserFavoriteStatus(
            self,
            place.placeid,
            current_user.id,
        ),
    })
    return True


@server_path(r'/v1/games/(\d+)/favorites', regex=True, commands={'POST'})
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    payload = _read_json_body(self)
    if payload is None:
        return True

    is_favorite = _parse_toggle_favorite_value(payload)
    if is_favorite is None:
        self.send_json(
            {"errors": [{"code": 0, "message": "Invalid favorite value."}]},
            400,
        )
        return True

    game_id = int(match.group(1))
    place = _resolve_place_from_game_identifier(self, game_id)
    if place is None:
        self.send_json({"errors": [{"code": 0, "message": "Invalid universeId."}]}, 404)
        return True

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.server.storage.asset_favorite.set_favorite(
        place.placeid,
        current_user.id,
        is_favorite,
    )
    self.send_json({"isFavorited": is_favorite})
    return True


@server_path(r'/vote/(\d+)/(\d+)', regex=True, commands={'POST'})
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    asset_id = int(match.group(1))
    status = int(match.group(2))
    if status not in (0, 1, 2):
        self.send_json({"errors": [{"code": 0, "message": "Invalid vote status."}]}, 400)
        return True

    asset_obj = _resolve_rate_asset(self, asset_id)
    if asset_obj is None:
        self.send_error(404)
        return True

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    can_vote, reason = _can_user_rate_asset(
        self,
        asset_obj,
        current_user.id,
    )
    if not can_vote:
        self.send_json(
            {"errors": [{"code": 0, "message": reason}]},
            400,
        )
        return True

    _set_asset_vote(
        self,
        asset_id=asset_obj.id,
        user_id=current_user.id,
        status=status,
    )
    self.send_json({"success": True})
    return True


@server_path(r'/favorite/(\d+)', regex=True, commands={'POST'})
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    asset_id = int(match.group(1))
    asset_obj = _resolve_rate_asset(self, asset_id)
    if asset_obj is None:
        self.send_error(404)
        return True

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.server.storage.asset_favorite.update(
        asset_obj.id,
        current_user.id,
    )
    self.send_json({"success": True})
    return True


@server_path(r'/favorite/(\d+)', regex=True, commands={'DELETE'})
@util.auth.authenticated_required_api
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    asset_id = int(match.group(1))
    asset_obj = _resolve_rate_asset(self, asset_id)
    if asset_obj is None:
        self.send_error(404)
        return True

    current_user = util.auth.GetCurrentUser(self)
    assert current_user is not None
    self.server.storage.asset_favorite.delete(
        asset_obj.id,
        current_user.id,
    )
    self.send_json({"success": True})
    return True


@server_path('/abuse-reporting/v1/dynamic-dialog-sequential')
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    self.send_json({"rootStepId": 0, "nodes": [{"title": "Your report has been sent.", "subtitle": "",
                                                "actionInfo": {"predefinedNextStepId": 100, "shouldSubmit": False},
                                                "stepId": 1, "internalStepName": "generic_legacy_success",
                                                "isCompletionStep": True,
                                                "innerContentConfig": {"type": "configurableComponentList",
                                                                       "configurableComponentList": {"components": [
                                                                           {"componentType": "paragraph",
                                                                            "isOptional": False,
                                                                            "requirementMessage": "", "formDataKey": "",
                                                                            "paragraph": {
                                                                                "text": "Thank you for your report. We will investigate further to determine if there has been a violation of our {terms}. For more information check out {safety}.",
                                                                                "links": {
                                                                                    "safety": {"label": "Roblox Safety",
                                                                                               "linkButtonLabel": "Read about Roblox Safety",
                                                                                               "url": "https://en.help.roblox.com/hc/en-us/categories/200213830-Parents-Safety-and-Moderation"},
                                                                                    "terms": {"label": "Terms of Use",
                                                                                              "linkButtonLabel": "View Terms of Use",
                                                                                              "url": "https://en.help.roblox.com/hc/en-us/articles/115004647846-Roblox-Terms-of-Use"}}}}]}}},
                                               {"title": "Report abuse",
                                                "subtitle": "Tell us how you think this is breaking the rules of Roblox",
                                                "actionInfo": {"actionLabel": "Submit", "predefinedNextStepId": 1,
                                                               "shouldSubmit": True}, "stepId": 0,
                                                "internalStepName": "generic_legacy_root", "isCompletionStep": False,
                                                "innerContentConfig": {"type": "configurableComponentList",
                                                                       "configurableComponentList": {"components": [
                                                                           {"componentType": "selector",
                                                                            "isOptional": True,
                                                                            "requirementMessage": "Optional",
                                                                            "formDataKey": "place_selector",
                                                                            "selector": {
                                                                                "prompt": "Please select any inappropriate media:"}},
                                                                           {"componentType": "dropdown",
                                                                            "isOptional": False,
                                                                            "requirementMessage": "You must select a category",
                                                                            "formDataKey": "abuse_category",
                                                                            "dropdown": {"prompt": "Subject:",
                                                                                         "placeholder": "Please select a category",
                                                                                         "items": [{
                                                                                                       "label": "Inappropriate Language - Profanity \u0026 Adult Content",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_INAPPROPRIATE_LANGUAGE_PROFANITY_AND_ADULT_CONTENT"},
                                                                                                   {
                                                                                                       "label": "Asking for or Giving Private Information",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_PERSONAL_QUESTION"},
                                                                                                   {
                                                                                                       "label": "Bullying, Harassment, Hate Speech",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_BULLYING"},
                                                                                                   {"label": "Dating",
                                                                                                    "formDataValue": "ABUSE_CATEGORY_DATING"},
                                                                                                   {
                                                                                                       "label": "Exploiting, Cheating, Scamming",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_EXPLOITING_CHEATING_SCAMMING"},
                                                                                                   {
                                                                                                       "label": "Account Theft - Phishing, Hacking, Trading",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_ACCOUNT_THEFT"},
                                                                                                   {
                                                                                                       "label": "Inappropriate Content - Place, Image, Model",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_INAPT_CONTENT"},
                                                                                                   {
                                                                                                       "label": "Real Life Threats \u0026 Suicide Threats",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_REAL_LIFE_THREATS_AND_SUICIDE_THREATS"},
                                                                                                   {
                                                                                                       "label": "Inaccurate Content Maturity (e.g. blood, violence)",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_INACCURATE_AGE_GUIDELINES"},
                                                                                                   {
                                                                                                       "label": "Other rule violation",
                                                                                                       "formDataValue": "ABUSE_CATEGORY_OTHER"}]}},
                                                                           {"componentType": "freeComment",
                                                                            "isOptional": True,
                                                                            "requirementMessage": "Optional",
                                                                            "formDataKey": "free_comment",
                                                                            "freeComment": {"prompt": "Comment:",
                                                                                            "placeholder": "Describe using your own words"}}]}},
                                                "footerContentConfig": {"type": "configurableComponentList",
                                                                        "configurableComponentList": {"components": [
                                                                            {"componentType": "paragraph",
                                                                             "isOptional": True,
                                                                             "requirementMessage": "",
                                                                             "formDataKey": "", "paragraph": {
                                                                                "text": "We'll review your report and take appropriate action. We won't share your information with any user you report. Reporting a user or content won't block them automatically.",
                                                                                "links": None}},
                                                                            {"componentType": "link",
                                                                             "isOptional": True,
                                                                             "requirementMessage": "",
                                                                             "formDataKey": "", "link": {
                                                                                "label": "Report illegal content under the EU Digital Services Act.",
                                                                                "linkButtonLabel": "Report illegal content under the EU Digital Services Act.",
                                                                                "url": "https://www.roblox.com/illegal-content-reporting"}}]}}}]})
    return True


@server_path('/abuse-reporting/v2/abuse-report')
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    self.send_json({"reportId": ""})
    return True