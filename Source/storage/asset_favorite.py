import dataclasses
from datetime import datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class asset_favorite_item:
    id: int
    asset_id: int
    user_id: int
    created_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "asset_favorite"

    class field(enum.Enum):
        ID = '"id"'
        ASSET_ID = '"asset_id"'
        USER_ID = '"user_id"'
        CREATED_AT = '"created_at"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.ASSET_ID.value} INTEGER NOT NULL,
                {self.field.USER_ID.value} INTEGER NOT NULL,
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
        *,
        created_at: datetime | str | None = None,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.ASSET_ID.value},
                {self.field.USER_ID.value},
                {self.field.CREATED_AT.value}
            )
            VALUES (?, ?, ?)
            """,
            (
                asset_id,
                user_id,
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

    def check(
        self,
        asset_id: int,
        user_id: int,
    ) -> asset_favorite_item | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.CREATED_AT.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.ASSET_ID.value} = ?
            AND {self.field.USER_ID.value} = ?
            """,
            values=(asset_id, user_id),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return asset_favorite_item(
            id=int(row[0]),
            asset_id=asset_id,
            user_id=user_id,
            created_at=str(row[1]),
        )

    def set_favorite(
        self,
        asset_id: int,
        user_id: int,
        is_favorite: bool,
        *,
        created_at: datetime | str | None = None,
    ) -> None:
        if is_favorite:
            self.update(asset_id, user_id, created_at=created_at)
        else:
            self.delete(asset_id, user_id)

    def list_asset_ids_for_user(
        self,
        user_id: int,
        *,
        limit: int = 20,
    ) -> list[int]:
        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT {self.field.ASSET_ID.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            ORDER BY {self.field.CREATED_AT.value} DESC, {self.field.ID.value} DESC
            LIMIT ?
            """,
            values=(user_id, limit),
        )
        assert results is not None
        return [int(row[0]) for row in results]

    def get_totals_for_assets(
        self,
        asset_ids: list[int],
    ) -> dict[int, int]:
        if not asset_ids:
            return {}

        placeholders = ",".join("?" for _ in asset_ids)
        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ASSET_ID.value},
            COUNT(*)
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.ASSET_ID.value} IN ({placeholders})
            GROUP BY {self.field.ASSET_ID.value}
            """,
            values=tuple(asset_ids),
        )
        assert results is not None
        return {
            int(row[0]): int(row[1])
            for row in results
        }

    def get_favorited_asset_ids_for_user(
        self,
        user_id: int,
        asset_ids: list[int],
    ) -> set[int]:
        if not asset_ids:
            return set()

        placeholders = ",".join("?" for _ in asset_ids)
        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT {self.field.ASSET_ID.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            AND {self.field.ASSET_ID.value} IN ({placeholders})
            """,
            values=(user_id, *asset_ids),
        )
        assert results is not None
        return {
            int(row[0])
            for row in results
        }
