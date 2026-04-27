import util.auth
from web_server._logic import server_path, web_server_handler


def _mask_email(email: str) -> str | None:
    local_part, separator, domain_part = email.partition("@")
    if separator != "@" or not local_part or not domain_part:
        return None
    return local_part[0] + ("*" * (len(local_part) - 1)) + "@" + domain_part


@server_path("/v1/email", commands={"GET"})
@util.auth.authenticated_required_api
def get_email_status(self: web_server_handler) -> bool:
    authenticated_user = util.auth.GetCurrentUser(self)
    if authenticated_user is None:
        self.send_json(
            {"errors": [{"code": 0, "message": "You are not logged in"}]},
            401,
        )
        return True

    user_email = self.server.storage.user_email.check_object(authenticated_user.id)
    self.send_json({
        "emailAddress": (
            _mask_email(user_email.email)
            if user_email is not None else
            None
        ),
        "verified": (
            user_email.verified
            if user_email is not None else
            False
        ),
        "canBypassPasswordForEmailUpdate": True,
    })
    return True


@server_path(r"/v1/themes/([^/]+)/(\d+)", regex=True, commands={"GET"})
def get_theme(self: web_server_handler, match) -> bool:
    del match
    # always returns a valid theme object here for authenticated web shells.
    return_value = {
        "themeType": "Dark",
    }
    self.send_json(return_value)
    return True
