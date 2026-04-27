from web_server._logic import server_path, web_server_handler
import util.const

from . import (
    account_settings,
    authentication,
    assets,
    avatar,
    badges,
    data_transfer,
    discovery_api,
    explore_api,
    funds,
    games_api,
    groups,
    join_data,
    marketplace,
    mobile,
    modern_player,
    oauth,
    persistence,
    player_info,
    friend_api,
    presence_api,
    rate,
    save_place,
    setup_player,
    image,
    setup_rcc,
    telemetry,
    text_filter,
    studio,
    users_api,
)


@server_path("/", commands={"GET", "POST", "HEAD"})
def _(self: web_server_handler) -> bool:
    if self.try_proxy_frontend(fallback_on_error=True):
        return True

    if self.command == "HEAD":
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()
        return True

    # Handle OAuth authorization requests (browser login)
    state = self.query.get('state', '')
    code_challenge = self.query.get('code_challenge', '')
    if state or code_challenge:
        location = '/oauth/v1/authorize'
        if self.url_split.query:
            location = f'{location}?{self.url_split.query}'
        self.send_response(302)
        self.send_header('Location', location)
        self.end_headers()
        return True

    # Default response
    data_string = (
        'Roblox Freedom Distribution webserver %s [%s]' %
        (
            util.const.GIT_RELEASE_VERSION,
            self.game_config.game_setup.roblox_version.value[0],
        )
    )
    self.send_data(data_string.encode('utf-8'))
    return True
