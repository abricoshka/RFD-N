import urllib.error
import urllib.request
import json

import util.auth
from web_server._logic import web_server_handler, server_path


def _query_value(self: web_server_handler, *names: str) -> str:
    for name in names:
        value = self.query.get(name)
        if value:
            return value.strip()
    return ""


def _validation_payload(self: web_server_handler) -> dict[str, object]:
    if self.command != "POST":
        return {}

    try:
        raw = self.read_content()
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}
    nested_payload = payload.get("request")
    if isinstance(nested_payload, dict):
        merged = dict(payload)
        merged.update(nested_payload)
        return merged
    return payload


def _request_value(
    self: web_server_handler,
    payload: dict[str, object],
    *names: str,
) -> str:
    for name in names:
        value = payload.get(name)
        if value is not None:
            return str(value).strip()
    return _query_value(self, *names)


@server_path('/v1/users/authenticated')
def _(self: web_server_handler) -> bool:
    return util.auth.HandleAuthenticatedUserEndpoint(self)

@server_path('/v1/users/authenticated/app-launch-info')
def _(self: web_server_handler) -> bool:
    return util.auth.HandleAuthenticatedAppLaunchInfoEndpoint(self)


@server_path('/v2/usernames/validate')
@server_path('/signup/is-username-valid', commands={'GET'})
def _(self: web_server_handler) -> bool:
    payload = _validation_payload(self)
    if (
        _request_value(self, payload, "context", "request.context") == "Signup" and
        not (
            _request_value(self, payload, "birthday", "request.birthday") or
            util.auth.GetCurrentUser(self) is not None
        )
    ):
        self.send_json({
            "errors": [{
                "code": 2,
                "message": "A valid birthday or authenticated user is required.",
            }],
        })
        return True

    username = _request_value(
        self,
        payload,
        "username",
        "value",
        "request.username",
    )
    code, message = util.auth.ValidateUsernameResult(
        self.server.storage,
        username,
    )
    self.send_json({"code": code, "message": message})
    return True


@server_path('/v2/passwords/validate')
@server_path(r'/signup/is-password-valid', commands={'GET'})
def _(self: web_server_handler) -> bool:
    payload = _validation_payload(self)
    password = _request_value(self, payload, "password", "request.password")
    username = _request_value(self, payload, "username", "request.username")
    code, message = util.auth.ValidatePasswordStringResult(
        password,
        username,
    )
    self.send_json({"code": code, "message": message})
    return True


@server_path('/v1/login')
def _(self: web_server_handler) -> bool:
    return util.auth.HandleLogin(self)


@server_path('/v2/login')
def _(self: web_server_handler) -> bool:
    return util.auth.HandleLogin(self)


@server_path('/v2/signup')
def _(self: web_server_handler) -> bool:
    return util.auth.HandleSignup(self)


@server_path('/v2/twostepverification/verify', commands={'POST'})
def _(self: web_server_handler) -> bool:
    return util.auth.HandleTwoStepVerification(self)


@server_path('/Login/NewAuthTicket', commands={'POST'})
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    return util.auth.HandleLoginNewAuthTicket(self)


@server_path('/game/logout.aspx', commands={'GET'})
@util.auth.authenticated_required
def _(self: web_server_handler) -> bool:
    return util.auth.HandleLogoutRedirect(self)


@server_path('/v1/logout', commands={'POST'})
@server_path('/v2/logout', commands={'POST'})
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    return util.auth.HandleLogoutApi(self)


@server_path('/v2/passwords/current-status', commands={'GET'})
@util.auth.authenticated_required_api
def _(self: web_server_handler) -> bool:
    return util.auth.HandlePasswordsCurrentStatus(self)


# Idk why i added auth-token-service APIs. It just looks cool.
@server_path('/auth-token-service/v1/login/create')
def _(self: web_server_handler) -> bool:
    self.send_json({
        "code": "This function is a placeholder.",
        "status": "Created",
        "privateKey": "b06e4db3-b800-471d-955d-f457a6640bb4",
        "expirationTime": "2030-04-15T14:29:00.670924",
        "imagePath": "/v1/login/qr-code-image?key=b06e4db3-b800-471d-955d-f457a6640bb4&code=W8WQ7D"
    })
    return True

@server_path('/auth-token-service/v1/login/status')
def _(self: web_server_handler) -> bool:
    self.send_json({
      "status": "Created",
      "accountName": None,
      "accountPictureUrl": None,
      "expirationTime": "2030-04-15T14:29:00.670924"
    })

    return True

@server_path('/auth-token-service/v1/login/qr-code-image')
def _(self: web_server_handler) -> bool:
    try:
        with urllib.request.urlopen("https://fbi.cults3d.com/uploaders/15082280/illustration-file/b538f0a9-04ef-42f6-8c50-d22f857e0051/Capture-d%E2%80%99%C3%A9cran-2022-12-11-125634.png", timeout=10) as response:
            self.send_data(
                response.read(),
                content_type='image/png',
            )
    except (urllib.error.HTTPError, urllib.error.URLError):
        self.send_error(502)

    return True