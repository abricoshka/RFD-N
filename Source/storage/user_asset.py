import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class user_asset_item:
    id: int
    user_id: int
    asset_id: int
    serial: int | None
    price: int
    created: str
    updated: str
    is_for_sale: bool


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "user_asset"

    class field(enum.Enum):
        ID = '"id"'
        USER_ID = '"user_id"'
        ASSET_ID = '"asset_id"'
        SERIAL = '"serial"'
        PRICE = '"price"'
        CREATED = '"created"'
        UPDATED = '"updated"'
        IS_FOR_SALE = '"is_for_sale"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.USER_ID.value} INTEGER NOT NULL,
                {self.field.ASSET_ID.value} INTEGER NOT NULL,
                {self.field.SERIAL.value} INTEGER,
                {self.field.PRICE.value} INTEGER NOT NULL DEFAULT 0,
                {self.field.CREATED.value} DATETIME NOT NULL,
                {self.field.UPDATED.value} DATETIME NOT NULL,
                {self.field.IS_FOR_SALE.value} BOOLEAN NOT NULL DEFAULT FALSE,
                UNIQUE (
                    {self.field.USER_ID.value},
                    {self.field.ASSET_ID.value}
                ) ON CONFLICT REPLACE
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
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_asset_id"
            ON "{self.TABLE_NAME}" ({self.field.ASSET_ID.value});
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
        user_id: int,
        asset_id: int,
        *,
        serial: int | None = None,
        price: int = 0,
        created: datetime | str | None = None,
        updated: datetime | str | None = None,
        is_for_sale: bool = False,
    ) -> None:
        resolved_created = self._normalise_timestamp(created)
        resolved_updated = self._normalise_timestamp(updated or created)
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.USER_ID.value},
                {self.field.ASSET_ID.value},
                {self.field.SERIAL.value},
                {self.field.PRICE.value},
                {self.field.CREATED.value},
                {self.field.UPDATED.value},
                {self.field.IS_FOR_SALE.value}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                asset_id,
                serial,
                price,
                resolved_created,
                resolved_updated,
                is_for_sale,
            ),
        )

    def check(
        self,
        user_id: int,
        asset_id: int,
    ) -> user_asset_item | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.SERIAL.value},
            {self.field.PRICE.value},
            {self.field.CREATED.value},
            {self.field.UPDATED.value},
            {self.field.IS_FOR_SALE.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            AND {self.field.ASSET_ID.value} = ?
            """,
            values=(user_id, asset_id),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return user_asset_item(
            id=int(row[0]),
            user_id=user_id,
            asset_id=asset_id,
            serial=None if row[1] is None else int(row[1]),
            price=int(row[2]),
            created=str(row[3]),
            updated=str(row[4]),
            is_for_sale=bool(row[5]),
        )

    def list_asset_ids_for_user(
        self,
        user_id: int,
        *,
        limit: int = 30,
        is_for_sale: bool | None = None,
    ) -> list[int]:
        filters = [f"{self.field.USER_ID.value} = ?"]
        values: list[int | bool] = [user_id]
        if is_for_sale is not None:
            filters.append(f"{self.field.IS_FOR_SALE.value} = ?")
            values.append(is_for_sale)

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT {self.field.ASSET_ID.value}
            FROM "{self.TABLE_NAME}"
            WHERE {" AND ".join(filters)}
            ORDER BY {self.field.UPDATED.value} DESC, {self.field.ID.value} DESC
            LIMIT ?
            """,
            values=(*values, limit),
        )
        assert results is not None
        return [int(row[0]) for row in results]
