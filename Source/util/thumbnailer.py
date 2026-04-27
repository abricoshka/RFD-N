from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import storage

# TODO: Proper implementation

def _build_avatar_hash(
    data_storage: "storage.storager",
    user_id: int,
) -> str:
    avatar = data_storage.user_avatar.ensure(user_id)
    asset_ids = data_storage.user_avatar_asset.list_asset_ids_for_user(user_id)
    hash_source = "|".join(
        [
            ",".join(str(asset_id) for asset_id in asset_ids),
            str(avatar.head_color_id),
            str(avatar.torso_color_id),
            str(avatar.left_arm_color_id),
            str(avatar.right_arm_color_id),
            str(avatar.left_leg_color_id),
            str(avatar.right_leg_color_id),
            str(int(avatar.r15)),
            str(avatar.height_scale),
            str(avatar.width_scale),
            str(avatar.head_scale),
            str(avatar.depth_scale),
            str(avatar.proportion_scale),
            str(avatar.body_type_scale),
        ],
    )
    return hashlib.sha256(hash_source.encode("utf-8")).hexdigest()


def TakeUserThumbnail(
    data_storage: "storage.storager",
    user_id: int,
    bypassCooldown: bool = False,
    bypassCache: bool = False,
) -> str:
    del bypassCooldown
    del bypassCache

    avatar = data_storage.user_avatar.ensure(user_id)
    avatar_hash = _build_avatar_hash(data_storage, user_id)
    if avatar.content_hash != avatar_hash:
        data_storage.user_avatar.update(
            user_id,
            content_hash=avatar_hash,
            avatar_type=avatar.avatar_type,
            head_color_id=avatar.head_color_id,
            torso_color_id=avatar.torso_color_id,
            right_arm_color_id=avatar.right_arm_color_id,
            left_arm_color_id=avatar.left_arm_color_id,
            right_leg_color_id=avatar.right_leg_color_id,
            left_leg_color_id=avatar.left_leg_color_id,
            r15=avatar.r15,
            height_scale=avatar.height_scale,
            width_scale=avatar.width_scale,
            head_scale=avatar.head_scale,
            depth_scale=avatar.depth_scale,
            proportion_scale=avatar.proportion_scale,
            body_type_scale=avatar.body_type_scale,
        )
        data_storage.userthumbnail.update(
            userid=user_id,
            full_contenthash=None,
            headshot_contenthash=None,
            updated_at=datetime.now(UTC).isoformat(),
        )
        return "Thumbnail invalidated"

    existing_thumbnail = data_storage.userthumbnail.check(user_id)
    if existing_thumbnail is None:
        data_storage.userthumbnail.update(
            userid=user_id,
            full_contenthash=None,
            headshot_contenthash=None,
            updated_at=datetime.now(UTC).isoformat(),
        )
    return "Thumbnail unchanged"
