import dataclasses
from datetime import UTC, datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class ingame_player_item:
    id: int
    server_uuid: str
    user_id: int
    join_time: str
    last_heartbeat: str
    is_guest: bool


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "ingame_player"

    class field(enum.Enum):
        ID = '"id"'
        SERVER_UUID = '"server_uuid"'
        USER_ID = '"user_id"'
        JOIN_TIME = '"join_time"'
        LAST_HEARTBEAT = '"last_heartbeat"'
        IS_GUEST = '"is_guest"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.SERVER_UUID.value} TEXT NOT NULL,
                {self.field.USER_ID.value} INTEGER NOT NULL,
                {self.field.JOIN_TIME.value} DATETIME NOT NULL,
                {self.field.LAST_HEARTBEAT.value} DATETIME NOT NULL,
                {self.field.IS_GUEST.value} BOOLEAN NOT NULL DEFAULT FALSE,
                UNIQUE (
                    {self.field.SERVER_UUID.value},
                    {self.field.USER_ID.value}
                ) ON CONFLICT REPLACE
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_server_uuid"
            ON "{self.TABLE_NAME}" ({self.field.SERVER_UUID.value});
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
            return datetime.now(UTC).isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def update(
        self,
        server_uuid: str,
        user_id: int,
        *,
        join_time: datetime | str | None = None,
        last_heartbeat: datetime | str | None = None,
        is_guest: bool = False,
    ) -> None:
        resolved_join_time = self._normalise_timestamp(join_time)
        resolved_last_heartbeat = self._normalise_timestamp(last_heartbeat or join_time)
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.SERVER_UUID.value},
                {self.field.USER_ID.value},
                {self.field.JOIN_TIME.value},
                {self.field.LAST_HEARTBEAT.value},
                {self.field.IS_GUEST.value}
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                server_uuid,
                user_id,
                resolved_join_time,
                resolved_last_heartbeat,
                is_guest,
            ),
        )

    def delete(
        self,
        server_uuid: str,
        user_id: int,
    ) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.SERVER_UUID.value} = ?
            AND {self.field.USER_ID.value} = ?
            """,
            (server_uuid, user_id),
        )

    def list_for_server_uuids(
        self,
        server_uuids: list[str],
        *,
        include_guests: bool = False,
    ) -> list[ingame_player_item]:
        if not server_uuids:
            return []

        placeholders = ",".join("?" for _ in server_uuids)
        values: list[str | int] = list(server_uuids)
        filters = [f"{self.field.SERVER_UUID.value} IN ({placeholders})"]
        if not include_guests:
            filters.append(f"{self.field.IS_GUEST.value} = FALSE")

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.SERVER_UUID.value},
            {self.field.USER_ID.value},
            {self.field.JOIN_TIME.value},
            {self.field.LAST_HEARTBEAT.value},
            {self.field.IS_GUEST.value}
            FROM "{self.TABLE_NAME}"
            WHERE {" AND ".join(filters)}
            ORDER BY {self.field.JOIN_TIME.value} ASC, {self.field.ID.value} ASC
            """,
            values=tuple(values),
        )
        assert results is not None
        return [
            ingame_player_item(
                id=int(row[0]),
                server_uuid=str(row[1]),
                user_id=int(row[2]),
                join_time=str(row[3]),
                last_heartbeat=str(row[4]),
                is_guest=bool(row[5]),
            )
            for row in results
        ]

    def list_for_user_ids(
        self,
        user_ids: list[int],
        *,
        include_guests: bool = False,
    ) -> list[ingame_player_item]:
        if not user_ids:
            return []

        placeholders = ",".join("?" for _ in user_ids)
        values: list[int] = list(user_ids)
        filters = [f"{self.field.USER_ID.value} IN ({placeholders})"]
        if not include_guests:
            filters.append(f"{self.field.IS_GUEST.value} = FALSE")

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.ID.value},
            {self.field.SERVER_UUID.value},
            {self.field.USER_ID.value},
            {self.field.JOIN_TIME.value},
            {self.field.LAST_HEARTBEAT.value},
            {self.field.IS_GUEST.value}
            FROM "{self.TABLE_NAME}"
            WHERE {" AND ".join(filters)}
            ORDER BY {self.field.JOIN_TIME.value} ASC, {self.field.ID.value} ASC
            """,
            values=tuple(values),
        )
        assert results is not None
        return [
            ingame_player_item(
                id=int(row[0]),
                server_uuid=str(row[1]),
                user_id=int(row[2]),
                join_time=str(row[3]),
                last_heartbeat=str(row[4]),
                is_guest=bool(row[5]),
            )
            for row in results
        ]

    def get_latest_for_user_ids(
        self,
        user_ids: list[int],
        *,
        include_guests: bool = False,
    ) -> dict[int, ingame_player_item]:
        if not user_ids:
            return {}

        rows = self.list_for_user_ids(
            user_ids,
            include_guests=include_guests,
        )
        rows.sort(
            key=lambda row: (
                row.last_heartbeat,
                row.join_time,
                row.id,
            ),
        )

        latest_rows: dict[int, ingame_player_item] = {}
        for row in reversed(rows):
            if row.user_id in latest_rows:
                continue
            latest_rows[row.user_id] = row
        return latest_rows
