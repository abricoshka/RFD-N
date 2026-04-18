import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class friend_item:
    id: int
    requester_id: int
    requestee_id: int
    status: int
    created_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "friend"

    class field(enum.Enum):
        ID = '"id"'
        REQUESTER_ID = '"requester_id"'
        REQUESTEE_ID = '"requestee_id"'
        STATUS = '"status"'
        CREATED_AT = '"created_at"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.REQUESTER_ID.value} INTEGER NOT NULL,
                {self.field.REQUESTEE_ID.value} INTEGER NOT NULL,
                {self.field.STATUS.value} INTEGER NOT NULL DEFAULT 0,
                {self.field.CREATED_AT.value} DATETIME NOT NULL,
                UNIQUE (
                    {self.field.REQUESTER_ID.value},
                    {self.field.REQUESTEE_ID.value}
                ) ON CONFLICT REPLACE
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_requester_id"
            ON "{self.TABLE_NAME}" ({self.field.REQUESTER_ID.value});
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_requestee_id"
            ON "{self.TABLE_NAME}" ({self.field.REQUESTEE_ID.value});
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_status"
            ON "{self.TABLE_NAME}" ({self.field.STATUS.value});
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
        requester_id: int,
        requestee_id: int,
        *,
        status: int = 0,
        created_at: datetime | str | None = None,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.REQUESTER_ID.value},
                {self.field.REQUESTEE_ID.value},
                {self.field.STATUS.value},
                {self.field.CREATED_AT.value}
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                requester_id,
                requestee_id,
                status,
                self._normalise_timestamp(created_at),
            ),
        )

    def delete(
        self,
        requester_id: int,
        requestee_id: int,
    ) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.REQUESTER_ID.value} = ?
            AND {self.field.REQUESTEE_ID.value} = ?
            """,
            (requester_id, requestee_id),
        )

    def list_friend_ids(
        self,
        user_id: int,
        *,
        accepted_only: bool = True,
        limit: int | None = None,
    ) -> list[int]:
        filters = [
            f"({self.field.REQUESTER_ID.value} = ? OR {self.field.REQUESTEE_ID.value} = ?)",
        ]
        values: list[int] = [user_id, user_id]
        if accepted_only:
            filters.append(f"{self.field.STATUS.value} = ?")
            values.append(1)

        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            values.append(limit)

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT DISTINCT
            CASE
                WHEN {self.field.REQUESTER_ID.value} = ?
                THEN {self.field.REQUESTEE_ID.value}
                ELSE {self.field.REQUESTER_ID.value}
            END AS friend_id
            FROM "{self.TABLE_NAME}"
            WHERE {" AND ".join(filters)}
            ORDER BY {self.field.CREATED_AT.value} DESC, {self.field.ID.value} DESC
            {limit_clause}
            """,
            values=(user_id, *values),
        )
        assert results is not None
        return [int(row[0]) for row in results]
