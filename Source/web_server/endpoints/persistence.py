# Standard library imports
import itertools
import base64
import hashlib
import re
from datetime import UTC, datetime
import urllib.parse

import json

# Local application imports
from web_server._logic import web_server_handler, server_path


def _read_request_payload(self: web_server_handler) -> dict:
    content = self.read_content()
    if len(content) == 0:
        return {}

    content_type = self.headers.get('content-type', '').lower()
    if 'application/json' in content_type:
        return json.loads(content.decode('utf-8'))

    return dict(urllib.parse.parse_qsl(content.decode('utf-8')))


def _resolve_v2_universe(
    self: web_server_handler,
    match: re.Match[str],
):
    universe_id = int(match.group(1))
    universe = self.server.storage.universe.check(universe_id)
    if universe is None:
        self.send_json({
            "errors": [{
                "code": 2,
                "message": "The requested universe does not exist.",
            }],
        }, 404)
        return None
    return universe


def _build_v2_entry(
    universe_id: int,
    datastore_key: str,
    scope: str,
    entry_key: str,
    value,
    *,
    state: str = "ACTIVE",
    users: list[str] | None = None,
    attributes: dict | None = None,
) -> dict:
    object_key = f"{scope}/{entry_key}"
    serialized_value = json.dumps(value)
    return {
        "path": (
            f"universes/{universe_id}/data-stores/{datastore_key}/entries/{object_key}"
        ),
        "id": object_key,
        "value": serialized_value,
        "users": users or [],
        "attributes": attributes or {},
        "state": state,
        # Compatibility aliases for internal/legacy parsers.
        "Value": serialized_value,
        "Scope": scope,
        "Key": datastore_key,
        "Target": entry_key,
        "objectKey": object_key,
        "entryId": entry_key,
    }


def _get_string(
    query: dict[str, str],
    payload: dict,
    names: tuple[str, ...],
    default: str | None = None,
) -> str | None:
    for name in names:
        query_value = query.get(name)
        if query_value is not None:
            return query_value
        payload_value = payload.get(name)
        if payload_value is not None:
            return str(payload_value)
    return default


def _resolve_v2_keys(self: web_server_handler, payload: dict):
    scope = _get_string(self.query, payload, ('scope',), 'global')
    data_type = _get_string(self.query, payload, ('type', 'dataType'), 'standard')

    key = _get_string(
        self.query,
        payload,
        ('datastore', 'dataStore', 'datastoreName', 'store', 'key'),
    )
    target = _get_string(
        self.query,
        payload,
        ('entry', 'entryKey', 'target', 'name', 'objectKey'),
    )

    # Roblox Studio may send objectKey as "<scope>/<entry>".
    if target is not None and '/' in target and self.query.get('scope') is None and payload.get('scope') is None:
        parsed_scope, parsed_target = target.split('/', 1)
        if parsed_scope and parsed_target:
            scope = parsed_scope
            target = parsed_target

    if key is None or target is None:
        self.send_json({
            "errors": [{
                "code": 1,
                "message": "Missing required datastore or entry key.",
            }],
        }, 400)
        return None

    return scope, data_type, key, target


def _send_octet_stream(
    self: web_server_handler,
    value_bytes: bytes,
    *,
    status: int = 200,
) -> None:
    content_md5 = base64.b64encode(hashlib.md5(value_bytes).digest()).decode('ascii')
    self.send_response(status)
    self.send_header('Content-Type', 'application/octet-stream')
    self.send_header('Content-MD5', content_md5)
    self.send_data(value_bytes, status=None)


def _handle_v2_increment(self: web_server_handler, match: re.Match[str]) -> bool:
    if _resolve_v2_universe(self, match) is None:
        return True
    universe_id = int(match.group(1))

    payload = _read_request_payload(self)
    resolved = _resolve_v2_keys(self, payload)
    if resolved is None:
        return True
    scope, data_type, key, target = resolved

    value_text = _get_string(self.query, payload, ('value', 'amount', 'delta'), '1')
    assert value_text is not None
    try:
        increment_value = int(value_text)
    except ValueError:
        self.send_json({
            "errors": [{"code": 1, "message": "Increment value must be integer."}],
        }, 400)
        return True

    database = self.server.storage.persistence
    current_value = database.get(scope, target, key, data_type)
    try:
        new_value = (
            increment_value
            if current_value is None
            else int(current_value) + increment_value
        )
    except (TypeError, ValueError):
        self.send_json({
            "errors": [{"code": 6, "message": "Stored value is not numeric."}],
        }, 409)
        return True

    stored_value = new_value if data_type == 'sorted' else str(new_value)
    database.set(scope, target, key, stored_value, data_type)
    self.send_json(_build_v2_entry(
        universe_id=universe_id,
        datastore_key=key,
        scope=scope,
        entry_key=target,
        value=stored_value,
    ))
    return True


def _handle_v2_list(self: web_server_handler, match: re.Match[str]) -> bool:
    if _resolve_v2_universe(self, match) is None:
        return True
    universe_id = int(match.group(1))

    payload = _read_request_payload(self)
    scope = _get_string(self.query, payload, ('scope',), 'global') or 'global'
    data_type = _get_string(self.query, payload, ('type', 'dataType'), 'standard') or 'standard'
    key = _get_string(
        self.query,
        payload,
        ('datastore', 'dataStore', 'datastoreName', 'store', 'key'),
    )
    if key is None:
        self.send_json({
            "errors": [{"code": 1, "message": "Missing required datastore key."}],
        }, 400)
        return True

    limit_text = _get_string(self.query, payload, ('limit', 'pageSize', 'maxPageSize'), '50') or '50'
    cursor_text = _get_string(self.query, payload, ('cursor', 'exclusiveStartKey'), '0') or '0'
    try:
        limit = int(limit_text)
        cursor = int(cursor_text)
    except ValueError:
        self.send_json({
            "errors": [{"code": 1, "message": "Invalid pagination arguments."}],
        }, 400)
        return True

    entries, next_cursor = self.server.storage.persistence.list_entries(
        scope=scope,
        key=key,
        typ=data_type,
        limit=limit,
        cursor=cursor,
    )
    self.send_json({
        "dataStoreEntries": [
            _build_v2_entry(
                universe_id=universe_id,
                datastore_key=key,
                scope=scope,
                entry_key=entry["target"],
                value=entry["value"],
            )
            for entry in entries
        ],
        "nextPageToken": str(next_cursor) if next_cursor is not None else None,
    })
    return True

@server_path('/persistence/set')  # Usually expects POST.
def _(self: web_server_handler) -> bool:
    '''
    https://github.com/InnitGroup/syntaxsource/blob/71ca82651707ad88fb717f3cc5e106ff62ac3013/syntaxwebsite/app/routes/datastoreservice.py#L92
    '''
    form_content = str(self.read_content(), encoding='utf-8')
    form_data = dict(urllib.parse.parse_qsl(form_content))
    database = self.server.storage.persistence

    scope = self.query.get('scope', 'global')
    data_type = self.query['type']
    target = self.query.get('target', 'null')
    key = self.query['key']

    value_str = form_data.get('value', 'null')
    value = json.loads(value_str)

    database.set(scope, target, key, value, data_type)
    self.send_json({'data': value})
    return True


@server_path('/persistence/getv2', commands={'POST'})
@server_path('/persistence/getV2', commands={'POST'})
def _(self: web_server_handler) -> bool:
    '''
    https://github.com/InnitGroup/syntaxsource/blob/71ca82651707ad88fb717f3cc5e106ff62ac3013/syntaxwebsite/app/routes/datastoreservice.py#L162
    '''
    form_content = str(self.read_content(), encoding='utf-8')
    form_data = dict(urllib.parse.parse_qsl(form_content))
    database = self.server.storage.persistence
    data_type = self.query['type']

    return_data = []
    starting_count = 0
    for starting_count in itertools.count(0):
        prefix = 'qkeys[%d]' % starting_count
        scope = form_data.get(
            f'{prefix}.scope',
            'global',
        )

        target = form_data.get(
            f'{prefix}.target',
            None,
        )
        if target is None:
            break

        key = form_data.get(
            f'{prefix}.key',
            None,
        )
        if key is None:
            break

        value = database.get(scope, target, key, data_type)
        return_data.append({
            'Value': json.dumps(value),
            'Scope': scope,
            'Key': key,
            'Target': target,
        })

    if starting_count == 0:
        self.send_json({'data': [], 'message': 'No data being requested'})
        return True

    self.send_json({'data': return_data})
    return True


@server_path('/persistence/getSortedValues')  # Expecting POST.
def _(self: web_server_handler) -> bool:
    '''
    Handles retrieval of sorted data from the persistence storage with pagination.
    '''
    data_type = self.query['type']
    scope = self.query.get('scope', 'global')
    key = self.query['key']

    exclusive_start_key = int(self.query.get('exclusiveStartKey', 1))
    is_ascending = self.query.get('ascending') == 'True'
    page_size = int(self.query.get('pageSize', 50))

    inclusive_min_str = self.query.get('inclusiveMinValue')
    inclusive_min_value = (
        int(inclusive_min_str)
        if inclusive_min_str is not None
        else None
    )

    exclusive_max_str = self.query.get('exclusiveMaxValue')
    exclusive_max_value = (
        int(exclusive_max_str)
        if exclusive_max_str is not None
        else None
    )

    if data_type != 'sorted':
        self.send_json({'data': [], 'message': 'Invalid data type'})
        return True

    if exclusive_start_key < 1:
        self.send_json({'data': [], 'message': 'Invalid exclusive start key'})
        return True

    # Assuming persistence supports sorted data.
    database = self.server.storage.persistence
    sorted_data = database.query_sorted_data(
        scope=scope,
        key=key,
        ascending=is_ascending,
        min_value=inclusive_min_value,
        max_value=exclusive_max_value,
        start=exclusive_start_key,
        size=page_size
    )

    if not sorted_data:
        self.send_json({
            'data': {
                'Entries': [],
                'ExclusiveStartKey': None,
            }
        })
        return True

    entries = [
        {
            'Target': entry.name,
            'Value': entry.value,
        }
        for entry in sorted_data.items
    ]

    self.send_json({
        'data': {
            'Entries': entries,
            'ExclusiveStartKey': sorted_data.next_start,
        }
    })
    return True


@server_path('/persistence/increment')  # Usually expects POST.
def _(self: web_server_handler) -> bool:
    '''
    Handles incrementing numeric values in the persistence storage.
    Supports both standard and sorted data types.
    '''
    database = self.server.storage.persistence

    scope = self.query.get('scope', 'global')
    target = self.query['target']
    key = self.query['key']
    data_type = self.query['type']

    try:
        increment_value = int(self.query.get('value', 1))
    except (TypeError, ValueError):
        self.send_json({'data': [], 'message': 'Increment must be an integer'})
        return True

    if not all([target, key]):
        self.send_json({'data': [], 'message': 'Missing required parameters'})
        return True

    # Get current value
    current_value = database.get(scope, target, key, data_type)

    try:
        if current_value is None:
            new_value = increment_value
        else:
            if isinstance(current_value, str):
                current_value = int(current_value)
            new_value = current_value + increment_value
    except (TypeError, ValueError):
        self.send_json(
            {'data': [], 'message': 'Current value is not an integer'})
        return True

    if data_type != 'sorted':
        new_value = str(new_value)

    # Stores the new value.
    database.set(scope, target, key, new_value, data_type)

    self.send_json({'data': new_value})
    return True


@server_path(
    r'/v2/persistence/(\d+)/datastores/objects/object',
    regex=True,
    commands={'GET'},
)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    print("11111111111")
    if _resolve_v2_universe(self, match) is None:
        return True

    payload = _read_request_payload(self)
    resolved = _resolve_v2_keys(self, payload)
    if resolved is None:
        return True
    scope, data_type, key, target = resolved

    database = self.server.storage.persistence
    print(scope,target,key,data_type)
    value = database.get(scope, target, key, data_type)
    if value is None:
        print("No value")
        self.send_json({
            "errors": [
                {"code": 11, "message": "The requested key does not exist.", "retryable": False}
            ],
        }, 404)
        return True

    serialized_value = json.dumps(value).encode('utf-8')
    print(serialized_value)
    _send_octet_stream(self, serialized_value)
    return True


@server_path(
    r'/v2/persistence/(\d+)/datastores/objects/object',
    regex=True,
    commands={'POST'},
)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    if _resolve_v2_universe(self, match) is None:
        return True

    payload = _read_request_payload(self)
    resolved = _resolve_v2_keys(self, payload)
    if resolved is None:
        return True
    scope, data_type, key, target = resolved

    database = self.server.storage.persistence
    raw_value_text = self.read_content().decode('utf-8')
    try:
        value = json.loads(raw_value_text)
    except json.JSONDecodeError:
        value = raw_value_text

    database.set(scope, target, key, value, data_type)
    now_iso = datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')
    self.send_json({
        "version": f"local.{int(datetime.now(UTC).timestamp())}",
        "deleted": False,
        "contentLength": len(raw_value_text.encode('utf-8')),
        "createdTime": now_iso,
        "objectCreatedTime": now_iso,
    })
    return True


@server_path(
    r'/v2/persistence/(\d+)/datastores/objects/object:increment',
    regex=True,
    commands={'POST'},
)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    return _handle_v2_increment(self, match)


@server_path(
    r'/v2/persistence/(\d+)/datastores/objects/object/increment',
    regex=True,
    commands={'POST'},
)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    return _handle_v2_increment(self, match)


@server_path(
    r'/v2/persistence/(\d+)/datastores/objects',
    regex=True,
    commands={'GET'},
)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    return _handle_v2_list(self, match)


@server_path(
    r'/v2/persistence/(\d+)/datastores/objects/list',
    regex=True,
    commands={'GET'},
)
def _(self: web_server_handler, match: re.Match[str]) -> bool:
    return _handle_v2_list(self, match)