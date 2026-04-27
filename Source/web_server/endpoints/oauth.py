from __future__ import annotations

import base64
from datetime import UTC, datetime
from functools import cache
import hashlib
import html
import json
from pathlib import Path
import secrets
import time
from urllib import parse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from storage.user import user_item
import util.auth
from web_server._logic import server_path, web_server_handler


GLOBAL_COOKIE_DOMAIN = ".rbolock.tk"
DEFAULT_SCOPE = "age credentials openid premium profile roles"
DEFAULT_OAUTH_CLIENT_ID = "7968549422692352298"
OAUTH_ISSUER = "https://rbolock.tk/oauth/"
AUTH_CODE_KIND = "oauth_code"
REFRESH_TOKEN_KIND = "oauth_refresh"
AUTH_CODE_EXPIRY = 60 * 10
REFRESH_TOKEN_EXPIRY = 60 * 60 * 24 * 365
ACCESS_TOKEN_EXPIRY = util.auth.DEFAULT_TOKEN_EXPIRY
AUTH_FORM_FIELDS = (
    "redirect_uri",
    "state",
    "client_id",
    "scope",
    "nonce",
    "response_type",
    "code_challenge",
    "code_challenge_method",
)
OAUTH_SIGNING_KEY_PATH = (
    Path(__file__).resolve().parents[2] /
    "ssl" /
    "oauth-es256-private.pem"
)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@cache
def _get_oauth_private_key() -> ec.EllipticCurvePrivateKey:
    OAUTH_SIGNING_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OAUTH_SIGNING_KEY_PATH.exists():
        with open(OAUTH_SIGNING_KEY_PATH, "rb") as file:
            private_key = serialization.load_pem_private_key(
                file.read(),
                password=None,
            )
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise TypeError("OAuth signing key must be an EC private key")
        return private_key

    private_key = ec.generate_private_key(ec.SECP256R1())
    with open(OAUTH_SIGNING_KEY_PATH, "wb") as file:
        file.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    return private_key


@cache
def _get_oauth_key_id() -> str:
    public_key = _get_oauth_private_key().public_key()
    public_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _b64url_encode(hashlib.sha256(public_der).digest()[:12])


def _build_jwks_payload() -> dict[str, list[dict[str, str]]]:
    public_numbers = _get_oauth_private_key().public_key().public_numbers()
    return {
        "keys": [{
            "kty": "EC",
            "crv": "P-256",
            "kid": _get_oauth_key_id(),
            "use": "sig",
            "alg": "ES256",
            "x": _b64url_encode(public_numbers.x.to_bytes(32, "big")),
            "y": _b64url_encode(public_numbers.y.to_bytes(32, "big")),
        }],
    }


def _sign_jwt(payload: dict[str, object]) -> str:
    header = {
        "alg": "ES256",
        "kid": _get_oauth_key_id(),
        "typ": "JWT",
    }
    encoded_header = _b64url_encode(
        json.dumps(
            header,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    encoded_payload = _b64url_encode(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    der_signature = _get_oauth_private_key().sign(
        signing_input,
        ec.ECDSA(hashes.SHA256()),
    )
    r_value, s_value = decode_dss_signature(der_signature)
    raw_signature = (
        r_value.to_bytes(32, "big") +
        s_value.to_bytes(32, "big")
    )
    return f"{encoded_header}.{encoded_payload}.{_b64url_encode(raw_signature)}"


def _get_remote_address(self: web_server_handler) -> str:
    if not self.client_address:
        return ""
    return str(self.client_address[0])


def _get_request_values(self: web_server_handler) -> dict[str, str]:
    values = dict(self.query)
    if self.command != "POST":
        return values

    raw_body = self.read_content()
    if not raw_body:
        return values

    form_values = dict(parse.parse_qsl(
        raw_body.decode("utf-8"),
        keep_blank_values=True,
    ))
    values.update(form_values)
    return values


def _get_bearer_token(self: web_server_handler) -> str | None:
    auth_header = self.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def _get_oauth_token(self: web_server_handler) -> str | None:
    return _get_bearer_token(self) or util.auth.GetRequestToken(self)


def _send_auth_cookie(
    self: web_server_handler,
    token: str,
    *,
    max_age: int = ACCESS_TOKEN_EXPIRY,
) -> None:
    self.send_header(
        "Set-Cookie",
        (
            f".ROBLOSECURITY={token}; "
            f"Path=/; Domain={GLOBAL_COOKIE_DOMAIN}; Max-Age={max_age}; "
            "HttpOnly; Secure; SameSite=None"
        ),
    )


def _clear_auth_cookie(self: web_server_handler) -> None:
    self.send_header(
        "Set-Cookie",
        (
            ".ROBLOSECURITY=; "
            f"Path=/; Domain={GLOBAL_COOKIE_DOMAIN}; Max-Age=0; "
            "Expires=Thu, 01 Jan 1970 00:00:00 GMT; "
            "HttpOnly; Secure; SameSite=None"
        ),
    )


def _send_oauth_error(
    self: web_server_handler,
    *,
    error: str,
    description: str,
    status: int,
) -> None:
    self.send_json({
        "error": error,
        "error_description": description,
    }, status)


def _parse_created_timestamp(value: str) -> int:
    try:
        created_at = datetime.fromisoformat(value)
    except ValueError:
        return 0

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    else:
        created_at = created_at.astimezone(UTC)
    return int(created_at.timestamp())


def _build_userinfo_payload(user: user_item) -> dict[str, object]:
    return {
        "sub": str(user.id),
        "name": user.username,
        "nickname": user.username,
        "preferred_username": user.username,
        "created_at": _parse_created_timestamp(user.created),
        "profile": f"https://www.rbolock.tk/users/{user.id}/profile",
        "picture": (
            "https://www.rbolock.tk/headshot-thumbnail/image?"
            f"userId={user.id}&x=150&y=150"
        ),
        "age_bracket": "Age13OrOver",
        "premium": user.is_premium,
        "roles": [],
        "internal_user": False,
    }


def _build_token_payload(
    access_token: str,
    refresh_token: str,
    *,
    scope: str,
) -> dict[str, object]:
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_EXPIRY,
        "id_token": access_token,
        "scope": scope,
    }


def _render_authorize_page(
    values: dict[str, str],
    *,
    username: str = "",
    error_message: str = "",
) -> str:
    hidden_fields = []
    for field_name in AUTH_FORM_FIELDS:
        field_value = values.get(field_name, "")
        hidden_fields.append(
            '<input type="hidden" name="%s" value="%s">' % (
                html.escape(field_name, quote=True),
                html.escape(field_value, quote=True),
            )
        )

    error_block = ""
    if error_message:
        error_block = (
            '<p class="error">%s</p>' %
            html.escape(error_message)
        )

    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rbolock Sign In</title>
    <style>
        :root {
            color-scheme: dark;
            --bg: #0d1117;
            --panel: #161b22;
            --accent: #238636;
            --accent-hover: #2ea043;
            --border: #30363d;
            --text: #e6edf3;
            --muted: #8b949e;
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            background:
                radial-gradient(circle at top, rgba(35, 134, 54, 0.16), transparent 34%%),
                linear-gradient(180deg, #090b10 0%%, var(--bg) 100%%);
            color: var(--text);
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            padding: 24px;
        }

        .panel {
            width: min(420px, 100%%);
            background: rgba(22, 27, 34, 0.96);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 28px;
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.35);
        }

        h1 {
            margin: 0 0 10px;
            font-size: 28px;
        }

        p {
            margin: 0 0 18px;
            color: var(--muted);
            line-height: 1.5;
        }

        label {
            display: block;
            margin: 0 0 8px;
            font-size: 14px;
            color: var(--muted);
        }

        input {
            width: 100%%;
            margin: 0 0 16px;
            padding: 12px 14px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: #0d1117;
            color: var(--text);
            font-size: 16px;
        }

        input:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(35, 134, 54, 0.2);
        }

        button {
            width: 100%%;
            border: 0;
            border-radius: 10px;
            padding: 12px 14px;
            background: var(--accent);
            color: white;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
        }

        button:hover {
            background: var(--accent-hover);
        }

        .error {
            margin: 0 0 16px;
            padding: 12px 14px;
            border-radius: 10px;
            background: rgba(248, 81, 73, 0.12);
            border: 1px solid rgba(248, 81, 73, 0.35);
            color: #ffb1ac;
        }

        .hint {
            margin-top: 14px;
            font-size: 13px;
            color: var(--muted);
        }
    </style>
</head>
<body>
    <main class="panel">
        <h1>Sign in to Rbolock</h1>
        <p>Enter your account credentials to continue the OAuth authorization flow.</p>
        %s
        <form method="post" action="/oauth/v1/authorize">
            %s
            <label for="username">Username</label>
            <input id="username" name="username" type="text" autocomplete="username" value="%s" required>
            <label for="password">Password</label>
            <input id="password" name="password" type="password" autocomplete="current-password" required>
            <button type="submit">Continue</button>
        </form>
        <p class="hint">The authorization code will be returned to the redirect URI supplied by the client.</p>
    </main>
</body>
</html>
""" % (
        error_block,
        "\n            ".join(hidden_fields),
        html.escape(username, quote=True),
    )


def _build_redirect_url(
    redirect_uri: str,
    *,
    code: str,
    state: str,
) -> str:
    split_url = parse.urlsplit(redirect_uri)
    query_params = parse.parse_qsl(
        split_url.query,
        keep_blank_values=True,
    )
    query_params.append(("code", code))
    if state:
        query_params.append(("state", state))
    return parse.urlunsplit((
        split_url.scheme,
        split_url.netloc,
        split_url.path,
        parse.urlencode(query_params),
        split_url.fragment,
    ))


def _render_redirect_page(redirect_url: str) -> str:
    escaped_url = html.escape(redirect_url, quote=True)
    redirect_json = json.dumps(redirect_url)
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Redirecting</title>
</head>
<body style="margin:0;display:grid;place-items:center;min-height:100vh;background:#0d1117;color:#e6edf3;font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif">
    <main style="max-width:520px;padding:28px;text-align:center;border:1px solid #30363d;border-radius:16px;background:#161b22">
        <h1 style="margin-top:0">Authorization complete</h1>
        <p style="line-height:1.5;color:#8b949e">The browser is redirecting back to the client application.</p>
        <p><a href="%s" style="color:#58a6ff;word-break:break-all">%s</a></p>
    </main>
    <script>
        window.location.replace(%s);
    </script>
</body>
</html>
""" % (
        escaped_url,
        escaped_url,
        redirect_json,
    )


def _get_authorization_code_store(
    self: web_server_handler,
) -> dict[str, dict[str, str]]:
    store = getattr(self.server, "oauth_authorization_codes", None)
    if store is None:
        store = {}
        self.server.oauth_authorization_codes = store
    return store


def _store_authorization_code_metadata(
    self: web_server_handler,
    code: str,
    values: dict[str, str],
) -> None:
    _get_authorization_code_store(self)[code] = {
        field_name: values.get(field_name, "")
        for field_name in AUTH_FORM_FIELDS
    }


def _pop_authorization_code_metadata(
    self: web_server_handler,
    code: str,
) -> dict[str, str] | None:
    return _get_authorization_code_store(self).pop(code, None)


def _validate_code_exchange(
    request_values: dict[str, str],
    metadata: dict[str, str],
) -> tuple[bool, str]:
    expected_redirect_uri = metadata.get("redirect_uri", "")
    supplied_redirect_uri = request_values.get("redirect_uri", "")
    if supplied_redirect_uri and expected_redirect_uri and supplied_redirect_uri != expected_redirect_uri:
        return (False, "redirect_uri does not match the authorization request.")

    expected_client_id = metadata.get("client_id", "")
    supplied_client_id = request_values.get("client_id", "")
    if supplied_client_id and expected_client_id and supplied_client_id != expected_client_id:
        return (False, "client_id does not match the authorization request.")

    expected_challenge = metadata.get("code_challenge", "")
    supplied_verifier = request_values.get("code_verifier", "")
    if supplied_verifier and expected_challenge:
        method = metadata.get("code_challenge_method", "") or "plain"
        if method == "S256":
            actual_challenge = _b64url_encode(
                hashlib.sha256(supplied_verifier.encode("utf-8")).digest()
            )
        else:
            actual_challenge = supplied_verifier
        if not secrets.compare_digest(actual_challenge, expected_challenge):
            return (False, "code_verifier is invalid.")

    return (True, "")


def _build_oauth_claims(
    user: user_item,
    *,
    scope: str,
    client_id: str,
    nonce: str,
) -> dict[str, object]:
    current_time = int(time.time())
    claims = _build_userinfo_payload(user)
    claims.update({
        "nonce": nonce,
        "jti": f"ID.{secrets.token_urlsafe(16)}",
        "nbf": current_time,
        "exp": current_time + ACCESS_TOKEN_EXPIRY,
        "iat": current_time,
        "iss": OAUTH_ISSUER,
        "aud": client_id or DEFAULT_OAUTH_CLIENT_ID,
        "scope": scope,
    })
    return claims


def _create_oauth_access_token(
    self: web_server_handler,
    user: user_item,
    *,
    scope: str,
    client_id: str,
    nonce: str,
) -> str:
    claims = _build_oauth_claims(
        user,
        scope=scope,
        client_id=client_id,
        nonce=nonce,
    )
    access_token = _sign_jwt(claims)
    self.server.storage.auth_session.delete_expired(claims["iat"])
    self.server.storage.auth_session.update(
        token=access_token,
        user_id=user.id,
        created=claims["iat"],
        expiry=claims["exp"],
        ip=_get_remote_address(self),
    )
    return access_token


def _issue_token_pair(
    self: web_server_handler,
    user: user_item,
    *,
    scope: str,
    client_id: str,
    nonce: str,
) -> None:
    access_token = _create_oauth_access_token(
        self,
        user,
        scope=scope,
        client_id=client_id,
        nonce=nonce,
    )
    refresh_token = util.auth.CreateTemporaryTicket(
        self.server.storage,
        user.id,
        REFRESH_TOKEN_KIND,
        expireIn=REFRESH_TOKEN_EXPIRY,
    )

    self.send_response(200)
    _send_auth_cookie(self, access_token, max_age=ACCESS_TOKEN_EXPIRY)
    self.send_json(
        _build_token_payload(
            access_token,
            refresh_token,
            scope=scope,
        ),
        status=None,
    )


@server_path('/oauth/.well-known/openid-configuration')
def _(self: web_server_handler) -> bool:
    self.send_json({
        "issuer": OAUTH_ISSUER,
        "authorization_endpoint": "https://rbolock.tk/oauth/v1/authorize",
        "token_endpoint": "https://rbolock.tk/oauth/v1/token",
        "introspection_endpoint": "https://rbolock.tk/oauth/v1/token/introspect",
        "revocation_endpoint": "https://rbolock.tk/oauth/v1/token/revoke",
        "resources_endpoint": "https://rbolock.tk/oauth/v1/token/resources",
        "userinfo_endpoint": "https://rbolock.tk/oauth/v1/userinfo",
        "jwks_uri": "https://rbolock.tk/oauth/v1/certs",
        "registration_endpoint": "https://create.roblox.com/dashboard/credentials",
        "service_documentation": "https://create.roblox.com/docs/reference/cloud",
        "scopes_supported": [
            "openid",
            "profile",
            "email",
            "verification",
            "credentials",
            "age",
            "premium",
            "roles",
        ],
        "response_types_supported": ["none", "code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["ES256"],
        "claims_supported": [
            "sub",
            "type",
            "iss",
            "aud",
            "exp",
            "iat",
            "nonce",
            "name",
            "nickname",
            "preferred_username",
            "created_at",
            "profile",
            "picture",
            "email",
            "email_verified",
            "verified",
            "age_bracket",
            "premium",
            "roles",
            "internal_user",
        ],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post",
            "client_secret_basic",
        ],
    })
    return True


@server_path('/oauth/v1/certs')
def _(self: web_server_handler) -> bool:
    self.send_json(_build_jwks_payload())
    return True


@server_path('/oauth/v1/userinfo')
def _(self: web_server_handler) -> bool:
    access_token = _get_oauth_token(self)
    if access_token is None:
        _send_oauth_error(
            self,
            error="invalid_token",
            description="Missing access token.",
            status=401,
        )
        return True

    user = util.auth.GetAuthenticatedUser(self.server.storage, access_token)
    if user is None:
        _send_oauth_error(
            self,
            error="invalid_token",
            description="The supplied access token is invalid or expired.",
            status=401,
        )
        return True

    self.send_json(_build_userinfo_payload(user))
    return True


@server_path('/oauth/v1/token', commands={'GET', 'POST'})
def _(self: web_server_handler) -> bool:
    values = _get_request_values(self)
    grant_type = values.get("grant_type", "").strip()
    if not grant_type and values.get("code"):
        grant_type = "authorization_code"

    if grant_type == "authorization_code":
        auth_code = values.get("code", "").strip()
        if not auth_code:
            _send_oauth_error(
                self,
                error="invalid_request",
                description="Missing authorization code.",
                status=400,
            )
            return True

        metadata = _pop_authorization_code_metadata(self, auth_code)
        ticket_info = util.auth.ConsumeTemporaryTicket(
            self.server.storage,
            auth_code,
            AUTH_CODE_KIND,
        )
        if ticket_info is None or metadata is None:
            _send_oauth_error(
                self,
                error="invalid_grant",
                description="Authorization code is invalid or expired.",
                status=400,
            )
            return True

        is_valid_exchange, validation_error = _validate_code_exchange(
            values,
            metadata,
        )
        if not is_valid_exchange:
            _send_oauth_error(
                self,
                error="invalid_grant",
                description=validation_error,
                status=400,
            )
            return True

        user = self.server.storage.user.check_object(ticket_info.user_id)
        if user is None or user.accountstatus <= 0:
            _send_oauth_error(
                self,
                error="invalid_grant",
                description="The authorization code does not resolve to an active user.",
                status=400,
            )
            return True

        _issue_token_pair(
            self,
            user,
            scope=metadata.get("scope", DEFAULT_SCOPE) or DEFAULT_SCOPE,
            client_id=metadata.get("client_id", ""),
            nonce=metadata.get("nonce", ""),
        )
        return True

    if grant_type == "refresh_token":
        refresh_token = values.get("refresh_token", "").strip()
        if not refresh_token:
            _send_oauth_error(
                self,
                error="invalid_request",
                description="Missing refresh token.",
                status=400,
            )
            return True

        ticket_info = util.auth.ConsumeTemporaryTicket(
            self.server.storage,
            refresh_token,
            REFRESH_TOKEN_KIND,
        )
        if ticket_info is None:
            _send_oauth_error(
                self,
                error="invalid_grant",
                description="Refresh token is invalid or expired.",
                status=400,
            )
            return True

        user = self.server.storage.user.check_object(ticket_info.user_id)
        if user is None or user.accountstatus <= 0:
            _send_oauth_error(
                self,
                error="invalid_grant",
                description="The refresh token does not resolve to an active user.",
                status=400,
            )
            return True

        _issue_token_pair(
            self,
            user,
            scope=values.get("scope", DEFAULT_SCOPE) or DEFAULT_SCOPE,
            client_id=values.get("client_id", DEFAULT_OAUTH_CLIENT_ID),
            nonce="",
        )
        return True

    _send_oauth_error(
        self,
        error="unsupported_grant_type",
        description="Expected authorization_code or refresh_token.",
        status=400,
    )
    return True


@server_path('/oauth/v1/token/revoke', commands={'GET', 'POST'})
def _(self: web_server_handler) -> bool:
    values = _get_request_values(self)
    token = values.get("token", "").strip() or _get_oauth_token(self)
    if token:
        util.auth.invalidateToken(self.server.storage, token)
        self.server.storage.auth_ticket.delete(token)
        _get_authorization_code_store(self).pop(token, None)

    self.send_response(200)
    _clear_auth_cookie(self)
    self.send_json({"success": True}, status=None)
    return True


@server_path('/oauth/v1/token/introspect', commands={'GET', 'POST'})
def _(self: web_server_handler) -> bool:
    values = _get_request_values(self)
    token = values.get("token", "").strip() or _get_oauth_token(self)
    if not token:
        self.send_json({"active": False})
        return True

    token_info = util.auth.GetTokenInfo(self.server.storage, token)
    if token_info is not None:
        self.send_json({
            "active": True,
            "token_type": "Bearer",
            "scope": DEFAULT_SCOPE,
            "sub": str(token_info.user_id),
            "iat": token_info.created,
            "exp": token_info.expiry,
        })
        return True

    refresh_info = util.auth.GetTemporaryTicketInfo(
        self.server.storage,
        token,
        REFRESH_TOKEN_KIND,
    )
    if refresh_info is not None:
        self.send_json({
            "active": True,
            "token_type": "refresh_token",
            "scope": DEFAULT_SCOPE,
            "sub": str(refresh_info.user_id),
            "iat": refresh_info.created,
            "exp": refresh_info.expiry,
        })
        return True

    self.send_json({
        "active": False,
    })
    return True


@server_path('/oauth/v1/token/resources', commands={'GET', 'POST'})
def _(self: web_server_handler) -> bool:
    self.send_json({
        "resource_infos": [],
    })
    return True


@server_path('/oauth/v1/authorize')
def _(self: web_server_handler) -> bool:
    values = _get_request_values(self)
    redirect_uri = values.get("redirect_uri", "").strip()
    state = values.get("state", "")

    if self.command == "GET":
        access_token = _get_oauth_token(self)
        if redirect_uri and access_token is not None:
            user = util.auth.GetAuthenticatedUser(
                self.server.storage,
                access_token,
            )
            if user is not None and user.accountstatus > 0:
                authorization_code = util.auth.CreateTemporaryTicket(
                    self.server.storage,
                    user.id,
                    AUTH_CODE_KIND,
                    expireIn=AUTH_CODE_EXPIRY,
                )
                _store_authorization_code_metadata(
                    self,
                    authorization_code,
                    values,
                )
                redirect_url = _build_redirect_url(
                    redirect_uri,
                    code=authorization_code,
                    state=state,
                )
                self.send_response(200)
                _send_auth_cookie(
                    self,
                    access_token,
                    max_age=ACCESS_TOKEN_EXPIRY,
                )
                self.send_data(
                    _render_redirect_page(redirect_url),
                    status=None,
                    content_type='text/html; charset=utf-8',
                )
                return True

        self.send_data(
            _render_authorize_page(values),
            content_type='text/html; charset=utf-8',
        )
        return True

    username = values.get("username", "").strip()
    password = values.get("password", "")
    if not redirect_uri:
        self.send_data(
            _render_authorize_page(
                values,
                username=username,
                error_message="redirect_uri is required.",
            ),
            status=400,
            content_type='text/html; charset=utf-8',
        )
        return True

    if not username or not password:
        self.send_data(
            _render_authorize_page(
                values,
                username=username,
                error_message="Username and password are required.",
            ),
            status=400,
            content_type='text/html; charset=utf-8',
        )
        return True

    user = self.server.storage.user.check_object_from_username(username)
    if user is None or not util.auth.VerifyPassword(
        self.server.storage,
        user,
        password,
    ):
        self.send_data(
            _render_authorize_page(
                values,
                username=username,
                error_message="Invalid username or password.",
            ),
            status=401,
            content_type='text/html; charset=utf-8',
        )
        return True

    if user.accountstatus <= 0:
        self.send_data(
            _render_authorize_page(
                values,
                username=username,
                error_message="User is not active.",
            ),
            status=403,
            content_type='text/html; charset=utf-8',
        )
        return True

    self.server.storage.user.update_lastonline(user.id)
    access_token = _create_oauth_access_token(
        self,
        user,
        scope=values.get("scope", DEFAULT_SCOPE) or DEFAULT_SCOPE,
        client_id=values.get("client_id", DEFAULT_OAUTH_CLIENT_ID),
        nonce=values.get("nonce", ""),
    )
    authorization_code = util.auth.CreateTemporaryTicket(
        self.server.storage,
        user.id,
        AUTH_CODE_KIND,
        expireIn=AUTH_CODE_EXPIRY,
    )
    _store_authorization_code_metadata(
        self,
        authorization_code,
        values,
    )
    redirect_url = _build_redirect_url(
        redirect_uri,
        code=authorization_code,
        state=state,
    )

    self.send_response(200)
    _send_auth_cookie(
        self,
        access_token,
        max_age=ACCESS_TOKEN_EXPIRY,
    )
    self.send_data(
        _render_redirect_page(redirect_url),
        status=None,
        content_type='text/html; charset=utf-8',
    )
    return True
