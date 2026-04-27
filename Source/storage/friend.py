import dataclasses
from datetime import UTC, datetime
import enum
from typing import TYPE_CHECKING, override

from . import _logic

if TYPE_CHECKING:
    from .friend_relationship import database as friend_relationship_database
    from .friend_request import database as friend_request_database


@dataclasses.dataclass
class friend_item:
    id: int
    requester_id: int
    requestee_id: int
    status: int
    created_at: str


class database(_logic.sqlite_connector_base):
    TABLE_NAME = "friend"
    friend_relationship_db: "friend_relationship_database | None" = None
    friend_request_db: "friend_request_database | None" = None
    _legacy_rows_synced = False

    class field(enum.Enum):
        ID = '"id"'
        REQUESTER_ID = '"requester_id"'
        REQUESTEE_ID = '"requestee_id"'
        STATUS = '"status"'
        CREATED_AT = '"created_at"'

    @override
    def first_time_setup(self) -> None:
        # Legacy compatibility table used by older project code and existing SQLite data.
        self.sqlite.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self.TABLE_NAME}" (
                {self.field.ID.value} INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                {self.field.REQUESTER_ID.value} INTEGER NOT NULL,
                {self.field.REQUESTEE_ID.value} INTEGER NOT NULL,
                {self.field.STATUS.value} INTEGER NOT NULL DEFAULT 0,
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
        self.sqlite.execute(
            f"""
            CREATE INDEX IF NOT EXISTS "idx_{self.TABLE_NAME}_status"
            ON "{self.TABLE_NAME}" ({self.field.STATUS.value});
            """,
        )

    @staticmethod
    def _normalise_timestamp(value: datetime | str | None) -> str:
        if value is None:
            return datetime.now(UTC).isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def link_databases(
        self,
        friend_relationship_db: "friend_relationship_database",
        friend_request_db: "friend_request_database",
    ) -> None:
        self.friend_relationship_db = friend_relationship_db
        self.friend_request_db = friend_request_db
        self.sync_legacy_rows()

    def _require_databases(
        self,
    ) -> tuple["friend_relationship_database", "friend_request_database"]:
        assert self.friend_relationship_db is not None
        assert self.friend_request_db is not None
        return (self.friend_relationship_db, self.friend_request_db)

    def sync_legacy_rows(self) -> None:
        if self._legacy_rows_synced:
            return
        friend_relationship_db, friend_request_db = self._require_databases()

        results = self.sqlite.execute_and_fetch(
            query=f"""
            SELECT
            {self.field.REQUESTER_ID.value},
            {self.field.REQUESTEE_ID.value},
            {self.field.STATUS.value},
            {self.field.CREATED_AT.value}
            FROM "{self.TABLE_NAME}"
            """,
        )
        assert results is not None

        for row in results:
            requester_id = int(row[0])
            requestee_id = int(row[1])
            status = int(row[2])
            created_at = str(row[3])
            if status == 1:
                friend_relationship_db.update(
                    requester_id,
                    requestee_id,
                    created_at=created_at,
                )
            else:
                friend_request_db.update(
                    requester_id,
                    requestee_id,
                    created_at=created_at,
                )

        self._legacy_rows_synced = True

    def _upsert_legacy_row(
        self,
        requester_id: int,
        requestee_id: int,
        status: int,
        created_at: datetime | str | None = None,
    ) -> None:
        self.sqlite.execute(
            f"""
            INSERT INTO "{self.TABLE_NAME}"
            (
                {self.field.REQUESTER_ID.value},
                {self.field.REQUESTEE_ID.value},
                {self.field.STATUS.value},
                {self.field.CREATED_AT.value}
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                requester_id,
                requestee_id,
                status,
                self._normalise_timestamp(created_at),
            ),
        )

    def _delete_legacy_request(
        self,
        requester_id: int,
        requestee_id: int,
    ) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.REQUESTER_ID.value} = ?
            AND {self.field.REQUESTEE_ID.value} = ?
            AND {self.field.STATUS.value} = 0
            """,
            (requester_id, requestee_id),
        )

    def _delete_legacy_pair(
        self,
        user_a_id: int,
        user_b_id: int,
    ) -> None:
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE (
                {self.field.REQUESTER_ID.value} = ?
                AND {self.field.REQUESTEE_ID.value} = ?
            ) OR (
                {self.field.REQUESTER_ID.value} = ?
                AND {self.field.REQUESTEE_ID.value} = ?
            )
            """,
            (user_a_id, user_b_id, user_b_id, user_a_id),
        )

    def create_request(
        self,
        requester_id: int,
        requestee_id: int,
        *,
        created_at: datetime | str | None = None,
    ) -> friend_item:
        _, friend_request_db = self._require_databases()
        request = friend_request_db.update(
            requester_id,
            requestee_id,
            created_at=created_at,
        )
        self._upsert_legacy_row(
            requester_id,
            requestee_id,
            0,
            created_at=request.created_at,
        )
        return friend_item(
            id=request.id,
            requester_id=request.requester_id,
            requestee_id=request.requestee_id,
            status=0,
            created_at=request.created_at,
        )

    def decline_request(
        self,
        requester_id: int,
        requestee_id: int,
    ) -> None:
        _, friend_request_db = self._require_databases()
        friend_request_db.delete(requester_id, requestee_id)
        self._delete_legacy_request(requester_id, requestee_id)

    def decline_all_requests(
        self,
        requestee_id: int,
    ) -> None:
        _, friend_request_db = self._require_databases()
        friend_request_db.delete_all_for_requestee(requestee_id)
        self.sqlite.execute(
            f"""
            DELETE FROM "{self.TABLE_NAME}"
            WHERE {self.field.REQUESTEE_ID.value} = ?
            AND {self.field.STATUS.value} = 0
            """,
            (requestee_id,),
        )

    def accept_request(
        self,
        requester_id: int,
        requestee_id: int,
        *,
        created_at: datetime | str | None = None,
    ) -> friend_item:
        friend_relationship_db, friend_request_db = self._require_databases()
        friend_request_db.delete(requester_id, requestee_id)
        friend_request_db.delete(requestee_id, requester_id)
        relationship = friend_relationship_db.update(
            requester_id,
            requestee_id,
            created_at=created_at,
        )
        self._delete_legacy_pair(requester_id, requestee_id)
        self._upsert_legacy_row(
            requester_id,
            requestee_id,
            1,
            created_at=relationship.created_at,
        )
        return friend_item(
            id=relationship.id,
            requester_id=relationship.user_id,
            requestee_id=relationship.friend_id,
            status=1,
            created_at=relationship.created_at,
        )

    def remove_friendship(
        self,
        user_a_id: int,
        user_b_id: int,
    ) -> None:
        friend_relationship_db, friend_request_db = self._require_databases()
        friend_relationship_db.delete(user_a_id, user_b_id)
        friend_request_db.delete(user_a_id, user_b_id)
        friend_request_db.delete(user_b_id, user_a_id)
        self._delete_legacy_pair(user_a_id, user_b_id)

    def has_pending_request(
        self,
        requester_id: int,
        requestee_id: int,
    ) -> bool:
        _, friend_request_db = self._require_databases()
        return friend_request_db.check(requester_id, requestee_id) is not None

    def has_friendship(
        self,
        user_a_id: int,
        user_b_id: int,
    ) -> bool:
        friend_relationship_db, _ = self._require_databases()
        return friend_relationship_db.check(user_a_id, user_b_id) is not None

    def update(
        self,
        requester_id: int,
        requestee_id: int,
        *,
        status: int = 0,
        created_at: datetime | str | None = None,
    ) -> None:
        if status == 1:
            self.accept_request(
                requester_id,
                requestee_id,
                created_at=created_at,
            )
            return
        self.create_request(
            requester_id,
            requestee_id,
            created_at=created_at,
        )

    def delete(
        self,
        requester_id: int,
        requestee_id: int,
    ) -> None:
        if self.has_friendship(requester_id, requestee_id):
            self.remove_friendship(requester_id, requestee_id)
            return
        self.decline_request(requester_id, requestee_id)

    def list_friend_ids(
        self,
        user_id: int,
        *,
        accepted_only: bool = True,
        limit: int | None = None,
    ) -> list[int]:
        friend_relationship_db, friend_request_db = self._require_databases()
        if accepted_only:
            return friend_relationship_db.list_friend_ids(user_id, limit=limit)

        friend_ids = friend_relationship_db.list_friend_ids(user_id, limit=limit)
        pending_ids = friend_request_db.list_requester_ids_for_requestee(
            user_id,
            limit=limit,
        )
        combined_ids: list[int] = []
        seen_ids: set[int] = set()
        for friend_id in [*friend_ids, *pending_ids]:
            if friend_id in seen_ids:
                continue
            seen_ids.add(friend_id)
            combined_ids.append(friend_id)
            if limit is not None and len(combined_ids) >= limit:
                break
        return combined_ids

    def check_pair(
        self,
        user_a_id: int,
        user_b_id: int,
    ) -> friend_item | None:
        friend_relationship_db, friend_request_db = self._require_databases()
        relationship = friend_relationship_db.check(user_a_id, user_b_id)
        if relationship is not None:
            return friend_item(
                id=relationship.id,
                requester_id=relationship.user_id,
                requestee_id=relationship.friend_id,
                status=1,
                created_at=relationship.created_at,
            )

        direct_request = friend_request_db.check(user_a_id, user_b_id)
        if direct_request is not None:
            return friend_item(
                id=direct_request.id,
                requester_id=direct_request.requester_id,
                requestee_id=direct_request.requestee_id,
                status=0,
                created_at=direct_request.created_at,
            )

        reverse_request = friend_request_db.check(user_b_id, user_a_id)
        if reverse_request is not None:
            return friend_item(
                id=reverse_request.id,
                requester_id=reverse_request.requester_id,
                requestee_id=reverse_request.requestee_id,
                status=0,
                created_at=reverse_request.created_at,
            )
        return None

    def count_friends(self, user_id: int) -> int:
        friend_relationship_db, _ = self._require_databases()
        return friend_relationship_db.count_for_user(user_id)

    def count_pending_requests(self, requestee_id: int) -> int:
        _, friend_request_db = self._require_databases()
        return friend_request_db.count_for_requestee(requestee_id)

    def list_incoming_request_user_ids(
        self,
        requestee_id: int,
        *,
        limit: int | None = None,
    ) -> list[int]:
        _, friend_request_db = self._require_databases()
        return friend_request_db.list_requester_ids_for_requestee(
            requestee_id,
            limit=limit,
        )
