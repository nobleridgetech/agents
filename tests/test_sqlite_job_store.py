from noble_ridge_agents.jobs.schema import Artifact, JobEnvelope
from noble_ridge_agents.jobs.sqlite_store import SQLiteJobStore


def test_sqlite_job_store_persists_lifecycle_across_instances(tmp_path):
    db_path = tmp_path / "jobs.db"
    job = JobEnvelope.create(
        requester="mark",
        source="discord",
        channel="agent-email",
        assigned_agent="iris",
        job_type="iris.draft_reply",
        payload={"thread_id": "thread-123", "intent": "follow up"},
    )

    store = SQLiteJobStore(db_path)
    store.create(job)
    store.record_tool_call(job.job_id, "gmail.thread_read")
    store.add_artifact(
        job.job_id,
        Artifact(
            kind="reply_draft",
            body="Draft only — do not send.",
            approval_channel="email-approvals",
            metadata={"thread_id": "thread-123"},
        ),
    )
    store.set_status(job.job_id, "approval_required")
    store.close()

    reopened = SQLiteJobStore(db_path)
    saved = reopened.get(job.job_id)

    assert saved is not None
    assert saved.status == "approval_required"
    assert saved.payload == {"thread_id": "thread-123", "intent": "follow up"}
    assert saved.tool_calls == ["gmail.thread_read"]
    assert saved.artifacts[0].kind == "reply_draft"
    assert saved.artifacts[0].approval_channel == "email-approvals"
    assert saved.artifacts[0].metadata == {"thread_id": "thread-123"}
    assert [event.event_type for event in saved.audit_events] == [
        "job_created",
        "tool_called",
        "artifact_added",
        "status_changed",
    ]
