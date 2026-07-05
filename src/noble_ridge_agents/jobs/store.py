from __future__ import annotations

from copy import deepcopy

from noble_ridge_agents.jobs.schema import Artifact, AuditEvent, JobEnvelope


class InMemoryJobStore:
    """Simple auditable job store for tests and local proof-of-concept runs."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobEnvelope] = {}

    def create(self, job: JobEnvelope) -> None:
        if job.job_id in self._jobs:
            raise ValueError(f"Job already exists: {job.job_id}")
        self._jobs[job.job_id] = deepcopy(job)

    def get(self, job_id: str) -> JobEnvelope | None:
        job = self._jobs.get(job_id)
        return deepcopy(job) if job is not None else None

    def record_tool_call(self, job_id: str, tool_name: str) -> None:
        job = self._require_job(job_id)
        job.tool_calls.append(tool_name)
        job.audit_events.append(AuditEvent(event_type="tool_called", detail=tool_name))

    def add_artifact(self, job_id: str, artifact: Artifact) -> None:
        job = self._require_job(job_id)
        job.artifacts.append(artifact)
        job.audit_events.append(AuditEvent(event_type="artifact_added", detail=artifact.kind))

    def set_status(self, job_id: str, status: str) -> None:
        job = self._require_job(job_id)
        job.status = status
        job.audit_events.append(AuditEvent(event_type="status_changed", detail=status))

    def _require_job(self, job_id: str) -> JobEnvelope:
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(f"Unknown job: {job_id}") from exc
