import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class previously_played_item:
    id: int
    user_id: int
    place_id: int
    last_played: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "previously_played"

    class field(enum.Enum):
        ID = '"id"'
        USER_ID = '"user_id"'
        PLACE_ID = '"place_id"'
        LAST_PLAYED = '"last_played"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.USER_ID.value} INTEGER NOT NULL,
                {self.field.PLACE_ID.value} INTEGER NOT NULL,
                {self.field.LAST_PLAYED.value} DATETIME NOT NULL,
                UNIQUE (
                    {self.field.USER_ID.value},
                    {self.field.PLACE_ID.value}
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
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_place_id"
            ON "{self.TABLE_NAME}" ({self.field.PLACE_ID.value});
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
        place_id: int,
        *,
        last_played: datetime | str | None = None,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.USER_ID.value},
                {self.field.PLACE_ID.value},
                {self.field.LAST_PLAYED.value}
            )
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                place_id,
                self._normalise_timestamp(last_played),
            ),
        )

    def check(
        self,
        user_id: int,
        place_id: int,
    ) -> previously_played_item | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.LAST_PLAYED.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            AND {self.field.PLACE_ID.value} = ?
            """,
            values=(user_id, place_id),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return previously_played_item(
            id=int(row[0]),
            user_id=user_id,
            place_id=place_id,
            last_played=str(row[1]),
        )
