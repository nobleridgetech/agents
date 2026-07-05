from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class Artifact:
    kind: str
    body: str
    approval_channel: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AuditEvent:
    event_type: str
    timestamp: str = field(default_factory=utc_now_iso)
    detail: str | None = None


@dataclass(slots=True)
class JobEnvelope:
    job_id: str
    requester: str
    source: str
    channel: str
    assigned_agent: str
    job_type: str
    payload: dict
    status: str = "created"
    created_at: str = field(default_factory=utc_now_iso)
    artifacts: list[Artifact] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        requester: str,
        source: str,
        channel: str,
        assigned_agent: str,
        job_type: str,
        payload: dict,
    ) -> "JobEnvelope":
        job = cls(
            job_id=str(uuid4()),
            requester=requester,
            source=source,
            channel=channel,
            assigned_agent=assigned_agent,
            job_type=job_type,
            payload=payload,
        )
        job.audit_events.append(AuditEvent(event_type="job_created"))
        return job


@dataclass(slots=True)
class AgentResult:
    status: str
    message: str
    artifacts: list[Artifact] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    approval_required: bool = False
