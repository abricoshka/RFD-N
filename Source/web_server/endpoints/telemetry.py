import random
from web_server._logic import web_server_handler, server_path

@server_path('/client/pbe')
@server_path('/mobile/pbe')
@server_path('/studio/pbe')
@server_path('/timespent/pbe')
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