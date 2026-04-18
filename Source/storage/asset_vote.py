import dataclasses
from datetime import datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class asset_vote_item:
    id: int
    asset_id: int
    user_id: int
    vote: bool
    created_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "asset_vote"

    class field(enum.Enum):
        ID = '"id"'
        ASSET_ID = '"asset_id"'
        USER_ID = '"user_id"'
        VOTE = '"vote"'
        CREATED_AT = '"created_at"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.ASSET_ID.value} INTEGER NOT NULL,
                {self.field.USER_ID.value} INTEGER NOT NULL,
                {self.field.VOTE.value} BOOLEAN NOT NULL,
                {self.field.CREATED_AT.value} DATETIME NOT NULL,
                UNIQUE (
                    {self.field.ASSET_ID.value},
                    {self.field.USER_ID.value}
                ) ON CONFLICT REPLACE
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_asset_id"
            ON "{self.TABLE_NAME}" ({self.field.ASSET_ID.value});
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_user_id"
            ON "{self.TABLE_NAME}" ({self.field.USER_ID.value});
            """,
        )

    @staticmethod
    def _normalise_timestamp(value: datetime | str | None) -> str:
        if value is None:
            return datetime.utcnow().isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def update(
        self,
        asset_id: int,
        user_id: int,
        vote: bool,
        *,
        created_at: datetime | str | None = None,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.ASSET_ID.value},
                {self.field.USER_ID.value},
                {self.field.VOTE.value},
                {self.field.CREATED_AT.value}
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                asset_id,
                user_id,
                vote,
                self._normalise_timestamp(created_at),
            ),
        )

    def delete(
        self,
        asset_id: int,
        user_id: int,
    ) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.ASSET_ID.value} = ?
            AND {self.field.USER_ID.value} = ?
            """,
            (asset_id, user_id),
        )

    def get_user_vote(
        self,
        asset_id: int,
        user_id: int,
    ) -> bool | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT {self.field.VOTE.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.ASSET_ID.value} = ?
            AND {self.field.USER_ID.value} = ?
            """,
            values=(asset_id, user_id),
        )
        value = self.unwrap_result(result, only_first_field=True)
        if value is None:
            return None
        return bool(value)

    def get_totals_for_assets(
        self,
        asset_ids: list[int],
    ) -> dict[int, tuple[int, int]]:
        if not asset_ids:
            return {}

        placeholders = ",".join("?" for _ in asset_ids)
        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ASSET_ID.value},
            SUM(CASE WHEN {self.field.VOTE.value} = TRUE THEN 1 ELSE 0 END),
            SUM(CASE WHEN {self.field.VOTE.value} = FALSE THEN 1 ELSE 0 END)
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.ASSET_ID.value} IN ({placeholders})
            GROUP BY {self.field.ASSET_ID.value}
            """,
            values=tuple(asset_ids),
        )
        assert results is not None
        return {
            int(row[0]): (
                int(row[1] or 0),
                int(row[2] or 0),
            )
            for row in results
        }
