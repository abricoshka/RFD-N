import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class friend_relationship_item:
    id: int
    user_id: int
    friend_id: int
    created_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "friend_relationship"

    class field(enum.Enum):
        ID = '"id"'
        USER_ID = '"user_id"'
        FRIEND_ID = '"friend_id"'
        CREATED_AT = '"created_at"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.USER_ID.value} INTEGER NOT NULL,
                {self.field.FRIEND_ID.value} INTEGER NOT NULL,
                {self.field.CREATED_AT.value} DATETIME NOT NULL,
                UNIQUE (
                    {self.field.USER_ID.value},
                    {self.field.FRIEND_ID.value}
                ) ON CONFLICT ABORT
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_user_id"
            ON "{self.TABLE_NAME}" ({self.field.USER_ID.value});
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_friend_id"
            ON "{self.TABLE_NAME}" ({self.field.FRIEND_ID.value});
            """,
        )

    @staticmethod
    def _normalise_timestamp(value: datetime | str | None) -> str:
        if value is None:
            return datetime.now(UTC).isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @staticmethod
    def _normalise_pair(user_id: int, friend_id: int) -> tuple[int, int]:
        return (
            (user_id, friend_id)
            if user_id < friend_id else
            (friend_id, user_id)
        )

    def update(
        self,
        user_id: int,
        friend_id: int,
        *,
        created_at: datetime | str | None = None,
    ) -> friend_relationship_item:
        normalized_user_id, normalized_friend_id = self._normalise_pair(
            user_id,
            friend_id,
        )
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.USER_ID.value},
                {self.field.FRIEND_ID.value},
                {self.field.CREATED_AT.value}
            )
            VALUES (?, ?, ?)
            ON CONFLICT(
                {self.field.USER_ID.value},
                {self.field.FRIEND_ID.value}
            )
            DO NOTHING
            """,
            (
                normalized_user_id,
                normalized_friend_id,
                self._normalise_timestamp(created_at),
            ),
        )
        relationship = self.check(user_id, friend_id)
        assert relationship is not None
        return relationship

    def delete(
        self,
        user_id: int,
        friend_id: int,
    ) -> None:
        normalized_user_id, normalized_friend_id = self._normalise_pair(
            user_id,
            friend_id,
        )
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            AND {self.field.FRIEND_ID.value} = ?
            """,
            (normalized_user_id, normalized_friend_id),
        )

    def check(
        self,
        user_id: int,
        friend_id: int,
    ) -> friend_relationship_item | None:
        normalized_user_id, normalized_friend_id = self._normalise_pair(
            user_id,
            friend_id,
        )
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.CREATED_AT.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            AND {self.field.FRIEND_ID.value} = ?
            """,
            values=(normalized_user_id, normalized_friend_id),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return friend_relationship_item(
            id=int(row[0]),
            user_id=normalized_user_id,
            friend_id=normalized_friend_id,
            created_at=str(row[1]),
        )

    def list_friend_ids(
        self,
        user_id: int,
        *,
        limit: int | None = None,
    ) -> list[int]:
        limit_clause = ""
        values: tuple[int, ...] | tuple[int, int] = (user_id, user_id)
        if limit is not None:
            limit_clause = "LIMIT ?"
            values = (user_id, user_id, limit)

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            CASE
                WHEN {self.field.USER_ID.value} = ?
                THEN {self.field.FRIEND_ID.value}
                ELSE {self.field.USER_ID.value}
            END AS friend_id
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            OR {self.field.FRIEND_ID.value} = ?
            ORDER BY {self.field.CREATED_AT.value} DESC, {self.field.ID.value} DESC
            {limit_clause}
            """,
            values=(user_id, *values),
        )
        assert results is not None
        return [int(row[0]) for row in results]

    def count_for_user(self, user_id: int) -> int:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT COUNT(*)
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            OR {self.field.FRIEND_ID.value} = ?
            """,
            values=(user_id, user_id),
        )
        count = self.unwrap_result(result, only_first_field=True)
        return int(count or 0)
