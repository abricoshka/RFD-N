import base64
import hashlib
import random
from web_server._logic import web_server_handler, server_path

@server_path('/client/pbe')
@server_path('/mobile/pbe')
@server_path('/studio/pbe')
@server_path('/timespent/pbe')
@server_path('/rcc/pbe')
def _(self: web_server_handler) -> bool:
    self.send_json({})
    return True

@server_path('/v1.1/Counters/BatchIncrement')
@server_path('/v1.0/SequenceStatistics/BatchAddToSequencesV2')
@server_path('/v1.1/Counters/Increment/')
def _(self: web_server_handler) -> bool:
    self.send_json({})
    return True

@server_path('/v1/enrollments')
def _(self: web_server_handler) -> bool:
    self.send_json({
        "SubjectType": "BrowserTracker",
        "SubjectTargetId": 63713166375,
        "ExperimentName": "AllUsers.DevelopSplashScreen.GreenStartCreatingButton",
        "Status": "Inactive",
        "Variation": None
    })
    return True

@server_path('/v1/get-enrollments')
def _(self: web_server_handler) -> bool:
    self.send_json({})
    return True

@server_path('/pe')
@server_path('/user-heartbeats-api/action-report')
@server_path('/user-heartbeats-api/pulse')
@server_path("/experience-signals-ingest/public/v1/events/single")
def _(self: web_server_handler) -> bool:
    self.send_json({})
    return True

@server_path('/product-experimentation-platform/v1/projects/1/values')
def _(self: web_server_handler) -> bool:
    self.send_json({"data":[]})
    return True


@server_path('/browser-tracker-api/device/initialize', commands={'POST'})
@server_path('/device/initialize', commands={'POST'}) # Android
def _(self: web_server_handler) -> bool:
    self.send_json({"browserTrackerId": random.randint(100000000,9999999999), "appDeviceIdentifier": None})
    return True


@server_path(
    '/product-experimentation-platform/v1/projects/1/layers/PlayerApp.Login/values',
    commands={'GET'},
)
def _(self: web_server_handler) -> bool:
    parameters = self.query_lists.get("parameters", [])
    if len(parameters) != 1 or not parameters[0]:
        self.send_json(
            {"code": 3, "message": "Invalid format for parameters", "details": []},
            400,
        )
        return True

    self.send_json({parameters[0]: None})
    return True


@server_path('/attribution/v1/events/post-authentication')
def _(self: web_server_handler) -> bool:
    self.send_data("", 200)
    return True

@server_path('/userhub/')
def _(self: web_server_handler) -> bool:
    if self.headers.get('Upgrade', '').lower() == 'websocket':
        ws_key = self.headers.get('Sec-WebSocket-Key', '')
        accept_value = base64.b64encode(
            hashlib.sha1(
                (
                    ws_key +
                    '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
                ).encode('utf-8'),
            ).digest(),
        ).decode('ascii')
        self.send_response(101)
        self.send_header('Upgrade', 'websocket')
        self.send_header('Connection', 'Upgrade')
        self.send_header('Sec-WebSocket-Accept', accept_value)
        self.end_headers()
        return True

    self.send_json({})
    return True
