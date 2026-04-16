from web_server._logic import server_path, web_server_handler
import util.const

from . import (
    authentication,
    assets,
    avatar,
    badges,
    data_transfer,
    funds,
    games_api,
    groups,
    image,
    join_data,
    marketplace,
    mobile,
    oauth,
    persistence,
    player_info,
    save_place,
    setup_player,
    setup_rcc,
    telemetry,
    text_filter,
    studio,
    users_api,
)


@server_path("/")
def _(self: web_server_handler) -> bool:
    if self.try_proxy_frontend(fallback_on_error=True):
        return True

    # Handle OAuth authorization requests (v554 browser login)
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
