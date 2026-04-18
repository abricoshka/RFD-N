import gzip
import functools
import hashlib
import io
import json
import os
import re
import ssl
import urllib.request
from datetime import UTC, datetime
from typing import Any

import assets.returns as returns
import util
import util.auth
from web_server._logic import server_path, web_server_handler


DEFAULT_IMAGE_SIZES = [36, 48, 50, 60, 75, 100, 128, 150, 180, 200, 256, 324, 352, 396, 420, 480, 500, 512, 576, 640, 700, 720, 768, 1280]
SQUARE_IMAGE_SIZES = [36, 48, 50, 60, 75, 100, 128, 150, 180, 200, 256, 352, 396, 420, 480, 500, 512, 576, 640, 700, 720, 768, 1280]
GAME_ICON_SIZES = [50, 128, 150, 256, 420, 512]
PLACE_ICON_SIZES = [48, 60, 100, 128, 150, 180, 256, 324, 352, 420, 512, 576]
BATCH_ALLOWED_TYPES = {"Avatar", "AvatarHeadShot", "GameIcon", "GameThumbnail", "Asset", "GroupIcon"}
MAX_BATCH_REQUESTS = 15
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
IMAGE_CACHE_DIR_NAME = "ImageCache"
GAME_ICON_PLACEHOLDER_REL_PATH = "img/placeholder/icon_one.png"
GAME_BANNER_PLACEHOLDER_REL_PATH = "img/placeholder/icon_two.png"
USER_AVATAR_PLACEHOLDER_REL_PATH = "img/placeholder/avatar_placeholder.png"
USER_HEADSHOT_PLACEHOLDER_REL_PATH = "img/placeholder/headshot_placeholder.png"


def _get_header(self: web_server_handler, name: str) -> str | None:
    return (
        self.headers.get(name)
        or self.headers.get(name.lower())
        or self.headers.get(name.upper())
    )


def _guess_image_content_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    return "application/octet-stream"


def _is_image_data(data: bytes) -> bool:
    return _guess_image_content_type(data).startswith("image/")


def _static_root() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def _static_file_path(relative_path: str) -> str:
    return os.path.join(_static_root(), *relative_path.replace("\\", "/").split("/"))


@functools.cache
def _read_static_file(relative_path: str) -> bytes:
    with open(_static_file_path(relative_path), "rb") as file_obj:
        return file_obj.read()


def _build_static_url(self: web_server_handler, relative_path: str) -> str:
    return f"{self.hostname}/static/{relative_path.replace(os.sep, '/')}"


def _image_cache_root(self: web_server_handler) -> str:
    asset_cache_dir = os.path.abspath(self.game_config.asset_cache.dir_path)
    return os.path.join(os.path.dirname(asset_cache_dir), IMAGE_CACHE_DIR_NAME)


def _cache_file_path(self: web_server_handler, bucket: str, key: str) -> str:
    key_digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return os.path.join(
        _image_cache_root(self),
        bucket,
        key_digest[:2],
        key_digest[2:4],
        key_digest,
    )


def _read_cached_image(self: web_server_handler, bucket: str, key: str) -> bytes | None:
    path = _cache_file_path(self, bucket, key)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as file_obj:
        return file_obj.read()


def _write_cached_image(
    self: web_server_handler,
    bucket: str,
    key: str,
    data: bytes,
) -> None:
    path = _cache_file_path(self, bucket, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as file_obj:
        file_obj.write(data)


def _download_binary(url: str) -> bytes | None:
    ssl_context = None
    if url.startswith("https://"):
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    with urllib.request.urlopen(url, timeout=10, context=ssl_context) as response:
        return response.read()


def _load_asset_bytes(
    self: web_server_handler,
    asset_key: int | str,
) -> bytes | None:
    asset = self.game_config.asset_cache.get_asset(
        asset_key,
        bypass_blocklist=self.is_privileged,
    )
    if isinstance(asset, returns.ret_data):
        return asset.data
    if isinstance(asset, returns.ret_relocate):
        try:
            return _download_binary(asset.url)
        except Exception:
            return None
    return None


def _load_original_image(
    self: web_server_handler,
    content_hash: str,
) -> bytes | None:
    cached_image = _read_cached_image(self, "originals", content_hash)
    if cached_image is not None:
        if not _is_image_data(cached_image):
            return None
        return cached_image

    asset_bytes = _load_asset_bytes(self, content_hash)
    if asset_bytes is None:
        return None
    if not _is_image_data(asset_bytes):
        return None

    _write_cached_image(self, "originals", content_hash, asset_bytes)
    return asset_bytes


def _resize_image_bytes(
    image_bytes: bytes,
    target_width: int,
    target_height: int,
) -> tuple[bytes, str, bool]:
    content_type = _guess_image_content_type(image_bytes)
    try:
        from PIL import Image  # pyright: ignore[reportMissingImports]
    except ImportError:
        return image_bytes, content_type, False

    try:
        image_obj = Image.open(io.BytesIO(image_bytes))
        resampling_attr = getattr(Image, "Resampling", Image)
        resampling = getattr(resampling_attr, "LANCZOS", getattr(Image, "LANCZOS", 1))
        image_obj = image_obj.convert("RGBA")
        image_obj = image_obj.resize((int(target_width), int(target_height)), resampling)

        output = io.BytesIO()
        image_obj.save(output, "PNG")
        return output.getvalue(), "image/png", True
    except Exception:
        return image_bytes, content_type, False


def _build_variant_hash(content_hash: str, target_width: int, target_height: int) -> str:
    return hashlib.sha512(
        f"{content_hash}-{target_width}-{target_height}-v3".encode("utf-8"),
    ).hexdigest()


def _load_variant_image(
    self: web_server_handler,
    image_content_hash: str,
    target_width: int,
    target_height: int,
    cropped_hash: str,
    skip_cache_cropped_image: bool = False,
) -> tuple[bytes, str] | None:
    if not skip_cache_cropped_image:
        cached_variant = _read_cached_image(self, "variants", cropped_hash)
        if cached_variant is not None:
            return cached_variant, _guess_image_content_type(cached_variant)

    original_image = _load_original_image(self, image_content_hash)
    if original_image is None:
        return None

    resized_image, content_type, resized = _resize_image_bytes(
        original_image,
        target_width,
        target_height,
    )
    if resized and not skip_cache_cropped_image:
        _write_cached_image(self, "variants", cropped_hash, resized_image)
    return resized_image, content_type


def _send_image_response(
    self: web_server_handler,
    image_bytes: bytes,
    content_type: str,
    cache_control: str = "max-age=120",
) -> None:
    self.send_response(200)
    self.send_header("Cache-Control", cache_control)
    self.send_data(
        image_bytes,
        status=None,
        content_type=content_type,
    )


def _send_placeholder_image(
    self: web_server_handler,
    relative_path: str,
    target_width: int | None = None,
    target_height: int | None = None,
    *,
    cache_control: str = "max-age=120",
) -> bool:
    placeholder_bytes = _read_static_file(relative_path)
    content_type = _guess_image_content_type(placeholder_bytes)
    if target_width is not None and target_height is not None:
        placeholder_bytes, content_type, _resized = _resize_image_bytes(
            placeholder_bytes,
            target_width,
            target_height,
        )

    _send_image_response(
        self,
        placeholder_bytes,
        content_type,
        cache_control=cache_control,
    )
    return True


def handle_resolution_check(
    self: web_server_handler,
    width_parameters_name: list[str] = ["width", "x"],
    height_parameters_name: list[str] = ["height", "y"],
    allowed_widths: list[int] = SQUARE_IMAGE_SIZES,
    allowed_heights: list[int] = SQUARE_IMAGE_SIZES,
    must_be_square: bool = True,
    can_round_to_nearest: bool = True,
) -> tuple[int, int] | None:
    width: int | None = None
    height: int | None = None

    for width_parameter_name in width_parameters_name:
        if width_parameter_name not in self.query:
            continue
        try:
            width = int(self.query[width_parameter_name])
        except ValueError:
            self.send_error(400)
            return None
        break

    for height_parameter_name in height_parameters_name:
        if height_parameter_name not in self.query:
            continue
        try:
            height = int(self.query[height_parameter_name])
        except ValueError:
            self.send_error(400)
            return None
        break

    if width is None or height is None:
        self.send_error(400)
        return None

    if must_be_square and width != height:
        self.send_error(400)
        return None

    if not can_round_to_nearest and (
        width not in allowed_widths or
        height not in allowed_heights
    ):
        self.send_error(400)
        return None

    if can_round_to_nearest:
        if width not in allowed_widths:
            width = min(allowed_widths, key=lambda allowed: abs(allowed - width))
        if height not in allowed_heights:
            height = min(allowed_heights, key=lambda allowed: abs(allowed - height))

    return width, height


def handle_image_resize(
    self: web_server_handler,
    image_content_hash: str,
    target_width: int,
    target_height: int,
    cropped_hash: str,
    cache_control: str = "max-age=120",
    skip_cache_cropped_image: bool = False,
    placeholder_path: str | None = None,
) -> bool:
    resized_image = _load_variant_image(
        self,
        image_content_hash,
        target_width,
        target_height,
        cropped_hash,
        skip_cache_cropped_image=skip_cache_cropped_image,
    )
    if resized_image is None:
        if placeholder_path is not None:
            return _send_placeholder_image(
                self,
                placeholder_path,
                target_width,
                target_height,
                cache_control=cache_control,
            )
        self.send_error(404)
        return True

    image_bytes, content_type = resized_image
    _send_image_response(
        self,
        image_bytes,
        content_type,
        cache_control=cache_control,
    )
    return True


def _send_stored_image(
    self: web_server_handler,
    content_hash: str | None,
    target_width: int | None = None,
    target_height: int | None = None,
    *,
    placeholder_path: str | None = None,
    cache_control: str = "max-age=120",
) -> bool:
    final_content_hash = content_hash
    if final_content_hash is None:
        if placeholder_path is not None:
            return _send_placeholder_image(
                self,
                placeholder_path,
                target_width,
                target_height,
                cache_control=cache_control,
            )
        self.send_error(404)
        return True

    if target_width is not None and target_height is not None:
        return handle_image_resize(
            self,
            final_content_hash,
            target_width,
            target_height,
            _build_variant_hash(final_content_hash, target_width, target_height),
            cache_control=cache_control,
            placeholder_path=placeholder_path,
        )

    original_image = _load_original_image(self, final_content_hash)
    if original_image is None:
        if placeholder_path is not None:
            return _send_placeholder_image(
                self,
                placeholder_path,
                cache_control=cache_control,
            )
        self.send_error(404)
        return True

    _send_image_response(
        self,
        original_image,
        _guess_image_content_type(original_image),
        cache_control=cache_control,
    )
    return True


def _read_json_body(self: web_server_handler) -> Any | None:
    raw_body = self.read_content()
    if not raw_body:
        return None

    if _get_header(self, "Content-Encoding") == "gzip":
        raw_body = gzip.decompress(raw_body)

    return json.loads(raw_body.decode("utf-8"))


def _read_image_upload(self: web_server_handler) -> tuple[bytes, str] | None:
    body = self.read_content()
    if not body:
        self.send_json({"errors": [{"code": 0, "message": "Image body is empty"}]}, 400)
        return None
    if len(body) > MAX_IMAGE_UPLOAD_BYTES:
        self.send_json({"errors": [{"code": 0, "message": "Image body is too large"}]}, 413)
        return None

    content_type = _guess_image_content_type(body)
    if not content_type.startswith("image/"):
        self.send_json({"errors": [{"code": 0, "message": "Body must contain a supported image"}]}, 415)
        return None
    return body, content_type


def _store_uploaded_image(self: web_server_handler, body: bytes) -> str:
    content_hash = hashlib.sha512(body).hexdigest()
    _write_cached_image(self, "originals", content_hash, body)
    return content_hash


def _current_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _require_privileged_image_upload(self: web_server_handler) -> bool:
    if self.is_privileged:
        return True
    self.send_json({"errors": [{"code": 0, "message": "Image uploads require a privileged request"}]}, 403)
    return False


def _resolve_user_id(self: web_server_handler) -> int | None:
    user_id = self.query.get("userId")
    if user_id is not None:
        try:
            return int(user_id)
        except ValueError:
            return None

    username = self.query.get("username")
    if username is None:
        return None
    return self.server.storage.user.get_id_from_username(username)


def _user_exists(self: web_server_handler, user_id: int) -> bool:
    return self.server.storage.user.check(user_id) is not None


def _get_user_thumbnail_hash(
    self: web_server_handler,
    user_id: int,
    *,
    headshot: bool,
) -> str | None:
    thumbnail_row = self.server.storage.userthumbnail.check(user_id)
    if thumbnail_row is None:
        return None

    full_content_hash, headshot_content_hash, _updated_at = thumbnail_row
    if headshot:
        return headshot_content_hash or full_content_hash
    return full_content_hash or headshot_content_hash


def _resolve_place_id_for_icon(
    self: web_server_handler,
    target_id: int,
    *,
    prefer_universe: bool,
) -> int | None:
    if prefer_universe:
        universe_row = self.server.storage.universe.check(target_id)
        if universe_row is not None:
            return int(universe_row[0])

    place_icon_row = self.server.storage.placeicon.check(target_id)
    if place_icon_row is not None:
        return target_id

    place_row = self.server.storage.place.check(target_id)
    if place_row is not None:
        return target_id

    if not prefer_universe:
        universe_row = self.server.storage.universe.check(target_id)
        if universe_row is not None:
            return int(universe_row[0])

    return None


def _get_place_icon_hash(
    self: web_server_handler,
    target_id: int,
    *,
    prefer_universe: bool,
) -> tuple[str | None, int | None]:
    place_id = _resolve_place_id_for_icon(
        self,
        target_id,
        prefer_universe=prefer_universe,
    )
    if place_id is None:
        return None, None

    place_icon_row = self.server.storage.placeicon.check(place_id)
    if place_icon_row is None:
        return None, place_id

    content_hash, _updated_at, moderation_status = place_icon_row
    if moderation_status != 0:
        return None, place_id
    return content_hash, place_id


def _build_avatar_image_url(
    self: web_server_handler,
    user_id: int,
    width: int,
    height: int,
) -> str:
    return f"{self.hostname}/avatar-thumbnail/image?userId={user_id}&x={width}&y={height}"


def _build_headshot_image_url(
    self: web_server_handler,
    user_id: int,
    width: int,
    height: int,
) -> str:
    return f"{self.hostname}/headshot-thumbnail/image?userId={user_id}&x={width}&y={height}"


def _build_game_icon_url(
    self: web_server_handler,
    place_id: int | None,
    width: int,
    height: int,
) -> str:
    if place_id is None:
        return f"{self.hostname}/Thumbs/GameIcon.ashx?x={width}&y={height}"
    return f"{self.hostname}/Thumbs/GameIcon.ashx?assetId={place_id}&x={width}&y={height}"


def _build_asset_thumbnail_url(
    self: web_server_handler,
    asset_id: int,
    width: int,
    height: int,
) -> str:
    return f"{self.hostname}/Game/Tools/ThumbnailAsset.ashx?aid={asset_id}&fmt=png&wd={width}&ht={height}"


@server_path(r"/rfd/image-cdn/v1/(?P<image_key>[A-Za-z0-9]+)", regex=True, commands={"GET"})
def serve_cdn_image(self: web_server_handler, match: re.Match[str]) -> bool:
    image_key = match.group("image_key")
    image_bytes = _read_cached_image(self, "variants", image_key)
    if image_bytes is None:
        image_bytes = _read_cached_image(self, "originals", image_key)
    if image_bytes is None:
        self.send_error(404)
        return True

    _send_image_response(
        self,
        image_bytes,
        _guess_image_content_type(image_bytes),
        cache_control="public, max-age=31536000",
    )
    return True


@server_path(r"/rfd/image-upload/v1/places/(?P<place_id>\d+)/icon", regex=True, commands={"POST"})
def upload_place_icon(self: web_server_handler, match: re.Match[str]) -> bool:
    if not _require_privileged_image_upload(self):
        return True

    image_upload = _read_image_upload(self)
    if image_upload is None:
        return True

    place_id = int(match.group("place_id"))
    image_body, _content_type = image_upload
    content_hash = _store_uploaded_image(self, image_body)
    self.server.storage.placeicon.update(
        placeid=place_id,
        content_hash=content_hash,
        updated_at=_current_timestamp(),
        moderation_status=0,
    )
    self.send_json({
        "targetType": "place-icon",
        "targetId": place_id,
        "contentHash": content_hash,
        "cdnUrl": f"{self.hostname}/rfd/image-cdn/v1/{content_hash}",
        "deliveryUrl": _build_game_icon_url(self, place_id, 420, 420),
    }, 201)
    return True


@server_path(r"/rfd/image-upload/v1/users/(?P<user_id>\d+)/avatar", regex=True, commands={"POST"})
def upload_user_avatar(self: web_server_handler, match: re.Match[str]) -> bool:
    if not _require_privileged_image_upload(self):
        return True

    image_upload = _read_image_upload(self)
    if image_upload is None:
        return True

    user_id = int(match.group("user_id"))
    existing_thumbnail = self.server.storage.userthumbnail.check(user_id)
    current_full = existing_thumbnail[0] if existing_thumbnail is not None else None
    current_headshot = existing_thumbnail[1] if existing_thumbnail is not None else None
    image_body, _content_type = image_upload
    content_hash = _store_uploaded_image(self, image_body)
    self.server.storage.userthumbnail.update(
        userid=user_id,
        full_contenthash=content_hash,
        headshot_contenthash=current_headshot,
        updated_at=_current_timestamp(),
    )
    self.send_json({
        "targetType": "user-avatar",
        "targetId": user_id,
        "contentHash": content_hash,
        "previousContentHash": current_full,
        "cdnUrl": f"{self.hostname}/rfd/image-cdn/v1/{content_hash}",
        "deliveryUrl": _build_avatar_image_url(self, user_id, 420, 420),
    }, 201)
    return True


@server_path(r"/rfd/image-upload/v1/users/(?P<user_id>\d+)/headshot", regex=True, commands={"POST"})
def upload_user_headshot(self: web_server_handler, match: re.Match[str]) -> bool:
    if not _require_privileged_image_upload(self):
        return True

    image_upload = _read_image_upload(self)
    if image_upload is None:
        return True

    user_id = int(match.group("user_id"))
    existing_thumbnail = self.server.storage.userthumbnail.check(user_id)
    current_full = existing_thumbnail[0] if existing_thumbnail is not None else None
    current_headshot = existing_thumbnail[1] if existing_thumbnail is not None else None
    image_body, _content_type = image_upload
    content_hash = _store_uploaded_image(self, image_body)
    self.server.storage.userthumbnail.update(
        userid=user_id,
        full_contenthash=current_full,
        headshot_contenthash=content_hash,
        updated_at=_current_timestamp(),
    )
    self.send_json({
        "targetType": "user-headshot",
        "targetId": user_id,
        "contentHash": content_hash,
        "previousContentHash": current_headshot,
        "cdnUrl": f"{self.hostname}/rfd/image-cdn/v1/{content_hash}",
        "deliveryUrl": _build_headshot_image_url(self, user_id, 420, 420),
    }, 201)
    return True


@server_path(r"/rfd/image-upload/v1/users/(?P<user_id>\d+)/thumbnail", regex=True, commands={"POST"})
def upload_user_thumbnail_bundle(self: web_server_handler, match: re.Match[str]) -> bool:
    if not _require_privileged_image_upload(self):
        return True

    image_upload = _read_image_upload(self)
    if image_upload is None:
        return True

    user_id = int(match.group("user_id"))
    image_body, _content_type = image_upload
    content_hash = _store_uploaded_image(self, image_body)
    self.server.storage.userthumbnail.update(
        userid=user_id,
        full_contenthash=content_hash,
        headshot_contenthash=content_hash,
        updated_at=_current_timestamp(),
    )
    self.send_json({
        "targetType": "user-thumbnail",
        "targetId": user_id,
        "contentHash": content_hash,
        "cdnUrl": f"{self.hostname}/rfd/image-cdn/v1/{content_hash}",
        "avatarUrl": _build_avatar_image_url(self, user_id, 420, 420),
        "headshotUrl": _build_headshot_image_url(self, user_id, 420, 420),
    }, 201)
    return True


@server_path("/avatar-thumbnail/image", commands={"GET"})
@server_path("/Thumbs/Avatar.ashx", commands={"GET"})
@server_path("/thumbs/avatar.ashx", commands={"GET"})
def avatar_thumbnail_image(self: web_server_handler) -> bool:
    user_id = _resolve_user_id(self)

    size_pair = handle_resolution_check(
        self,
        width_parameters_name=["x", "width"],
        height_parameters_name=["y", "height"],
        allowed_widths=SQUARE_IMAGE_SIZES,
        allowed_heights=SQUARE_IMAGE_SIZES,
        must_be_square=True,
        can_round_to_nearest=True,
    )
    if size_pair is None:
        return True

    target_width, target_height = size_pair
    content_hash = None
    if user_id is not None and _user_exists(self, user_id):
        content_hash = _get_user_thumbnail_hash(self, user_id, headshot=False)

    return _send_stored_image(
        self,
        content_hash,
        target_width,
        target_height,
        placeholder_path=USER_AVATAR_PLACEHOLDER_REL_PATH,
    )


@server_path("/avatar-thumbnail/json", commands={"GET"})
def avatar_thumbnail_json(self: web_server_handler) -> bool:
    user_id = _resolve_user_id(self)
    if user_id is None:
        self.send_json({"Final": True, "Url": _build_static_url(self, USER_AVATAR_PLACEHOLDER_REL_PATH)})
        return True

    size_pair = handle_resolution_check(
        self,
        width_parameters_name=["width", "x"],
        height_parameters_name=["height", "y"],
        allowed_widths=SQUARE_IMAGE_SIZES,
        allowed_heights=SQUARE_IMAGE_SIZES,
        must_be_square=True,
        can_round_to_nearest=True,
    )
    if size_pair is None:
        return True

    target_width, target_height = size_pair
    self.send_json({
        "Final": True,
        "Url": _build_avatar_image_url(self, user_id, target_width, target_height),
    })
    return True


@server_path("/Thumbs/GameIcon.ashx", commands={"GET"})
@server_path("/Thumbs/PlaceIcon.ashx", commands={"GET"})
def place_icon_image(self: web_server_handler) -> bool:
    asset_id = self.query.get("assetId") or self.query.get("assetid")
    content_hash: str | None = None

    if asset_id is not None:
        try:
            requested_id = int(asset_id)
        except ValueError:
            self.send_error(400)
            return True

        content_hash, _place_id = _get_place_icon_hash(
            self,
            requested_id,
            prefer_universe=False,
        )

    if "x" not in self.query and "y" not in self.query and "width" not in self.query and "height" not in self.query:
        return _send_stored_image(
            self,
            content_hash,
            placeholder_path=GAME_ICON_PLACEHOLDER_REL_PATH,
        )

    size_pair = handle_resolution_check(
        self,
        width_parameters_name=["x", "width"],
        height_parameters_name=["y", "height"],
        allowed_widths=PLACE_ICON_SIZES,
        allowed_heights=PLACE_ICON_SIZES,
        must_be_square=False,
        can_round_to_nearest=True,
    )
    if size_pair is None:
        return True

    target_width, target_height = size_pair
    return _send_stored_image(
        self,
        content_hash,
        target_width,
        target_height,
        placeholder_path=GAME_ICON_PLACEHOLDER_REL_PATH,
    )


@server_path("/v1/games/icons", commands={"GET"})
def get_game_icons(self: web_server_handler) -> bool:
    universe_ids_csv = self.query.get("universeIds")
    if universe_ids_csv is None:
        self.send_json({"errors": [{"code": 4, "message": "The requested Ids are invalid, of an invalid type or missing."}]}, 400)
        return True

    universe_ids = universe_ids_csv.split(",")
    if len(universe_ids) > 100:
        self.send_json({"errors": [{"code": 1, "message": "There are too many requested Ids."}]}, 400)
        return True

    requested_size = self.query.get("size") or "50x50"
    try:
        size_width, size_height = requested_size.split("x", 1)
        target_width = min(GAME_ICON_SIZES, key=lambda allowed: abs(allowed - int(size_width)))
        target_height = min(GAME_ICON_SIZES, key=lambda allowed: abs(allowed - int(size_height)))
    except Exception:
        self.send_json({"errors": [{"code": 3, "message": "The requested size is invalid. Please see documentation for valid thumbnail size parameter name and format."}]}, 400)
        return True

    processed_requests = []
    for universe_id in universe_ids:
        try:
            universe_id_num = int(universe_id)
        except ValueError:
            continue

        content_hash, place_id = _get_place_icon_hash(
            self,
            universe_id_num,
            prefer_universe=True,
        )
        if place_id is None and content_hash is None:
            continue

        processed_requests.append({
            "targetId": universe_id_num,
            "state": "Completed",
            "imageUrl": _build_game_icon_url(self, place_id, target_width, target_height),
            "version": "TN3",
        })

    self.send_json({"data": processed_requests})
    return True


@server_path("/asset-thumbnail/json", commands={"GET"})
def asset_thumbnail_json(self: web_server_handler) -> bool:
    requested_size = self.query.get("size") or "768x432"
    try:
        size_width, size_height = requested_size.split("x", 1)
        target_width = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - int(size_width)))
        target_height = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - int(size_height)))
    except Exception:
        self.send_json({"Final": False, "Url": _build_static_url(self, GAME_BANNER_PLACEHOLDER_REL_PATH)})
        return True

    asset_id = self.query.get("assetId") or self.query.get("assetid")
    if asset_id is None:
        self.send_json({"Final": True, "Url": _build_static_url(self, GAME_BANNER_PLACEHOLDER_REL_PATH)})
        return True

    try:
        asset_id_num = int(asset_id)
    except ValueError:
        self.send_json({"Final": True, "Url": _build_static_url(self, GAME_BANNER_PLACEHOLDER_REL_PATH)})
        return True

    self.send_json({
        "Final": True,
        "Url": _build_asset_thumbnail_url(self, asset_id_num, target_width, target_height),
    })
    return True


@server_path("/asset-thumbnail/image", commands={"GET"})
@server_path("/thumbs/asset.ashx", commands={"GET"})
@server_path("/Thumbs/Asset.ashx", commands={"GET"})
def asset_thumbnail_image(self: web_server_handler) -> bool:
    asset_id = self.query.get("assetId") or self.query.get("assetid")
    if asset_id is None:
        return _send_placeholder_image(self, GAME_BANNER_PLACEHOLDER_REL_PATH)

    try:
        asset_id_num = int(asset_id)
    except ValueError:
        self.send_error(400)
        return True

    size_pair = handle_resolution_check(
        self,
        width_parameters_name=["x", "width"],
        height_parameters_name=["y", "height"],
        allowed_widths=DEFAULT_IMAGE_SIZES,
        allowed_heights=DEFAULT_IMAGE_SIZES,
        must_be_square=False,
        can_round_to_nearest=True,
    )
    if size_pair is None:
        return True

    target_width, target_height = size_pair
    asset_bytes = _load_asset_bytes(self, asset_id_num)
    if asset_bytes is None or not _is_image_data(asset_bytes):
        return _send_placeholder_image(
            self,
            GAME_BANNER_PLACEHOLDER_REL_PATH,
            target_width,
            target_height,
        )

    asset_key = f"asset-{asset_id_num}"
    _write_cached_image(self, "originals", asset_key, asset_bytes)
    return _send_stored_image(
        self,
        asset_key,
        target_width,
        target_height,
        placeholder_path=GAME_BANNER_PLACEHOLDER_REL_PATH,
    )


@server_path("/Game/Tools/ThumbnailAsset.ashx", commands={"GET"})
def thumbnail_asset(self: web_server_handler) -> bool:
    asset_id = self.query.get("aid")
    if asset_id is None:
        self.send_error(400)
        return True

    try:
        asset_id_num = int(asset_id)
    except ValueError:
        self.send_error(400)
        return True

    size_pair = None
    if (
        "wd" in self.query or
        "width" in self.query or
        "ht" in self.query or
        "height" in self.query
    ):
        size_pair = handle_resolution_check(
            self,
            width_parameters_name=["wd", "width"],
            height_parameters_name=["ht", "height"],
            allowed_widths=DEFAULT_IMAGE_SIZES,
            allowed_heights=DEFAULT_IMAGE_SIZES,
            must_be_square=False,
            can_round_to_nearest=True,
        )
        if size_pair is None:
            return True

    asset_bytes = _load_asset_bytes(self, asset_id_num)
    if asset_bytes is None or not _is_image_data(asset_bytes):
        if size_pair is None:
            return _send_placeholder_image(self, GAME_BANNER_PLACEHOLDER_REL_PATH)
        target_width, target_height = size_pair
        return _send_placeholder_image(
            self,
            GAME_BANNER_PLACEHOLDER_REL_PATH,
            target_width,
            target_height,
        )

    asset_key = f"asset-{asset_id_num}"
    _write_cached_image(self, "originals", asset_key, asset_bytes)

    if size_pair is None:
        _send_image_response(
            self,
            asset_bytes,
            _guess_image_content_type(asset_bytes),
        )
        return True

    target_width, target_height = size_pair
    return _send_stored_image(
        self,
        asset_key,
        target_width,
        target_height,
        placeholder_path=GAME_BANNER_PLACEHOLDER_REL_PATH,
    )


@server_path("/v1/batch", commands={"POST"})
def batch_image_request(self: web_server_handler) -> bool:
    try:
        json_data = _read_json_body(self)
    except gzip.BadGzipFile:
        self.send_json({"success": False, "message": "Invalid gzip data"}, 400)
        return True
    except Exception:
        self.send_json({"success": False, "message": "Invalid JSON data"}, 400)
        return True

    if json_data is None:
        self.send_json({"success": False, "message": "Missing JSON data"}, 400)
        return True
    if not isinstance(json_data, list):
        self.send_json({"success": False, "message": "JSON body must be an array"}, 400)
        return True

    if len(json_data) > MAX_BATCH_REQUESTS:
        self.send_json({"success": False, "message": "Too many requests"}, 400)
        return True
    if len(json_data) == 0:
        self.send_json({"data": []})
        return True

    processed_requests = []
    for request_obj in json_data:
        if not isinstance(request_obj, dict):
            continue
        if (
            "requestId" not in request_obj or
            "targetId" not in request_obj or
            "type" not in request_obj or
            "size" not in request_obj
        ):
            continue
        if request_obj["type"] not in BATCH_ALLOWED_TYPES:
            continue

        if "x" not in request_obj["size"]:
            continue
        split_size = request_obj["size"].split("x")
        if len(split_size) != 2:
            continue
        try:
            requested_width = int(split_size[0])
            requested_height = int(split_size[1])
            target_id = int(request_obj["targetId"])
        except (TypeError, ValueError):
            continue

        target_width = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - requested_width))
        target_height = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - requested_height))
        request_type = request_obj["type"]

        if request_type == "Avatar":
            image_url = _build_avatar_image_url(self, target_id, target_width, target_height)
            version = "TN3"
        elif request_type == "AvatarHeadShot":
            image_url = _build_headshot_image_url(self, target_id, target_width, target_height)
            version = "1"
        elif request_type == "GameIcon":
            _content_hash, place_id = _get_place_icon_hash(
                self,
                target_id,
                prefer_universe=True,
            )
            if place_id is None and _content_hash is None:
                continue
            image_url = _build_game_icon_url(self, place_id, target_width, target_height)
            version = None
        elif request_type in {"GameThumbnail", "Asset"}:
            image_url = _build_asset_thumbnail_url(self, target_id, target_width, target_height)
            version = None
        else:
            continue

        processed_requests.append({
            "requestId": request_obj["requestId"],
            "targetId": target_id,
            "state": "Completed",
            "imageUrl": image_url,
            "version": version,
        })

    self.send_json({"data": processed_requests})
    return True


@server_path("/Thumbs/Head.ashx", commands={"GET"})
@server_path("/headshot-thumbnail/image", commands={"GET"})
def headshot_thumbnail_image(self: web_server_handler) -> bool:
    user_id = self.query.get("userId")
    if user_id is None:
        self.send_error(400)
        return True

    try:
        user_id_num = int(user_id)
    except ValueError:
        self.send_error(400)
        return True

    size_pair = handle_resolution_check(
        self,
        width_parameters_name=["x", "width"],
        height_parameters_name=["y", "height"],
        allowed_widths=SQUARE_IMAGE_SIZES,
        allowed_heights=SQUARE_IMAGE_SIZES,
        must_be_square=True,
        can_round_to_nearest=True,
    )
    if size_pair is None:
        return True

    target_width, target_height = size_pair
    content_hash = None
    if _user_exists(self, user_id_num):
        content_hash = _get_user_thumbnail_hash(self, user_id_num, headshot=True)

    return _send_stored_image(
        self,
        content_hash,
        target_width,
        target_height,
        placeholder_path=USER_HEADSHOT_PLACEHOLDER_REL_PATH,
    )


@server_path("/v1/users/avatar-headshot", commands={"GET"})
def multi_avatar_headshot(self: web_server_handler) -> bool:
    user_ids_csv = self.query.get("userIds")
    if user_ids_csv is None:
        self.send_json({"errors": [{"code": 4, "message": "The requested Ids are invalid, of an invalid type or missing."}]}, 400)
        return True

    user_ids = user_ids_csv.split(",")
    if len(user_ids) > 100:
        self.send_json({"errors": [{"code": 1, "message": "There are too many requested Ids."}]}, 400)
        return True

    requested_size = self.query.get("size") or "48x48"
    try:
        size_width, size_height = requested_size.split("x", 1)
        target_width = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - int(size_width)))
        target_height = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - int(size_height)))
    except Exception:
        self.send_json({"errors": [{"code": 3, "message": "The requested size is invalid. Please see documentation for valid thumbnail size parameter name and format."}]}, 400)
        return True

    processed_requests = []
    for user_id in user_ids:
        try:
            user_id_num = int(user_id)
        except ValueError:
            continue

        processed_requests.append({
            "targetId": user_id_num,
            "state": "Completed",
            "imageUrl": _build_headshot_image_url(self, user_id_num, target_width, target_height),
            "version": "1",
        })

    self.send_json({"data": processed_requests})
    return True


@server_path("/v1/users/avatar-3d", commands={"GET"})
@util.auth.authenticated_required_api
def user_avatar_3d(self: web_server_handler) -> bool:
    self.send_json({
        "targetId": 1,
        "state": "Completed",
        "imageUrl": "https://t3.rbxcdn.com/30DAY-Avatar-310966282D3529E36976BF6B07B1DC90-Obj",
        "version": "TN3",
    }, 200)
    return True


@server_path("/v1/users/avatar", commands={"GET"})
@util.auth.authenticated_required_api
def multi_avatar(self: web_server_handler) -> bool:
    user_ids_csv = self.query.get("userIds")
    if user_ids_csv is None:
        self.send_json({"errors": [{"code": 4, "message": "The requested Ids are invalid, of an invalid type or missing."}]}, 400)
        return True

    user_ids = user_ids_csv.split(",")
    if len(user_ids) > 100:
        self.send_json({"errors": [{"code": 1, "message": "There are too many requested Ids."}]}, 400)
        return True

    requested_size = self.query.get("size") or "48x48"
    try:
        size_width, size_height = requested_size.split("x", 1)
        target_width = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - int(size_width)))
        target_height = min(DEFAULT_IMAGE_SIZES, key=lambda allowed: abs(allowed - int(size_height)))
    except Exception:
        self.send_json({"errors": [{"code": 3, "message": "The requested size is invalid. Please see documentation for valid thumbnail size parameter name and format."}]}, 400)
        return True

    processed_requests = []
    for user_id in user_ids:
        try:
            user_id_num = int(user_id)
        except ValueError:
            continue

        processed_requests.append({
            "targetId": user_id_num,
            "state": "Completed",
            "imageUrl": _build_avatar_image_url(self, user_id_num, target_width, target_height),
            "version": "TN3",
        })

    self.send_json({"data": processed_requests}, 200)
    return True
