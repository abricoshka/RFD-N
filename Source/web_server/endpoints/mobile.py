from web_server._logic import web_server_handler, server_path

@server_path('/v1/mobile-client-version')
@server_path('/mobileapi/check-app-version')
def _(self: web_server_handler) -> bool:
    self.send_response(200)
    self.send_json({"data":{"UpgradeAction":"None"}})
    return True