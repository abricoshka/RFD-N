import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class follow_relationship_item:
    id: int
    follower_user_id: int
    followee_user_id: int
    created_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "follow_relationship"

    class field(enum.Enum):
        ID = '"id"'
        FOLLOWER_USER_ID = '"follower_user_id"'
        FOLLOWEE_USER_ID = '"followee_user_id"'
        CREATED_AT = '"created_at"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.FOLLOWER_USER_ID.value} INTEGER NOT NULL,
                {self.field.FOLLOWEE_USER_ID.value} INTEGER NOT NULL,
                {self.field.CREATED_AT.value} DATETIME NOT NULL,
                UNIQUE (
                    {self.field.FOLLOWER_USER_ID.value},
                    {self.field.FOLLOWEE_USER_ID.value}
                ) ON CONFLICT REPLACE
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_follower_user_id"
            ON "{self.TABLE_NAME}" ({self.field.FOLLOWER_USER_ID.value});
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_followee_user_id"
            ON "{self.TABLE_NAME}" ({self.field.FOLLOWEE_USER_ID.value});
            """,
        )

    @staticmethod
    def _normalise_timestamp(value: datetime | str | None) -> str:
        if value is None:
            return datetime.now(UTC).isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def update(
        self,
        follower_user_id: int,
        followee_user_id: int,
        *,
        created_at: datetime | str | None = None,
    ) -> follow_relationship_item:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.FOLLOWER_USER_ID.value},
                {self.field.FOLLOWEE_USER_ID.value},
                {self.field.CREATED_AT.value}
            )
            VALUES (?, ?, ?)
            """,
            (
                follower_user_id,
                followee_user_id,
                self._normalise_timestamp(created_at),
            ),
        )
        relationship = self.check(follower_user_id, followee_user_id)
        assert relationship is not None
        return relationship

    def delete(
        self,
        follower_user_id: int,
        followee_user_id: int,
    ) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.FOLLOWER_USER_ID.value} = ?
            AND {self.field.FOLLOWEE_USER_ID.value} = ?
            """,
            (follower_user_id, followee_user_id),
        )

    def check(
        self,
        follower_user_id: int,
        followee_user_id: int,
    ) -> follow_relationship_item | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.CREATED_AT.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.FOLLOWER_USER_ID.value} = ?
            AND {self.field.FOLLOWEE_USER_ID.value} = ?
            """,
            values=(follower_user_id, followee_user_id),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return follow_relationship_item(
            id=int(row[0]),
            follower_user_id=follower_user_id,
            followee_user_id=followee_user_id,
            created_at=str(row[1]),
        )

    def is_following(
        self,
        follower_user_id: int,
        followee_user_id: int,
    ) -> bool:
        return self.check(follower_user_id, followee_user_id) is not None

    def count_followers(self, followee_user_id: int) -> int:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT COUNT(*)
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.FOLLOWEE_USER_ID.value} = ?
            """,
            values=(followee_user_id,),
        )
        count = self.unwrap_result(result, only_first_field=True)
        return int(count or 0)

    def count_following(self, follower_user_id: int) -> int:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT COUNT(*)
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.FOLLOWER_USER_ID.value} = ?
            """,
            values=(follower_user_id,),
        )
        count = self.unwrap_result(result, only_first_field=True)
        return int(count or 0)
