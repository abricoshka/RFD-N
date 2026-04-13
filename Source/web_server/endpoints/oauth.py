from web_server._logic import server_path, web_server_handler


STATIC_ROBLOSECURITY = (
    "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-"
    "to-log-into-your-account-and-to-steal-your-ROBUX-and-items.|"
    "_rbolock_security_token_12345"
)
TOKEN_COOKIE_DOMAIN = "www.rbolock.tk"
GLOBAL_COOKIE_DOMAIN = ".rbolock.tk"
AUTHORIZATION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Studio Offline Login</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #212529;
            color: #fff;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }

        .container {
            text-align: center;
            max-width: 400px;
            padding: 20px;
            background-color: #30363b;
            border-radius: 10px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.2);
        }

        h1 {
            color: inherit;
        }

        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }

        button:hover {
            background-color: #45a049;
        }

        footer {
            margin-top: 20px;
            font-size: 12px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Studio Offline Login</h1>
        <p>You are on the Studio Offline login page. To login, click the button below.</p>
        <button onclick="redirectToRobloxStudio()">Login</button>
    </div>
    <footer>
        <p>Made by Stan. Thanks to Chris for the hook help.</p>
    </footer>
    <script>
        function redirectToRobloxStudio() {
            let params = (new URL(document.location)).searchParams;
            let state = params.get("state");
            let redirect_uri = params.get("redirect_uri");
            window.location.href = redirect_uri + "?code=a&state=" + state;
        }
    </script>
</body>
</html>
"""
STATIC_ACCESS_TOKEN = (
    "eyJhbGciOiJFUzI1NiIsImtpZCI6InJib2xvY2sta2V5LTEiLCJ0eXAiOiJKV1QifQ."
    "eyJzdWIiOiIxIiwibmFtZSI6IlJvYmxveCIsIm5pY2tuYW1lIjoiUm9ibG94Iiwi"
    "cHJlZmVycmVkX3VzZXJuYW1lIjoiUm9ibG94IiwiY3JlYXRlZF9hdCI6MSwicHJv"
    "ZmlsZSI6Imh0dHBzOi8vd3d3LnJib2xvY2sudGsvdXNlcnMvMS9wcm9maWxlIiwi"
    "bm9uY2UiOiJpZC1yb2Jsb3giLCJqdGkiOiJJRC5yYm9sb2NrMSIsIm5iZiI6MTc3"
    "MzQ2NjQ1OCwiZXhwIjoxODA1MDAyNDU4LCJpYXQiOjE3NzM0NjY0NTgsImlzcyI6"
    "Imh0dHBzOi8vd3d3LnJib2xvY2sudGsvb2F1dGgvIiwiYXVkIjoiNzk2ODU0OTQy"
    "MjY5MjM1MjI5OCJ9.NIsRoGz7-r4kh06uqOuynVvrep4BxiDRM68B9miDPBbfQWpKJ"
    "gi9W-3QLngZfZNZ2mUH1CTW569sNgo6qkJewQ"
)


def _send_cookie(self: web_server_handler, domain: str) -> None:
    self.send_header(
        "Set-Cookie",
        (
            f".ROBLOSECURITY={STATIC_ROBLOSECURITY}; "
            f"Path=/; Domain={domain}; Secure; SameSite=None"
        ),
    )


def _send_json_with_cookie(
    self: web_server_handler,
    payload,
    *,
    domain: str,
) -> None:
    self.send_response(200)
    _send_cookie(self, domain)
    self.send_json(payload, status=None)


@server_path('/oauth/.well-known/openid-configuration')
def _(self: web_server_handler) -> bool:
    _send_json_with_cookie(self, {
        "issuer": "https://rbolock.tk/oauth/",
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
    }, domain=GLOBAL_COOKIE_DOMAIN)
    return True


@server_path('/oauth/v1/certs')
def _(self: web_server_handler) -> bool:
    _send_json_with_cookie(self, {
        "keys": [{
            "kty": "EC",
            "crv": "P-256",
            "kid": "rbolock-key-1",
            "use": "sig",
            "alg": "ES256",
            "x": "OZC64mYuoR2j8nPNLf-MqlroheUroHMT7qb4Cord1Bc",
            "y": "W0YhP4lO5jiMinLaPL8iXYM_bmD9rvYytvxMRljfi3o",
        }],
    }, domain=GLOBAL_COOKIE_DOMAIN)
    return True


@server_path('/oauth/v1/userinfo')
def _(self: web_server_handler) -> bool:
    _send_json_with_cookie(self, {
        "sub": "1",
        "name": "Roblox",
        "nickname": "Roblox",
        "preferred_username": "Roblox",
        "created_at": 1,
        "profile": "https://www.roblox.com/users/1/profile",
        "picture": "http://localhost/headshot",
        "age_bracket": "Age13OrOver",
        "premium": False,
        "roles": [],
        "internal_user": False,
    }, domain=GLOBAL_COOKIE_DOMAIN)
    return True


@server_path('/oauth/v1/token', commands={'GET', 'POST'})
def _(self: web_server_handler) -> bool:
    _send_json_with_cookie(self, {
        "access_token": STATIC_ACCESS_TOKEN,
        "refresh_token": "rbolock-refresh-token-static",
        "token_type": "Bearer",
        "expires_in": 31536000,
        "id_token": STATIC_ACCESS_TOKEN,
        "scope": "age credentials openid premium profile roles",
    }, domain=TOKEN_COOKIE_DOMAIN)
    return True


@server_path('/oauth/v1/token/revoke', commands={'GET', 'POST'})
def _(self: web_server_handler) -> bool:
    self.send_json({"success": True})
    return True


@server_path('/oauth/v1/token/introspect', commands={'GET', 'POST'})
def _(self: web_server_handler) -> bool:
    self.send_json({
        "active": True,
        "token_type": "Bearer",
        "scope": "age credentials openid premium profile roles",
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
    self.send_data(
        AUTHORIZATION_HTML,
        content_type='text/html; charset=utf-8',
    )
    return True
