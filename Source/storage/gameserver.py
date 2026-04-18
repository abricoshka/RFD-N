import dataclasses
from datetime import datetime
import enum
from typing import override

from . import _logic


@dataclasses.dataclass
class gameserver_item:
    server_uuid: str
    server_name: str
    place_id: int
    server_ip: str
    server_port: int
    access_key: str
    player_count: int
    max_players: int
    last_heartbeat: str | None
    is_online: bool


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "gameserver"

    class field(enum.Enum):
        SERVER_UUID = '"server_uuid"'
        SERVER_NAME = '"server_name"'
        PLACE_ID = '"place_id"'
        SERVER_IP = '"server_ip"'
        SERVER_PORT = '"server_port"'
        ACCESS_KEY = '"access_key"'
        PLAYER_COUNT = '"player_count"'
        MAX_PLAYERS = '"max_players"'
        LAST_HEARTBEAT = '"last_heartbeat"'
        IS_ONLINE = '"is_online"'

    @override
    def first_time_setup(self) -> None:
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.SERVER_UUID.value} TEXT PRIMARY KEY NOT NULL,
                {self.field.SERVER_NAME.value} TEXT NOT NULL,
                {self.field.PLACE_ID.value} INTEGER NOT NULL,
                {self.field.SERVER_IP.value} TEXT NOT NULL DEFAULT '',
                {self.field.SERVER_PORT.value} INTEGER NOT NULL DEFAULT 0,
                {self.field.ACCESS_KEY.value} TEXT NOT NULL DEFAULT '',
                {self.field.PLAYER_COUNT.value} INTEGER NOT NULL DEFAULT 0,
                {self.field.MAX_PLAYERS.value} INTEGER NOT NULL DEFAULT 0,
                {self.field.LAST_HEARTBEAT.value} DATETIME,
                {self.field.IS_ONLINE.value} BOOLEAN NOT NULL DEFAULT TRUE
            );
            """,
        )
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_place_id"
            ON "{self.TABLE_NAME}" ({self.field.PLACE_ID.value});
            """,
        )

    @staticmethod
    def _normalise_timestamp(value: datetime | str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def update(
        self,
        server_uuid: str,
        server_name: str,
        place_id: int,
        *,
        server_ip: str = "",
        server_port: int = 0,
        access_key: str = "",
        player_count: int = 0,
        max_players: int = 0,
        last_heartbeat: datetime | str | None = None,
        is_online: bool = True,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.SERVER_UUID.value},
                {self.field.SERVER_NAME.value},
                {self.field.PLACE_ID.value},
                {self.field.SERVER_IP.value},
                {self.field.SERVER_PORT.value},
                {self.field.ACCESS_KEY.value},
                {self.field.PLAYER_COUNT.value},
                {self.field.MAX_PLAYERS.value},
                {self.field.LAST_HEARTBEAT.value},
                {self.field.IS_ONLINE.value}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT({self.field.SERVER_UUID.value})
            DO UPDATE SET
                {self.field.SERVER_NAME.value} = excluded.{self.field.SERVER_NAME.value},
                {self.field.PLACE_ID.value} = excluded.{self.field.PLACE_ID.value},
                {self.field.SERVER_IP.value} = excluded.{self.field.SERVER_IP.value},
                {self.field.SERVER_PORT.value} = excluded.{self.field.SERVER_PORT.value},
                {self.field.ACCESS_KEY.value} = excluded.{self.field.ACCESS_KEY.value},
                {self.field.PLAYER_COUNT.value} = excluded.{self.field.PLAYER_COUNT.value},
                {self.field.MAX_PLAYERS.value} = excluded.{self.field.MAX_PLAYERS.value},
                {self.field.LAST_HEARTBEAT.value} = excluded.{self.field.LAST_HEARTBEAT.value},
                {self.field.IS_ONLINE.value} = excluded.{self.field.IS_ONLINE.value}
            """,
            (
                server_uuid,
                server_name,
                place_id,
                server_ip,
                server_port,
                access_key,
                player_count,
                max_players,
                self._normalise_timestamp(last_heartbeat),
                is_online,
            ),
        )

    def get_player_counts_for_places(
        self,
        place_ids: list[int],
    ) -> dict[int, int]:
        if not place_ids:
            return {}

        placeholders = ",".join("?" for _ in place_ids)
        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.PLACE_ID.value},
            SUM({self.field.PLAYER_COUNT.value})
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.PLACE_ID.value} IN ({placeholders})
            AND {self.field.IS_ONLINE.value} = TRUE
            GROUP BY {self.field.PLACE_ID.value}
            """,
            values=tuple(place_ids),
        )
        assert results is not None
        return {
            int(row[0]): int(row[1] or 0)
            for row in results
        }

    def list_online_servers_for_places(
        self,
        place_ids: list[int],
    ) -> list[gameserver_item]:
        if not place_ids:
            return []

        placeholders = ",".join("?" for _ in place_ids)
        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.SERVER_UUID.value},
            {self.field.SERVER_NAME.value},
            {self.field.PLACE_ID.value},
            {self.field.SERVER_IP.value},
            {self.field.SERVER_PORT.value},
            {self.field.ACCESS_KEY.value},
            {self.field.PLAYER_COUNT.value},
            {self.field.MAX_PLAYERS.value},
            {self.field.LAST_HEARTBEAT.value},
            {self.field.IS_ONLINE.value}
            FROM "{self.TABLE_NAME}"
            WHERE {self.field.PLACE_ID.value} IN ({placeholders})
            AND {self.field.IS_ONLINE.value} = TRUE
            ORDER BY {self.field.PLACE_ID.value} ASC, {self.field.SERVER_UUID.value} ASC
            """,
            values=tuple(place_ids),
        )
        assert results is not None
        return [
            gameserver_item(
                server_uuid=str(row[0]),
                server_name=str(row[1]),
                place_id=int(row[2]),
                server_ip=str(row[3]),
                server_port=int(row[4]),
                access_key=str(row[5]),
                player_count=int(row[6]),
                max_players=int(row[7]),
                last_heartbeat=(None if row[8] is None else str(row[8])),
                is_online=bool(row[9]),
            )
            for row in results
        ]

    def get_place_ids_for_servers(
        self,
        server_uuids: list[str],
        *,
        online_only: bool = True,
    ) -> dict[str, int]:
        if not server_uuids:
            return {}

        placeholders = ",".join("?" for _ in server_uuids)
        filters = [f"{self.field.SERVER_UUID.value} IN ({placeholders})"]
        if online_only:
            filters.append(f"{self.field.IS_ONLINE.value} = TRUE")

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.SERVER_UUID.value},
            {self.field.PLACE_ID.value}
            FROM "{self.TABLE_NAME}"
            WHERE {" AND ".join(filters)}
            """,
            values=tuple(server_uuids),
        )
        assert results is not None
        return {
            str(row[0]): int(row[1])
            for row in results
        }
