from noble_ridge_agents.jobs.schema import Artifact, JobEnvelope
from noble_ridge_agents.jobs.store import InMemoryJobStore


def test_job_store_records_lifecycle_artifacts_and_audit_events():
    store = InMemoryJobStore()
    job = JobEnvelope.create(
        requester="mark",
        source="discord",
        channel="agent-email",
        assigned_agent="iris",
        job_type="iris.inbox_summary",
        payload={"query": "newer_than:1d"},
    )

    store.create(job)
    store.record_tool_call(job.job_id, "gmail.search")
    store.add_artifact(job.job_id, Artifact(kind="inbox_summary", body="Two messages need attention."))
    store.set_status(job.job_id, "completed")

    saved = store.get(job.job_id)

    assert saved is not None
    assert saved.status == "completed"
    assert saved.tool_calls == ["gmail.search"]
    assert saved.artifacts[0].kind == "inbox_summary"
    assert saved.audit_events[-1].event_type == "status_changed"
