import dataclasses
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class user_avatar_item:
    user_id: int
    content_hash: str | None
    avatar_type: int
    head_color_id: int
    torso_color_id: int
    right_arm_color_id: int
    left_arm_color_id: int
    right_leg_color_id: int
    left_leg_color_id: int
    r15: bool
    height_scale: float
    width_scale: float
    head_scale: float
    depth_scale: float
    proportion_scale: float
    body_type_scale: float


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "user_avatar"

    class field(enum.Enum):
        USER_ID = '"user_id"'
        CONTENT_HASH = '"content_hash"'
        AVATAR_TYPE = '"avatar_type"'
        HEAD_COLOR_ID = '"head_color_id"'
        TORSO_COLOR_ID = '"torso_color_id"'
        RIGHT_ARM_COLOR_ID = '"right_arm_color_id"'
        LEFT_ARM_COLOR_ID = '"left_arm_color_id"'
        RIGHT_LEG_COLOR_ID = '"right_leg_color_id"'
        LEFT_LEG_COLOR_ID = '"left_leg_color_id"'
        R15 = '"r15"'
        HEIGHT_SCALE = '"height_scale"'
        WIDTH_SCALE = '"width_scale"'
        HEAD_SCALE = '"head_scale"'
        DEPTH_SCALE = '"depth_scale"'
        PROPORTION_SCALE = '"proportion_scale"'
        BODY_TYPE_SCALE = '"body_type_scale"'

    DEFAULT_BODY_COLOR_ID = 1001

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.USER_ID.value} INTEGER PRIMARY KEY NOT NULL,
                {self.field.CONTENT_HASH.value} TEXT,
                {self.field.AVATAR_TYPE.value} INTEGER NOT NULL DEFAULT 1,
                {self.field.HEAD_COLOR_ID.value} INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID},
                {self.field.TORSO_COLOR_ID.value} INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID},
                {self.field.RIGHT_ARM_COLOR_ID.value} INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID},
                {self.field.LEFT_ARM_COLOR_ID.value} INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID},
                {self.field.RIGHT_LEG_COLOR_ID.value} INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID},
                {self.field.LEFT_LEG_COLOR_ID.value} INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID},
                {self.field.R15.value} BOOLEAN NOT NULL DEFAULT FALSE,
                {self.field.HEIGHT_SCALE.value} REAL NOT NULL DEFAULT 1.0,
                {self.field.WIDTH_SCALE.value} REAL NOT NULL DEFAULT 1.0,
                {self.field.HEAD_SCALE.value} REAL NOT NULL DEFAULT 1.0,
                {self.field.DEPTH_SCALE.value} REAL NOT NULL DEFAULT 1.0,
                {self.field.PROPORTION_SCALE.value} REAL NOT NULL DEFAULT 0.0,
                {self.field.BODY_TYPE_SCALE.value} REAL NOT NULL DEFAULT 0.0
            );
            """,
        )
        self._ensure_column(self.field.CONTENT_HASH, "TEXT")
        self._ensure_column(self.field.AVATAR_TYPE, "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(
            self.field.HEAD_COLOR_ID,
            f"INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID}",
        )
        self._ensure_column(
            self.field.TORSO_COLOR_ID,
            f"INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID}",
        )
        self._ensure_column(
            self.field.RIGHT_ARM_COLOR_ID,
            f"INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID}",
        )
        self._ensure_column(
            self.field.LEFT_ARM_COLOR_ID,
            f"INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID}",
        )
        self._ensure_column(
            self.field.RIGHT_LEG_COLOR_ID,
            f"INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID}",
        )
        self._ensure_column(
            self.field.LEFT_LEG_COLOR_ID,
            f"INTEGER NOT NULL DEFAULT {self.DEFAULT_BODY_COLOR_ID}",
        )
        self._ensure_column(self.field.R15, "BOOLEAN NOT NULL DEFAULT FALSE")
        self._ensure_column(self.field.HEIGHT_SCALE, "REAL NOT NULL DEFAULT 1.0")
        self._ensure_column(self.field.WIDTH_SCALE, "REAL NOT NULL DEFAULT 1.0")
        self._ensure_column(self.field.HEAD_SCALE, "REAL NOT NULL DEFAULT 1.0")
        self._ensure_column(self.field.DEPTH_SCALE, "REAL NOT NULL DEFAULT 1.0")
        self._ensure_column(self.field.PROPORTION_SCALE, "REAL NOT NULL DEFAULT 0.0")
        self._ensure_column(self.field.BODY_TYPE_SCALE, "REAL NOT NULL DEFAULT 0.0")

    def _ensure_column(self, field: "database.field", definition: str) -> None:
        column_name = field.value.strip('"')
        result = self.sqlite.execute_and_fetch(
            query=f'PRAGMA table_info("{self.TABLE_NAME}")',
        )
        assert result is not None
        if any(str(row[1]) == column_name for row in result):
            return

        self.sqlite.execute(
            f"""
            ALTER TABLE "{self.TABLE_NAME}"
            ADD COLUMN {field.value} {definition}
            """,
        )

    def update(
        self,
        user_id: int,
        *,
        content_hash: str | None = None,
        avatar_type: int = 1,
        head_color_id: int = DEFAULT_BODY_COLOR_ID,
        torso_color_id: int = DEFAULT_BODY_COLOR_ID,
        right_arm_color_id: int = DEFAULT_BODY_COLOR_ID,
        left_arm_color_id: int = DEFAULT_BODY_COLOR_ID,
        right_leg_color_id: int = DEFAULT_BODY_COLOR_ID,
        left_leg_color_id: int = DEFAULT_BODY_COLOR_ID,
        r15: bool = False,
        height_scale: float = 1.0,
        width_scale: float = 1.0,
        head_scale: float = 1.0,
        depth_scale: float = 1.0,
        proportion_scale: float = 0.0,
        body_type_scale: float = 0.0,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.USER_ID.value},
                {self.field.CONTENT_HASH.value},
                {self.field.AVATAR_TYPE.value},
                {self.field.HEAD_COLOR_ID.value},
                {self.field.TORSO_COLOR_ID.value},
                {self.field.RIGHT_ARM_COLOR_ID.value},
                {self.field.LEFT_ARM_COLOR_ID.value},
                {self.field.RIGHT_LEG_COLOR_ID.value},
                {self.field.LEFT_LEG_COLOR_ID.value},
                {self.field.R15.value},
                {self.field.HEIGHT_SCALE.value},
                {self.field.WIDTH_SCALE.value},
                {self.field.HEAD_SCALE.value},
                {self.field.DEPTH_SCALE.value},
                {self.field.PROPORTION_SCALE.value},
                {self.field.BODY_TYPE_SCALE.value}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT({self.field.USER_ID.value})
            DO UPDATE SET
                {self.field.CONTENT_HASH.value} = excluded.{self.field.CONTENT_HASH.value},
                {self.field.AVATAR_TYPE.value} = excluded.{self.field.AVATAR_TYPE.value},
                {self.field.HEAD_COLOR_ID.value} = excluded.{self.field.HEAD_COLOR_ID.value},
                {self.field.TORSO_COLOR_ID.value} = excluded.{self.field.TORSO_COLOR_ID.value},
                {self.field.RIGHT_ARM_COLOR_ID.value} = excluded.{self.field.RIGHT_ARM_COLOR_ID.value},
                {self.field.LEFT_ARM_COLOR_ID.value} = excluded.{self.field.LEFT_ARM_COLOR_ID.value},
                {self.field.RIGHT_LEG_COLOR_ID.value} = excluded.{self.field.RIGHT_LEG_COLOR_ID.value},
                {self.field.LEFT_LEG_COLOR_ID.value} = excluded.{self.field.LEFT_LEG_COLOR_ID.value},
                {self.field.R15.value} = excluded.{self.field.R15.value},
                {self.field.HEIGHT_SCALE.value} = excluded.{self.field.HEIGHT_SCALE.value},
                {self.field.WIDTH_SCALE.value} = excluded.{self.field.WIDTH_SCALE.value},
                {self.field.HEAD_SCALE.value} = excluded.{self.field.HEAD_SCALE.value},
                {self.field.DEPTH_SCALE.value} = excluded.{self.field.DEPTH_SCALE.value},
                {self.field.PROPORTION_SCALE.value} = excluded.{self.field.PROPORTION_SCALE.value},
                {self.field.BODY_TYPE_SCALE.value} = excluded.{self.field.BODY_TYPE_SCALE.value}
            """,
            (
                user_id,
                content_hash,
                avatar_type,
                head_color_id,
                torso_color_id,
                right_arm_color_id,
                left_arm_color_id,
                right_leg_color_id,
                left_leg_color_id,
                r15,
                height_scale,
                width_scale,
                head_scale,
                depth_scale,
                proportion_scale,
                body_type_scale,
            ),
        )

    def check(
        self,
        user_id: int,
    ) -> tuple[
        str | None,
        int,
        int,
        int,
        int,
        int,
        int,
        int,
        bool,
        float,
        float,
        float,
        float,
        float,
        float,
    ] | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.CONTENT_HASH.value},
            {self.field.AVATAR_TYPE.value},
            {self.field.HEAD_COLOR_ID.value},
            {self.field.TORSO_COLOR_ID.value},
            {self.field.RIGHT_ARM_COLOR_ID.value},
            {self.field.LEFT_ARM_COLOR_ID.value},
            {self.field.RIGHT_LEG_COLOR_ID.value},
            {self.field.LEFT_LEG_COLOR_ID.value},
            {self.field.R15.value},
            {self.field.HEIGHT_SCALE.value},
            {self.field.WIDTH_SCALE.value},
            {self.field.HEAD_SCALE.value},
            {self.field.DEPTH_SCALE.value},
            {self.field.PROPORTION_SCALE.value},
            {self.field.BODY_TYPE_SCALE.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            """,
            values=(user_id,),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None
        return (
            None if row[0] is None else str(row[0]),
            int(row[1]),
            int(row[2]),
            int(row[3]),
            int(row[4]),
            int(row[5]),
            int(row[6]),
            int(row[7]),
            bool(row[8]),
            float(row[9]),
            float(row[10]),
            float(row[11]),
            float(row[12]),
            float(row[13]),
            float(row[14]),
        )

    def check_object(self, user_id: int) -> user_avatar_item | None:
        row = self.check(user_id)
        if row is None:
            return None
        return user_avatar_item(
            user_id=user_id,
            content_hash=row[0],
            avatar_type=row[1],
            head_color_id=row[2],
            torso_color_id=row[3],
            right_arm_color_id=row[4],
            left_arm_color_id=row[5],
            right_leg_color_id=row[6],
            left_leg_color_id=row[7],
            r15=row[8],
            height_scale=row[9],
            width_scale=row[10],
            head_scale=row[11],
            depth_scale=row[12],
            proportion_scale=row[13],
            body_type_scale=row[14],
        )

    def ensure(self, user_id: int) -> user_avatar_item:
        avatar = self.check_object(user_id)
        if avatar is not None:
            return avatar

        self.update(user_id)
        created_avatar = self.check_object(user_id)
        assert created_avatar is not None
        return created_avatar
