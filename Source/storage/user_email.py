import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class user_email_item:
    user_id: int
    email: str
    verified: bool
    updated_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "user_email"

    class field(enum.Enum):
        USER_ID = '"user_id"'
        EMAIL = '"email"'
        VERIFIED = '"verified"'
        UPDATED_AT = '"updated_at"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.USER_ID.value} INTEGER NOT NULL,
                {self.field.EMAIL.value} TEXT NOT NULL,
                {self.field.VERIFIED.value} BOOLEAN NOT NULL DEFAULT FALSE,
                {self.field.UPDATED_AT.value} DATETIME NOT NULL,
                PRIMARY KEY(
                    {self.field.USER_ID.value}
                ) ON CONFLICT REPLACE
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_email"
            ON "{self.TABLE_NAME}" ({self.field.EMAIL.value});
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
        email: str,
        verified: bool = False,
        *,
        updated_at: datetime | str | None = None,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.USER_ID.value},
                {self.field.EMAIL.value},
                {self.field.VERIFIED.value},
                {self.field.UPDATED_AT.value}
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                email,
                verified,
                self._normalise_timestamp(updated_at),
            ),
        )

    def check(
        self,
        user_id: int,
    ) -> tuple[str, bool, str] | None:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.EMAIL.value},
            {self.field.VERIFIED.value},
            {self.field.UPDATED_AT.value}

            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            """,
            values=(user_id,),
        )
        row = self.unwrap_result(result)
        if row is None:
            return None

        return (
            str(row[0]),
            bool(row[1]),
            str(row[2]),
        )

    def check_object(
        self,
        user_id: int,
    ) -> user_email_item | None:
        row = self.check(user_id)
        if row is None:
            return None
        return user_email_item(
            user_id=user_id,
            email=row[0],
            verified=row[1],
            updated_at=row[2],
        )

    def delete(
        self,
        user_id: int,
    ) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            """,
            (user_id,),
        )
