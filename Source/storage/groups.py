import dataclasses
from datetime import datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class group_item:
    id: int
    owner_id: int | None
    name: str
    description: str
    created_at: str
    updated_at: str
    locked: bool


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "groups"

    class field(enum.Enum):
        ID = '"id"'
        OWNER_ID = '"owner_id"'
        NAME = '"name"'
        DESCRIPTION = '"description"'
        CREATED_AT = '"created_at"'
        UPDATED_AT = '"updated_at"'
        LOCKED = '"locked"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY NOT NULL,
                {self.field.OWNER_ID.value} INTEGER,
                {self.field.NAME.value} TEXT NOT NULL,
                {self.field.DESCRIPTION.value} TEXT NOT NULL,
                {self.field.CREATED_AT.value} DATETIME NOT NULL,
                {self.field.UPDATED_AT.value} DATETIME NOT NULL,
                {self.field.LOCKED.value} BOOLEAN NOT NULL DEFAULT FALSE
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_owner_id"
            ON "{self.TABLE_NAME}" ({self.field.OWNER_ID.value});
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
        group_id: int,
        name: str,
        description: str = "",
        *,
        owner_id: int | None = None,
        created_at: datetime | str | None = None,
        updated_at: datetime | str | None = None,
        locked: bool = False,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.ID.value},
                {self.field.OWNER_ID.value},
                {self.field.NAME.value},
                {self.field.DESCRIPTION.value},
                {self.field.CREATED_AT.value},
                {self.field.UPDATED_AT.value},
                {self.field.LOCKED.value}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT({self.field.ID.value})
            DO UPDATE SET
                {self.field.OWNER_ID.value} = excluded.{self.field.OWNER_ID.value},
                {self.field.NAME.value} = excluded.{self.field.NAME.value},
                {self.field.DESCRIPTION.value} = excluded.{self.field.DESCRIPTION.value},
                {self.field.UPDATED_AT.value} = excluded.{self.field.UPDATED_AT.value},
                {self.field.LOCKED.value} = excluded.{self.field.LOCKED.value}
            """,
            (
                group_id,
                owner_id,
                name,
                description,
                self._normalise_timestamp(created_at),
                self._normalise_timestamp(updated_at),
                locked,
            ),
        )

    def check_object(
        self,
        group_id: int,
    ) -> group_item | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.OWNER_ID.value},
            {self.field.NAME.value},
            {self.field.DESCRIPTION.value},
            {self.field.CREATED_AT.value},
            {self.field.UPDATED_AT.value},
            {self.field.LOCKED.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.ID.value} = ?
            """,
            values=(group_id,),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return group_item(
            id=group_id,
            owner_id=None if row[0] is None else int(row[0]),
            name=str(row[1]),
            description=str(row[2]),
            created_at=str(row[3]),
            updated_at=str(row[4]),
            locked=bool(row[5]),
        )
