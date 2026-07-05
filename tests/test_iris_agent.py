from noble_ridge_agents.agents.iris import IrisAgent
from noble_ridge_agents.jobs.schema import JobEnvelope
from noble_ridge_agents.tools.gmail import FakeGmailClient, EmailMessage, EmailThread


def make_job(job_type: str, payload: dict) -> JobEnvelope:
    return JobEnvelope.create(
        requester="mark",
        source="discord",
        channel="agent-email",
        assigned_agent="iris",
        job_type=job_type,
        payload=payload,
    )


def test_iris_summarizes_inbox_without_requiring_send_capability():
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="t-1",
                subject="Client follow up",
                messages=[
                    EmailMessage(sender="client@example.com", body="Can we schedule a call Tuesday?"),
                ],
            ),
            EmailThread(
                thread_id="t-2",
                subject="Invoice question",
                messages=[
                    EmailMessage(sender="vendor@example.com", body="Please confirm invoice receipt."),
                ],
            ),
        ]
    )
    iris = IrisAgent(gmail_client=gmail)

    result = iris.handle(make_job("iris.inbox_summary", {"query": "newer_than:7d"}))

    assert result.status == "completed"
    assert result.approval_required is False
    assert result.artifacts[0].kind == "inbox_summary"
    assert "Client follow up" in result.artifacts[0].body
    assert "Invoice question" in result.artifacts[0].body
    assert "gmail.search" in result.tool_calls
    assert "gmail.send" not in result.tool_calls


def test_iris_masks_sensitive_values_in_inbox_summary():
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="t-1",
                subject="Reset link for client@example.com",
                messages=[
                    EmailMessage(
                        sender="client@example.com",
                        body="Use https://example.com/reset?token=abc and ghp_1234567890abcdefghijklmnopqrstuvwxyz",
                    ),
                ],
            )
        ]
    )
    iris = IrisAgent(gmail_client=gmail)

    result = iris.handle(make_job("iris.inbox_summary", {"query": "newer_than:7d"}))
    body = result.artifacts[0].body

    assert "client@example.com" not in body
    assert "https://example.com" not in body
    assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in body
    assert "[redacted-email]" in body
    assert "[redacted-url]" in body
    assert "[redacted-token]" in body


def test_iris_draft_reply_creates_approval_artifact_and_does_not_send():
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-123",
                subject="Proposal next steps",
                messages=[
                    EmailMessage(sender="prospect@example.com", body="Please send next steps for the proposal."),
                ],
            )
        ]
    )
    iris = IrisAgent(gmail_client=gmail)

    result = iris.handle(make_job("iris.draft_reply", {"thread_id": "thread-123", "intent": "confirm we will follow up"}))

    assert result.status == "approval_required"
    assert result.approval_required is True
    assert result.artifacts[0].kind == "reply_draft"
    assert result.artifacts[0].approval_channel == "email-approvals"
    assert "Subject: Re: Proposal next steps" in result.artifacts[0].body
    assert "Draft only" in result.artifacts[0].body
    assert gmail.sent_messages == []
    assert "gmail.thread_read" in result.tool_calls
    assert "gmail.send" not in result.tool_calls


def test_iris_creates_thread_summary_with_masked_participants_and_context():
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-123",
                subject="Proposal token ghp_1234567890abcdefghijklmnopqrstuvwxyz",
                messages=[
                    EmailMessage(sender="prospect@example.com", body="Can we schedule Tuesday?"),
                    EmailMessage(sender="mark@nobleridge.test", body="Here is https://example.com/private"),
                ],
            )
        ]
    )
    iris = IrisAgent(gmail_client=gmail)

    result = iris.handle(make_job("iris.thread_summary", {"thread_id": "thread-123"}))
    body = result.artifacts[0].body

    assert result.status == "completed"
    assert result.artifacts[0].kind == "thread_summary"
    assert "2 messages" in body
    assert "[redacted-email]" in body
    assert "[redacted-url]" in body
    assert "[redacted-token]" in body
    assert "prospect@example.com" not in body
    assert "https://example.com" not in body


def test_iris_extracts_action_items_from_thread():
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-123",
                subject="Proposal next steps",
                messages=[
                    EmailMessage(sender="prospect@example.com", body="Please send the revised proposal by Friday."),
                    EmailMessage(sender="mark@nobleridge.test", body="FYI, background only."),
                    EmailMessage(sender="prospect@example.com", body="Can we schedule a call Tuesday?"),
                ],
            )
        ]
    )
    iris = IrisAgent(gmail_client=gmail)

    result = iris.handle(make_job("iris.action_items", {"thread_id": "thread-123"}))
    body = result.artifacts[0].body

    assert result.status == "completed"
    assert result.artifacts[0].kind == "action_items"
    assert "Please send the revised proposal by Friday." in body
    assert "Can we schedule a call Tuesday?" in body
    assert "FYI, background only" not in body
    assert "gmail.thread_read" in result.tool_calls


def test_iris_monitor_inbox_flags_actionable_threads_for_review():
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-123",
                subject="Proposal next steps",
                messages=[
                    EmailMessage(sender="prospect@example.com", body="Please send the revised proposal by Friday."),
                ],
            ),
            EmailThread(
                thread_id="thread-456",
                subject="Newsletter",
                messages=[
                    EmailMessage(sender="news@example.com", body="FYI only."),
                ],
            ),
        ]
    )
    iris = IrisAgent(gmail_client=gmail)

    result = iris.handle(make_job("iris.monitor_inbox", {"query": "in:inbox newer_than:1d"}))
    body = result.artifacts[0].body

    assert result.status == "approval_required"
    assert result.approval_required is True
    assert result.artifacts[0].kind == "inbox_triage"
    assert result.artifacts[0].approval_channel == "email-approvals"
    assert result.artifacts[0].metadata == {"actionable_threads": "1", "threads_reviewed": "2"}
    assert "Iris active inbox monitor" in body
    assert "thread-123" in body
    assert "Proposal next steps" in body
    assert "Newsletter" not in body
    assert "gmail.search" in result.tool_calls
    assert "gmail.send" not in result.tool_calls


def test_iris_monitor_inbox_completes_when_no_actionable_threads_are_found():
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-456",
                subject="Newsletter",
                messages=[
                    EmailMessage(sender="news@example.com", body="FYI only."),
                ],
            ),
        ]
    )
    iris = IrisAgent(gmail_client=gmail)

    result = iris.handle(make_job("iris.monitor_inbox", {"query": "in:inbox newer_than:1d"}))

    assert result.status == "completed"
    assert result.approval_required is False
    assert result.artifacts[0].kind == "inbox_triage"
    assert "No actionable inbox threads found" in result.artifacts[0].body


def test_iris_rejects_out_of_scope_job_types():
    iris = IrisAgent(gmail_client=FakeGmailClient(threads=[]))

    result = iris.handle(make_job("thalia.content_calendar", {"customer": "demo"}))

    assert result.status == "rejected"
    assert result.approval_required is False
    assert "outside Iris's email administration swimlane" in result.message
