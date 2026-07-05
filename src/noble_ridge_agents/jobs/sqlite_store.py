from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from noble_ridge_agents.jobs.schema import Artifact, AuditEvent, JobEnvelope


class SQLiteJobStore:
    """SQLite-backed job and audit store for local durable runs."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        self._conn.close()

    def create(self, job: JobEnvelope) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    job_id, requester, source, channel, assigned_agent, job_type,
                    payload_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.requester,
                    job.source,
                    job.channel,
                    job.assigned_agent,
                    job.job_type,
                    json.dumps(job.payload, sort_keys=True),
                    job.status,
                    job.created_at,
                ),
            )
            for event in job.audit_events:
                self._insert_audit_event(job.job_id, event)

    def get(self, job_id: str) -> JobEnvelope | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = JobEnvelope(
            job_id=row["job_id"],
            requester=row["requester"],
            source=row["source"],
            channel=row["channel"],
            assigned_agent=row["assigned_agent"],
            job_type=row["job_type"],
            payload=json.loads(row["payload_json"]),
            status=row["status"],
            created_at=row["created_at"],
            artifacts=self._load_artifacts(job_id),
            tool_calls=self._load_tool_calls(job_id),
            audit_events=self._load_audit_events(job_id),
        )
        return job

    def record_tool_call(self, job_id: str, tool_name: str) -> None:
        self._require_job(job_id)
        with self._conn:
            self._conn.execute(
                "INSERT INTO tool_calls (job_id, tool_name) VALUES (?, ?)",
                (job_id, tool_name),
            )
            self._insert_audit_event(job_id, AuditEvent(event_type="tool_called", detail=tool_name))

    def add_artifact(self, job_id: str, artifact: Artifact) -> None:
        self._require_job(job_id)
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO artifacts (job_id, kind, body, approval_channel, metadata_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    artifact.kind,
                    artifact.body,
                    artifact.approval_channel,
                    json.dumps(artifact.metadata, sort_keys=True),
                ),
            )
            self._insert_audit_event(job_id, AuditEvent(event_type="artifact_added", detail=artifact.kind))

    def set_status(self, job_id: str, status: str) -> None:
        self._require_job(job_id)
        with self._conn:
            self._conn.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (status, job_id))
            self._insert_audit_event(job_id, AuditEvent(event_type="status_changed", detail=status))

    def _create_schema(self) -> None:
        with self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    requester TEXT NOT NULL,
                    source TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    assigned_agent TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    tool_name TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    kind TEXT NOT NULL,
                    body TEXT NOT NULL,
                    approval_channel TEXT,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    event_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    detail TEXT
                );
                """
            )

    def _require_job(self, job_id: str) -> None:
        if self._conn.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,)).fetchone() is None:
            raise KeyError(f"Unknown job: {job_id}")

    def _insert_audit_event(self, job_id: str, event: AuditEvent) -> None:
        self._conn.execute(
            "INSERT INTO audit_events (job_id, event_type, timestamp, detail) VALUES (?, ?, ?, ?)",
            (job_id, event.event_type, event.timestamp, event.detail),
        )

    def _load_tool_calls(self, job_id: str) -> list[str]:
        rows = self._conn.execute("SELECT tool_name FROM tool_calls WHERE job_id = ? ORDER BY id", (job_id,))
        return [row["tool_name"] for row in rows]

    def _load_artifacts(self, job_id: str) -> list[Artifact]:
        rows = self._conn.execute(
            "SELECT kind, body, approval_channel, metadata_json FROM artifacts WHERE job_id = ? ORDER BY id",
            (job_id,),
        )
        return [
            Artifact(
                kind=row["kind"],
                body=row["body"],
                approval_channel=row["approval_channel"],
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def _load_audit_events(self, job_id: str) -> list[AuditEvent]:
        rows = self._conn.execute(
            "SELECT event_type, timestamp, detail FROM audit_events WHERE job_id = ? ORDER BY id",
            (job_id,),
        )
        return [
            AuditEvent(event_type=row["event_type"], timestamp=row["timestamp"], detail=row["detail"])
            for row in rows
        ]
