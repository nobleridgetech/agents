from __future__ import annotations

from noble_ridge_agents.tools.gmail import EmailMessage, EmailThread, FakeGmailClient


def demo_gmail_client() -> FakeGmailClient:
    return FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-123",
                subject="Proposal next steps",
                messages=[
                    EmailMessage(
                        sender="prospect@example.com",
                        body="Please send the next steps for the proposal.",
                    )
                ],
            ),
            EmailThread(
                thread_id="thread-456",
                subject="Tuesday scheduling",
                messages=[
                    EmailMessage(
                        sender="client@example.com",
                        body="Can we schedule a call Tuesday afternoon?",
                    )
                ],
            ),
        ]
    )
