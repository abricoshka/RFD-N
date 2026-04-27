import enum
from typing import override

from . import _logic


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "user_avatar_asset"

    class field(enum.Enum):
        ID = '"id"'
        USER_ID = '"user_id"'
        ASSET_ID = '"asset_id"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.USER_ID.value} INTEGER NOT NULL,
                {self.field.ASSET_ID.value} INTEGER NOT NULL,
                UNIQUE (
                    {self.field.USER_ID.value},
                    {self.field.ASSET_ID.value}
                ) ON CONFLICT IGNORE
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

    def update(self, user_id: int, asset_id: int) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.USER_ID.value},
                {self.field.ASSET_ID.value}
            )
            VALUES (?, ?)
            """,
            (user_id, asset_id),
        )

    def delete_for_user(self, user_id: int) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            """,
            (user_id,),
        )

    def replace_for_user(self, user_id: int, asset_ids: list[int]) -> None:
        self.delete_for_user(user_id)
        for asset_id in asset_ids:
            self.update(user_id, asset_id)

    def list_asset_ids_for_user(self, user_id: int) -> list[int]:
        result = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT {self.field.ASSET_ID.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.USER_ID.value} = ?
            ORDER BY {self.field.ID.value} ASC
            """,
            values=(user_id,),
        )
        assert result is not None
        return [int(row[0]) for row in result]
