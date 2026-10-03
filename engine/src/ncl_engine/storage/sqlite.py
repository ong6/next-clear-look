"""Small explicit SQLite repository with WAL and atomic job/event writes."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _json(value: Mapping[str, Any] | BaseModel) -> str:
    raw = value.model_dump(mode="json", by_alias=True) if isinstance(value, BaseModel) else value
    return json.dumps(raw, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._connection = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        migration = files("ncl_engine.storage.migrations").joinpath("001_initial.sql")
        with self._lock:
            self._connection.executescript(migration.read_text(encoding="utf-8"))

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def health(self) -> bool:
        with self._lock:
            row = self._connection.execute("PRAGMA quick_check").fetchone()
        return row is not None and row[0] == "ok"

    def set_metadata(self, key: str, value: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO metadata(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_metadata(self, key: str) -> str | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT value FROM metadata WHERE key=?", (key,)
            ).fetchone()
        return None if row is None else str(row[0])

    def put_resource(
        self,
        kind: str,
        identifier: str,
        payload: Mapping[str, Any] | BaseModel,
        *,
        parent_id: str | None = None,
        sort_key: str = "",
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO resources(kind,id,parent_id,sort_key,payload_json,updated_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET "
                "parent_id=excluded.parent_id,sort_key=excluded.sort_key,"
                "payload_json=excluded.payload_json,updated_at=excluded.updated_at",
                (kind, identifier, parent_id, sort_key, _json(payload), _now()),
            )

    def get_resource(self, kind: str, identifier: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM resources WHERE kind=? AND id=?", (kind, identifier)
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row[0]))
        if not isinstance(value, dict):
            raise RuntimeError("stored resource is not a JSON object")
        return value

    def list_resources(
        self, kind: str, *, parent_id: str | None = None, descending: bool = False
    ) -> list[dict[str, Any]]:
        direction = "DESC" if descending else "ASC"
        query = "SELECT payload_json FROM resources WHERE kind=?"
        parameters: tuple[object, ...] = (kind,)
        if parent_id is not None:
            query += " AND parent_id=?"
            parameters = (kind, parent_id)
        query += f" ORDER BY sort_key {direction}, id {direction}"
        with self._lock:
            rows = self._connection.execute(query, parameters).fetchall()
        output: list[dict[str, Any]] = []
        for row in rows:
            value = json.loads(str(row[0]))
            if isinstance(value, dict):
                output.append(value)
        return output

    def delete_resource(self, kind: str, identifier: str) -> bool:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM resources WHERE kind=? AND id=?", (kind, identifier)
            )
        return cursor.rowcount > 0

    def delete_resources(self, kind: str, *, parent_id: str) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM resources WHERE kind=? AND parent_id=?", (kind, parent_id)
            )
        return cursor.rowcount

    def delete_children(self, parent_id: str) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM resources WHERE parent_id=?", (parent_id,))

    def put_job(self, fingerprint: str, payload: BaseModel) -> None:
        job_id = str(payload.model_dump()["id"])
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO jobs(id,fingerprint,payload_json,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json,"
                "updated_at=excluded.updated_at",
                (job_id, fingerprint, _json(payload), _now()),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row[0]))
        return value if isinstance(value, dict) else None

    def find_job(self, fingerprint: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM jobs WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
        if row is None:
            return None
        value = json.loads(str(row[0]))
        return value if isinstance(value, dict) else None

    def retire_job_fingerprint(self, job_id: str) -> None:
        """Keep terminal history while freeing the request identity for a retry."""

        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE jobs SET fingerprint=fingerprint || ':terminal:' || id WHERE id=?",
                (job_id,),
            )

    def count_job_attempts(self, fingerprint: str) -> int:
        """Count every job ever created for one request identity, retired retries included."""

        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE fingerprint=? OR fingerprint LIKE ?",
                (fingerprint, f"{fingerprint}:terminal:%"),
            ).fetchone()
        return int(row[0])

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM jobs ORDER BY updated_at DESC, id DESC"
            ).fetchall()
        return [value for row in rows if isinstance((value := json.loads(str(row[0]))), dict)]

    def append_event(self, job_id: str, event: Mapping[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO job_events("
                "job_id,sequence,event_id,event_type,emitted_at,payload_json) "
                "VALUES(?,?,?,?,?,?)",
                (
                    job_id,
                    int(event["sequence"]),
                    str(event["id"]),
                    str(event["type"]),
                    str(event["emitted_at"]),
                    _json(event),
                ),
            )

    def list_events(self, job_id: str, after_sequence: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload_json FROM job_events "
                "WHERE job_id=? AND sequence>? ORDER BY sequence",
                (job_id, after_sequence),
            ).fetchall()
        return [value for row in rows if isinstance((value := json.loads(str(row[0]))), dict)]

    def event_count(self, job_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT count(*) FROM job_events WHERE job_id=?", (job_id,)
            ).fetchone()
        return 0 if row is None else int(row[0])

    def claim_idempotency(
        self, key: str, request_sha256: str, resource_kind: str, resource_id: str
    ) -> tuple[bool, str | None]:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT request_sha256,resource_id FROM idempotency_keys WHERE key=?", (key,)
            ).fetchone()
            if row is not None:
                return str(row[0]) == request_sha256, str(row[1])
            self._connection.execute(
                "INSERT INTO idempotency_keys("
                "key,request_sha256,resource_kind,resource_id,created_at) "
                "VALUES(?,?,?,?,?)",
                (key, request_sha256, resource_kind, resource_id, _now()),
            )
        return True, None
