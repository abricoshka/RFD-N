from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import time
from functools import wraps
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any, Callable, Concatenate, ParamSpec

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error

import util.const
import util.player_cookie_store
from storage.auth_ticket import auth_ticket_item
from storage.auth_session import auth_session_item
from storage.user import user_item

if TYPE_CHECKING:
    from storage import storager
    from web_server._logic import web_server_handler


AUTH_COOKIE_NAME = ".ROBLOSECURITY"
GLOBAL_COOKIE_DOMAIN = ".rbolock.tk"
DEFAULT_TOKEN_EXPIRY = 60 * 60 * 24 * 31
DEFAULT_TICKET_EXPIRY = 60 * 10
USERNAME_ALLOWED_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 200
AUTH_TICKET_KIND_LOGIN = "login"
AUTH_TICKET_KIND_TWO_STEP = "two_step"
P = ParamSpec("P")


def _parse_cookies(cookie_header: str | None) -> dict[str, str]:
    if not cookie_header:
        return {}
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    return {
        key: morsel.value
        for key, morsel in cookie.items()
    }


def _get_cookie_value(self: web_server_handler, name: str) -> str | None:
    return _parse_cookies(self.headers.get("Cookie")).get(name)


def _build_cookie_header(
    name: str,
    value: str,
    *,
    domain: str | None = None,
    max_age: int | None = None,
    expires: str | None = None,
    secure: bool = False,
    samesite: str = "Lax",
) -> str:
    cookie = SimpleCookie()
    cookie[name] = value
    morsel = cookie[name]
    morsel["path"] = "/"
    morsel["httponly"] = True
    morsel["samesite"] = samesite
    if domain is not None:
        morsel["domain"] = domain
    if max_age is not None:
        morsel["max-age"] = str(max_age)
    if expires is not None:
        morsel["expires"] = expires
    if secure:
        morsel["secure"] = True
    return cookie.output(header="").strip()


def _uses_global_cookie_domain(self: web_server_handler) -> bool:
    domain = getattr(self, "domain", "")
    if not isinstance(domain, str) or not domain:
        return False
    root_domain = GLOBAL_COOKIE_DOMAIN.removeprefix(".")
    normalized_domain = domain.strip(".").lower()
    return (
        normalized_domain == root_domain or
        normalized_domain.endswith(f".{root_domain}")
    )


def SetAuthCookie(
    self: web_server_handler,
    token: str,
    expireIn: int = DEFAULT_TOKEN_EXPIRY,
) -> None:
    use_global_cookie_domain = _uses_global_cookie_domain(self)
    self.send_header(
        "Set-Cookie",
        _build_cookie_header(
            AUTH_COOKIE_NAME,
            token,
            domain=GLOBAL_COOKIE_DOMAIN if use_global_cookie_domain else None,
            max_age=expireIn,
            secure=use_global_cookie_domain,
            samesite="None" if use_global_cookie_domain else "Lax",
        ),
    )
    _sync_player_cookie_store(self, token)


def ClearAuthCookie(self: web_server_handler) -> None:
    use_global_cookie_domain = _uses_global_cookie_domain(self)
    self.send_header(
        "Set-Cookie",
        _build_cookie_header(
            AUTH_COOKIE_NAME,
            "",
            domain=GLOBAL_COOKIE_DOMAIN if use_global_cookie_domain else None,
            max_age=0,
            expires="Thu, 01 Jan 1970 00:00:00 GMT",
            secure=use_global_cookie_domain,
            samesite="None" if use_global_cookie_domain else "Lax",
        ),
    )
    _sync_player_cookie_store(self, None)


def _get_player_cookie_hosts(self: web_server_handler) -> set[str]:
    hosts: set[str] = set()

    raw_host = self.headers.get("Host")
    if raw_host:
        host = raw_host.rsplit(":", 1)[0]
        hosts.add(host.strip("[]"))

    domain = getattr(self, "domain", None)
    if isinstance(domain, str) and domain:
        hosts.add(domain)
        if _uses_global_cookie_domain(self):
            hosts.add(GLOBAL_COOKIE_DOMAIN)

    if "localhost" in hosts:
        hosts.add("127.0.0.1")
    if "127.0.0.1" in hosts:
        hosts.add("localhost")
    return hosts


def _sync_player_cookie_store(
    self: web_server_handler,
    token: str | None,
) -> None:
    try:
        util.player_cookie_store.sync_auth_cookie(
            _get_player_cookie_hosts(self),
            token,
        )
    except Exception:
        logging.exception("Failed to sync Roblox player cookie store")


def _get_request_token(self: web_server_handler) -> str | None:
    token = _get_cookie_value(self, AUTH_COOKIE_NAME)
    if token:
        return token

    header_token = (
        self.headers.get("X-Roblosecurity") or
        self.headers.get("X-Robloxsecurity") or
        self.headers.get("Roblosecurity")
    )
    if header_token:
        return header_token.strip()

    syntax_session = (
        _get_cookie_value(self, "Roblox-Session-Id") or
        self.headers.get("Roblox-Session-Id")
    )
    if syntax_session is None:
        return None

    data_sections = syntax_session.split("|")
    if len(data_sections) != 9:
        return None
    token = data_sections[8].strip()
    return token or None


def GetRequestToken(self: web_server_handler) -> str | None:
    return _get_request_token(self)


def _get_remote_address(self: web_server_handler) -> str:
    if not self.client_address:
        return ""
    return str(self.client_address[0])


def _read_json_object(self: web_server_handler) -> dict[str, Any]:
    raw = self.read_content()
    if not raw:
        return {}
    result = json.loads(raw.decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("JSON body must be an object")
    return result


def _extract_username(payload: dict[str, Any]) -> str:
    username = (
        payload.get("username") or
        payload.get("Username") or
        payload.get("cvalue") or
        payload.get("value")
    )
    if username is None:
        return ""
    return str(username).strip()


def _extract_password(payload: dict[str, Any]) -> str:
    password = payload.get("password") or payload.get("Password")
    if password is None:
        return ""
    return str(password)


def ValidateUsernameResult(
    storage: storager,
    username: str,
) -> tuple[int, str]:
    if not (USERNAME_MIN_LENGTH <= len(username) <= USERNAME_MAX_LENGTH):
        return (3, "Usernames can be 3 to 20 characters long")
    if username.endswith("_"):
        return (4, "Username can't end with _")
    if username.count("_") > 1:
        return (5, "Usernames can have at most one _")
    if not USERNAME_ALLOWED_PATTERN.fullmatch(username):
        return (7, "Only a-z, A-Z, 0-9, and _ are allowed")
    if storage.user.get_id_from_username(username) is not None:
        return (1, "Username is already in use")
    return (0, "Username is valid")


def ValidateUsername(
    storage: storager,
    username: str,
) -> str | None:
    code, message = ValidateUsernameResult(storage, username)
    return None if code == 0 else message


def ValidatePasswordStringResult(
    password: str,
    username: str = "",
) -> tuple[int, str]:
    if not (PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH):
        return (2, "Password must be between 8 and 200 characters long")
    if username and password.casefold() == username.casefold():
        return (3, "Password must not be your username")
    return (0, "Password is valid")


def ValidatePasswordString(
    password: str,
    username: str = "",
) -> str | None:
    code, message = ValidatePasswordStringResult(password, username)
    return None if code == 0 else message


def GetTokenInfo(
    storage: storager,
    token: str,
) -> auth_session_item | None:
    if not token:
        return None

    current_time = int(time.time())
    storage.auth_session.delete_expired(current_time)

    token_info = storage.auth_session.check_object(token)
    if token_info is None:
        return None
    if token_info.expiry < current_time:
        storage.auth_session.delete(token)
        return None
    return token_info


def ValidateToken(
    storage: storager,
    token: str,
) -> bool:
    return GetTokenInfo(storage, token) is not None


def GetAuthenticatedUser(
    storage: storager,
    token: str,
) -> user_item | None:
    auth_token_info = GetTokenInfo(storage, token)
    if auth_token_info is None:
        return None
    return storage.user.check_object(auth_token_info.user_id)


def CreateToken(
    storage: storager,
    userid: int,
    ip: str,
    expireIn: int = DEFAULT_TOKEN_EXPIRY,
) -> str:
    current_time = int(time.time())
    storage.auth_session.delete_expired(current_time)
    token = secrets.token_urlsafe(96)
    storage.auth_session.update(
        token=token,
        user_id=userid,
        created=current_time,
        expiry=current_time + expireIn,
        ip=ip,
    )
    return token


def invalidateToken(
    storage: storager,
    token: str | None,
) -> None:
    if token:
        storage.auth_session.delete(token)


def CreateTemporaryTicket(
    storage: storager,
    user_id: int,
    kind: str,
    expireIn: int = DEFAULT_TICKET_EXPIRY,
) -> str:
    current_time = int(time.time())
    storage.auth_ticket.delete_expired(current_time)
    ticket = secrets.token_urlsafe(96)
    storage.auth_ticket.update(
        ticket=ticket,
        user_id=user_id,
        kind=kind,
        created=current_time,
        expiry=current_time + expireIn,
    )
    return ticket


def GetTemporaryTicketInfo(
    storage: storager,
    ticket: str,
    kind: str,
) -> auth_ticket_item | None:
    if not ticket:
        return None

    current_time = int(time.time())
    storage.auth_ticket.delete_expired(current_time)
    ticket_info = storage.auth_ticket.check_object(ticket)
    if ticket_info is None:
        return None
    if ticket_info.kind != kind or ticket_info.expiry < current_time:
        storage.auth_ticket.delete(ticket)
        return None
    return ticket_info


def ConsumeTemporaryTicket(
    storage: storager,
    ticket: str,
    kind: str,
) -> auth_ticket_item | None:
    ticket_info = GetTemporaryTicketInfo(storage, ticket, kind)
    if ticket_info is None:
        return None
    storage.auth_ticket.delete(ticket)
    return ticket_info


def CreateAuthTicket(
    storage: storager,
    user_id: int,
    expireIn: int = DEFAULT_TICKET_EXPIRY,
) -> str:
    return CreateTemporaryTicket(
        storage,
        user_id,
        AUTH_TICKET_KIND_LOGIN,
        expireIn,
    )


def ConsumeAuthTicket(
    storage: storager,
    ticket: str,
) -> auth_ticket_item | None:
    return ConsumeTemporaryTicket(
        storage,
        ticket,
        AUTH_TICKET_KIND_LOGIN,
    )


def CreateTwoStepTicket(
    storage: storager,
    user_id: int,
    expireIn: int = DEFAULT_TICKET_EXPIRY,
) -> str:
    return CreateTemporaryTicket(
        storage,
        user_id,
        AUTH_TICKET_KIND_TWO_STEP,
        expireIn,
    )


def ConsumeTwoStepTicket(
    storage: storager,
    ticket: str,
) -> auth_ticket_item | None:
    return ConsumeTemporaryTicket(
        storage,
        ticket,
        AUTH_TICKET_KIND_TWO_STEP,
    )


def isAuthenticated(self: web_server_handler) -> bool:
    token = _get_request_token(self)
    if token is None:
        return False
    return ValidateToken(self.server.storage, token)


def GetCurrentUser(self: web_server_handler) -> user_item | None:
    cache_attr = "_current_authenticated_user"
    if hasattr(self, cache_attr):
        return getattr(self, cache_attr)

    token = _get_request_token(self)
    user = None
    if token is not None:
        user = GetAuthenticatedUser(self.server.storage, token)
        if user is not None:
            _sync_player_cookie_store(self, token)

    setattr(self, cache_attr, user)
    return user


def GetUserPayload(user: user_item) -> dict[str, int | str]:
    return {
        "id": user.id,
        "name": user.username,
        "displayName": user.username,
    }


def GetAuthenticatedAppLaunchInfoPayload(user: user_item) -> dict[str, object]:
    return {
        "ageBracket": 0,
        "countryCode": "US",
        "isPremium": user.is_premium,
        "hasRobloxSubscription": False,
        **GetUserPayload(user),
    }


def _send_api_auth_error(
    self: web_server_handler,
    *,
    message: str = "Authentication cookie is empty",
    clear_cookie: bool = False,
) -> None:
    self.send_response(401)
    if clear_cookie:
        ClearAuthCookie(self)
    self.send_json({"errors":[{"code":0,"message":message}]}, status=None)


def _send_redirect_to_login(
    self: web_server_handler,
    *,
    clear_cookie: bool = False,
) -> None:
    self.send_response(301)
    if clear_cookie:
        ClearAuthCookie(self)
    self.send_header("Location", "/login")
    self.end_headers()


def authenticated_required(
    f: Callable[Concatenate[web_server_handler, P], bool],
) -> Callable[Concatenate[web_server_handler, P], bool]:
    @wraps(f)
    def decorated_function(
        self: web_server_handler,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> bool:
        token = _get_request_token(self)
        if token is None:
            _send_redirect_to_login(self)
            return True
        if not ValidateToken(self.server.storage, token):
            _send_redirect_to_login(self, clear_cookie=True)
            return True
        return f(self, *args, **kwargs)

    return decorated_function


def authenticated_required_api(
    f: Callable[Concatenate[web_server_handler, P], bool],
) -> Callable[Concatenate[web_server_handler, P], bool]:
    @wraps(f)
    def decorated_function(
        self: web_server_handler,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> bool:
        token = _get_request_token(self)
        if token is None:
            _send_api_auth_error(self, message="You are not logged in")
            return True
        if not ValidateToken(self.server.storage, token):
            _send_api_auth_error(
                self,
                message="You are not logged in",
                clear_cookie=True,
            )
            return True
        return f(self, *args, **kwargs)

    return decorated_function


def authenticated_client_endpoint(
    f: Callable[Concatenate[web_server_handler, P], bool],
) -> Callable[Concatenate[web_server_handler, P], bool]:
    @wraps(f)
    def decorated_function(
        self: web_server_handler,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> bool:
        syntax_session = (
            _get_cookie_value(self, "Syntax-Session-Id") or
            self.headers.get("Syntax-Session-Id")
        )
        if syntax_session is None:
            self.send_json({"success": False, "error": "Missing Headers"}, 401)
            return True

        data_sections = syntax_session.split("|")
        if len(data_sections) != 9:
            self.send_json({"success": False, "error": "Invalid Headers"}, 401)
            return True

        auth_token = data_sections[8].strip()
        if not ValidateToken(self.server.storage, auth_token):
            self.send_json({"success": False, "error": "Invalid Token"}, 401)
            return True

        return f(self, *args, **kwargs)

    return decorated_function


def gameserver_authenticated_required(
    f: Callable[Concatenate[web_server_handler, P], bool],
) -> Callable[Concatenate[web_server_handler, P], bool]:
    @wraps(f)
    def decorated_function(
        self: web_server_handler,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> bool:
        if "Roblox/" not in self.headers.get("User-Agent", ""):
            self.send_error(404)
            return True
        if not self.is_privileged:
            self.send_error(404)
            return True

        requester_access_key = self.headers.get("AccessKey", "")
        if "UserRequest" in requester_access_key:
            logging.warning(
                "GameServer %s - UserRequest access key used for %s",
                _get_remote_address(self),
                self.url,
            )
            self.send_error(404)
            return True

        return f(self, *args, **kwargs)

    return decorated_function


def gameserver_accesskey_required(
    f: Callable[Concatenate[web_server_handler, P], bool],
) -> Callable[Concatenate[web_server_handler, P], bool]:
    @wraps(f)
    def decorated_function(
        self: web_server_handler,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> bool:
        requester_access_key = self.headers.get("AccessKey")
        if not self.is_privileged or requester_access_key != util.const.SESSION_KEY:
            self.send_error(404)
            return True
        return f(self, *args, **kwargs)

    return decorated_function


def Validate2FACode(
    storage: storager,
    userid: int,
    code: str,
) -> bool:
    if not code:
        return False
    user = storage.user.check_object(userid)
    if user is None or not user.TOTPEnabled:
        return False

    logging.warning(
        "TOTP validation requested for user %s, but TOTP is not implemented in this project",
        userid,
    )
    return False


def _GetArgonSalt(UserObj: user_item) -> bytes:
    return hashlib.sha256(
        f"{util.const.SESSION_KEY}:{UserObj.id}".encode("utf-8"),
    ).digest()[:16]


def _GetPasswordHasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=16,
        memory_cost=2 ** 14,
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )


def VerifyPassword(
    storage: storager,
    UserObj: user_item,
    password: str,
) -> bool:
    argon_ph = _GetPasswordHasher()
    if not UserObj.password.startswith("$argon2"):
        is_correct = (
            hashlib.sha512(password.encode("utf-8")).hexdigest() ==
            UserObj.password
        )
        if is_correct:
            UserObj.password = argon_ph.hash(
                password,
                salt=_GetArgonSalt(UserObj),
            )
            storage.user.set_password(UserObj.id, UserObj.password)
            logging.info(
                "User %s [%s] migrated to argon2 password hash",
                UserObj.username,
                UserObj.id,
            )
        return is_correct

    try:
        is_correct = argon_ph.verify(UserObj.password, password)
    except Argon2Error:
        return False

    if is_correct and argon_ph.check_needs_rehash(UserObj.password):
        UserObj.password = argon_ph.hash(
            password,
            salt=_GetArgonSalt(UserObj),
        )
        storage.user.set_password(UserObj.id, UserObj.password)
    return is_correct


def SetPassword(
    storage: storager,
    UserObj: user_item,
    password: str,
) -> bool:
    argon_ph = _GetPasswordHasher()
    UserObj.password = argon_ph.hash(
        password,
        salt=_GetArgonSalt(UserObj),
    )
    storage.user.set_password(UserObj.id, UserObj.password)
    return True


def CreateUser(
    storage: storager,
    username: str,
    password: str,
) -> user_item | None:
    username_error = ValidateUsername(storage, username)
    if username_error is not None:
        return None
    password_error = ValidatePasswordString(password, username)
    if password_error is not None:
        return None

    user_id = storage.user.update(
        username=username,
        password="!",
    )
    user = storage.user.check_object(user_id)
    if user is None:
        return None

    SetPassword(storage, user, password)
    if storage.funds.check(user_id) is None:
        storage.funds.first_init(user_id, 0)
    return storage.user.check_object(user_id)


def HandleAuthenticatedUserEndpoint(self: web_server_handler) -> bool:
    token = _get_request_token(self)
    if token is None:
        _send_api_auth_error(self)
        return True

    user = GetCurrentUser(self)
    if user is None:
        _send_api_auth_error(self, clear_cookie=True)
        return True

    self.send_json(GetUserPayload(user))
    return True


def HandleAuthenticatedAppLaunchInfoEndpoint(
    self: web_server_handler,
) -> bool:
    token = _get_request_token(self)
    if token is None:
        _send_api_auth_error(self)
        return True

    user = GetCurrentUser(self)
    if user is None:
        _send_api_auth_error(self, clear_cookie=True)
        return True

    self.send_json(GetAuthenticatedAppLaunchInfoPayload(user))
    return True


def HandleLogin(self: web_server_handler) -> bool:
    try:
        payload = _read_json_object(self)
    except Exception:
        self.send_json(
            {"errors": [{"code": 0, "message": "Malformed JSON body"}]},
            400,
        )
        return True

    username = _extract_username(payload)
    password = _extract_password(payload)
    if not username or not password:
        self.send_json(
            {"errors": [{"code": 0, "message": "Username and password are required"}]},
            400,
        )
        return True

    storage = self.server.storage
    user = storage.user.check_object_from_username(username)
    if user is None or not VerifyPassword(storage, user, password):
        self.send_response(401)
        ClearAuthCookie(self)
        self.send_json(
            {"errors": [{"code": 0, "message": "Invalid username or password"}]},
            status=None,
        )
        return True

    if user.accountstatus <= 0:
        self.send_json(
            {"errors": [{"code": 0, "message": "User is not active"}], "isBanned": True},
            403,
        )
        return True

    storage.user.update_lastonline(user.id)
    token = CreateToken(
        storage,
        user.id,
        _get_remote_address(self),
    )

    self.send_response(200)
    SetAuthCookie(self, token)
    self.send_json(
        {
            "user": GetUserPayload(user),
            "isBanned": False,
        },
        status=None,
    )
    return True


def HandleSignup(self: web_server_handler) -> bool:
    try:
        payload = _read_json_object(self)
    except Exception:
        self.send_json(
            {"errors": [{"code": 0, "message": "Malformed JSON body"}]},
            400,
        )
        return True

    username = _extract_username(payload)
    password = _extract_password(payload)
    if not username or not password:
        self.send_json(
            {"errors": [{"code": 0, "message": "Username and password are required"}]},
            400,
        )
        return True

    storage = self.server.storage
    username_error = ValidateUsername(storage, username)
    if username_error is not None:
        self.send_json(
            {"errors": [{"code": 0, "message": username_error}]},
            409,
        )
        return True

    password_error = ValidatePasswordString(password, username)
    if password_error is not None:
        self.send_json(
            {"errors": [{"code": 0, "message": password_error}]},
            400,
        )
        return True

    user = CreateUser(storage, username, password)
    if user is None:
        self.send_json(
            {"errors": [{"code": 0, "message": "Failed to create user"}]},
            500,
        )
        return True

    token = CreateToken(
        storage,
        user.id,
        _get_remote_address(self),
    )

    self.send_response(200)
    SetAuthCookie(self, token)
    self.send_json(
        {
            "user": GetUserPayload(user),
            "isBanned": False,
        },
        status=None,
    )
    return True


def HandleLoginNegotiate(self: web_server_handler) -> bool:
    auth_ticket = self.query.get("suggest", "")
    ticket_info = ConsumeAuthTicket(self.server.storage, auth_ticket)
    if ticket_info is None:
        self.send_data("Invalid request", status=400, content_type="text/plain")
        return True

    user = self.server.storage.user.check_object(ticket_info.user_id)
    if user is None or user.accountstatus <= 0:
        self.send_data("Invalid request", status=400, content_type="text/plain")
        return True

    new_auth_token = CreateToken(
        self.server.storage,
        user.id,
        _get_remote_address(self),
    )
    self.send_response(200)
    self.send_header("Content-Type", "text/plain")
    SetAuthCookie(self, new_auth_token)
    self.send_data(new_auth_token, status=None)
    return True


def HandleLoginNewAuthTicket(self: web_server_handler) -> bool:
    current_user = GetCurrentUser(self)
    if current_user is None:
        _send_api_auth_error(self, message="You are not logged in")
        return True

    auth_ticket = CreateAuthTicket(
        self.server.storage,
        current_user.id,
    )
    self.send_data(auth_ticket, content_type="text/plain")
    return True


def HandleLogoutApi(self: web_server_handler) -> bool:
    token = _get_request_token(self)
    invalidateToken(self.server.storage, token)
    self.send_response(200)
    ClearAuthCookie(self)
    self.send_json({}, status=None)
    return True


def HandleLogoutRedirect(self: web_server_handler) -> bool:
    token = _get_request_token(self)
    invalidateToken(self.server.storage, token)
    self.send_response(301)
    ClearAuthCookie(self)
    self.send_header("Location", "/login")
    self.end_headers()
    return True


def HandlePasswordsCurrentStatus(self: web_server_handler) -> bool:
    self.send_json({"valid": True})
    return True


def HandleTwoStepVerification(self: web_server_handler) -> bool:
    try:
        payload = _read_json_object(self)
    except Exception:
        self.send_json(
            {"errors": [{"code": 1, "message": "Invalid request."}]},
            400,
        )
        return True

    try:
        username = payload["username"]
        code = payload["code"]
        ticket = payload["ticket"]
        assert isinstance(username, str), "Invalid parameter type: username, expected string"
        assert isinstance(ticket, str), "Invalid parameter type: ticket, expected string"
        assert isinstance(code, (str, int)), "Invalid parameter type: code, expected string or integer"
    except Exception as e:
        self.send_json(
            {"errors": [{"code": 1, "message": f"Validation failed, {str(e)}"}]},
            400,
        )
        return True

    ticket_info = ConsumeTwoStepTicket(
        self.server.storage,
        ticket,
    )
    if ticket_info is None:
        self.send_json(
            {"errors": [{"code": 5, "message": "Invalid two step verification ticket."}]},
            400,
        )
        return True

    user = self.server.storage.user.check_object(ticket_info.user_id)
    if user is None or user.username.lower() != username.lower():
        self.send_json(
            {"errors": [{"code": 5, "message": "Invalid two step verification ticket."}]},
            400,
        )
        return True

    if not Validate2FACode(self.server.storage, user.id, str(code)):
        self.send_json(
            {"errors": [{"code": 6, "message": "The code is invalid."}]},
            400,
        )
        return True

    session_token = CreateToken(
        storage=self.server.storage,
        userid=user.id,
        ip=_get_remote_address(self),
    )
    self.send_response(200)
    SetAuthCookie(self, session_token)
    self.send_json({}, status=None)
    return True
