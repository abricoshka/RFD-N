import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class friend_request_item:
    id: int
    requester_id: int
    requestee_id: int
    created_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "friend_request"

    class field(enum.Enum):
        ID = '"id"'
        REQUESTER_ID = '"requester_id"'
        REQUESTEE_ID = '"requestee_id"'
        CREATED_AT = '"created_at"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.REQUESTER_ID.value} INTEGER NOT NULL,
                {self.field.REQUESTEE_ID.value} INTEGER NOT NULL,
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
        created_at: datetime | str | None = None,
    ) -> friend_request_item:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.REQUESTER_ID.value},
                {self.field.REQUESTEE_ID.value},
                {self.field.CREATED_AT.value}
            )
            VALUES (?, ?, ?)
            """,
            (
                requester_id,
                requestee_id,
                self._normalise_timestamp(created_at),
            ),
        )
        request = self.check(requester_id, requestee_id)
        assert request is not None
        return request

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

    def delete_all_for_requestee(self, requestee_id: int) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.REQUESTEE_ID.value} = ?
            """,
            (requestee_id,),
        )

    def check(
        self,
        requester_id: int,
        requestee_id: int,
    ) -> friend_request_item | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.CREATED_AT.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.REQUESTER_ID.value} = ?
            AND {self.field.REQUESTEE_ID.value} = ?
            """,
            values=(requester_id, requestee_id),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return friend_request_item(
            id=int(row[0]),
            requester_id=requester_id,
            requestee_id=requestee_id,
            created_at=str(row[1]),
        )

    def count_for_requestee(self, requestee_id: int) -> int:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT COUNT(*)
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.REQUESTEE_ID.value} = ?
            """,
            values=(requestee_id,),
        )
        count = self.unwrap_result(result, only_first_field=True)
        return int(count or 0)

    def list_requester_ids_for_requestee(
        self,
        requestee_id: int,
        *,
        limit: int | None = None,
    ) -> list[int]:
        limit_clause = ""
        values: tuple[int, ...] | tuple[int, int] = (requestee_id,)
        if limit is not None:
            limit_clause = "LIMIT ?"
            values = (requestee_id, limit)

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT {self.field.REQUESTER_ID.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.REQUESTEE_ID.value} = ?
            ORDER BY {self.field.CREATED_AT.value} DESC, {self.field.ID.value} DESC
            {limit_clause}
            """,
            values=values,
        )
        assert results is not None
        return [int(row[0]) for row in results]
