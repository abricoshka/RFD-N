import subprocess
import functools
import urllib3
import base64
import dataclasses
import json
import gzip
import os
import re


@dataclasses.dataclass(frozen=True)
class download_failure:
    status: int
    message: str


def get_cookie_store_path() -> str:
    return os.path.join(
        os.getenv("USERPROFILE", ""),
        "AppData",
        "Local",
        "Roblox",
        "LocalStorage",
        "RobloxCookies.dat",
    )


def get_cookie_from_system() -> str | None:
    '''
    Only works on Windows systems.
    Do not count on a valid cookie being returned when you run this on a remote server.
    https://github.com/Ramona-Flower/Roblox-Client-Cookie-Stealer/blob/main/main.py
    '''
    roblox_cookies_path = get_cookie_store_path()

    if not os.path.exists(roblox_cookies_path):
        return

    with open(roblox_cookies_path, 'r', encoding='utf-8') as file:
        file_content = json.load(file)

    encoded_cookies = file_content.get("CookiesData")
    if encoded_cookies is None:
        return

    try:
        import win32crypt
    except ImportError:
        return

    decoded_cookies = base64.b64decode(encoded_cookies)
    decrypted_cookies: bytes = win32crypt.CryptUnprotectData(
        decoded_cookies, None, None, None, 0,
    )[1]

    match = re.search(br'\.ROBLOSECURITY\t([^;]+)', decrypted_cookies)
    if match is None:
        return
    return match[1].decode('utf-8', errors='ignore')


def test_cookie(cookie: str | None) -> bool:
    return (
        cookie is not None and
        cookie.startswith(
            "_|WARNING:-DO-NOT-SHARE-THIS.--Sharing-this-will-allow-someone-to-log-in-as-you-and-to-steal-your-ROBUX-and-items.|_"
        )
    )


@functools.cache
def get_rōblox_cookie() -> str | None:
    return next(
        (
            v for v in
            (
                get_cookie_from_system(),
                os.environ.get('ROBLOSECURITY', None),
            )
            if test_cookie(v)
        ), None,
    )


def unzip(data: bytes) -> bytes:
    try:
        return gzip.decompress(data)
    except gzip.BadGzipFile:
        return data


def _extract_error_message(data: bytes) -> str | None:
    try:
        payload = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    errors = payload.get("errors")
    if isinstance(errors, list):
        for error in errors:
            if not isinstance(error, dict):
                continue
            message = error.get("message")
            if isinstance(message, str) and message:
                return message

    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    return None


def _build_http_error_message(
    status: int,
    response_data: bytes,
    has_valid_cookie: bool,
) -> str:
    upstream_message = _extract_error_message(response_data)

    if status == 401:
        if not has_valid_cookie:
            message = (
                "Roblox rejected the asset request with HTTP 401 because RFD "
                "could not load a valid .ROBLOSECURITY cookie from "
                f'"{get_cookie_store_path()}". '
                "Log into Roblox on this machine so the cookie is written to "
                "RobloxCookies.dat, or set the ROBLOSECURITY environment "
                "variable manually."
            )
        else:
            message = (
                "Roblox rejected the asset request with HTTP 401 even though "
                "RFD loaded a .ROBLOSECURITY cookie. The cookie may be expired "
                "or may not have access to this asset."
            )
        if upstream_message is not None:
            return f"{message} Upstream message: {upstream_message}"
        return message

    if upstream_message is not None:
        return (
            f"Roblox asset delivery request failed with HTTP {status}. "
            f"Upstream message: {upstream_message}"
        )
    return f"Roblox asset delivery request failed with HTTP {status}."


def download_item_result(
    url: str,
    cookie: str | None = None,
) -> bytes | download_failure:
    if cookie is None:
        cookie = get_rōblox_cookie()
    has_valid_cookie = test_cookie(cookie)

    headers = {
        'User-Agent': 'Roblox/WinInet',
        'Referer': 'https://www.roblox.com/',
    }
    if has_valid_cookie:
        headers['Cookie'] = "; ".join(
            f'{x}={y}'
            for x, y in {
                '.ROBLOSECURITY': cookie,
            }.items()
        )

    place_id = os.environ.get("rfdplaceid")
    if place_id:
        headers["Roblox-Place-Id"] = place_id
        headers["Roblox-Browser-Asset-Request"] = "false"

    try:
        http = urllib3.PoolManager()
        response = http.request('GET', url, headers=headers)
        if response.status != 200:
            return download_failure(
                status=response.status,
                message=_build_http_error_message(
                    response.status,
                    response.data,
                    has_valid_cookie=has_valid_cookie,
                ),
            )
        return response.data

    except urllib3.exceptions.HTTPError as error:
        return download_failure(
            status=502,
            message=(
                "Failed to reach Roblox asset delivery. "
                f"{type(error).__name__}: {error}"
            ),
        )


def download_item(url: str, cookie: str | None = None) -> bytes | None:
    result = download_item_result(url, cookie=cookie)
    if isinstance(result, download_failure):
        return None
    return result


def download_rōblox_asset_result(
    asset_id: int,
    cookie: str | None = None,
) -> bytes | download_failure | None:
    last_failure: download_failure | None = None
    for key in {'id'}:
        result = download_item_result(
            'https://assetdelivery.roblox.com/v1/asset/?%s=%s' %
            (key, asset_id),
            cookie=cookie,
        )
        if isinstance(result, download_failure):
            last_failure = result
            continue
        return unzip(result)
    return last_failure


def download_rōblox_asset(asset_id: int, cookie: str | None = None) -> bytes | None:
    result = download_rōblox_asset_result(asset_id, cookie=cookie)
    if isinstance(result, download_failure):
        return None
    return result


get_roblox_cookie = get_rōblox_cookie
download_roblox_asset_result = download_rōblox_asset_result
download_roblox_asset = download_rōblox_asset


def process_command_line(cmd_line: str) -> bytes:
    popen = subprocess.Popen(
        args=cmd_line,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=True,
    )
    (stdout, _) = popen.communicate()
    return stdout
