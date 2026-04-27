from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage import storager


def user_has_verified_badge(
    storage: "storager",
    user_id: int,
) -> bool:
    user = storage.user.check_object(user_id)
    return bool(user is not None and user.is_verified)


def group_has_verified_badge(
    storage: "storager",
    group_id: int,
) -> bool:
    group = storage.group.check_object(group_id)
    return bool(group is not None and group.is_verified)


def creator_has_verified_badge(
    storage: "storager",
    creator_type: int,
    creator_id: int,
) -> bool:
    if creator_type == 0:
        return user_has_verified_badge(storage, creator_id)
    return group_has_verified_badge(storage, creator_id)
