from pathlib import Path

import pytest

from noble_ridge_agents.tools.gmail import EmailMessage, EmailThread, RealGmailClient


class FakeExecute:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class FakeMessagesResource:
    def __init__(self):
        self.list_calls = []
        self.get_calls = []

    def list(self, *, userId, q, maxResults):
        self.list_calls.append({"userId": userId, "q": q, "maxResults": maxResults})
        return FakeExecute({"messages": [{"id": "msg-1", "threadId": "thread-1"}]})

    def get(self, *, userId, id, format):
        self.get_calls.append({"userId": userId, "id": id, "format": format})
        return FakeExecute(
            {
                "id": "msg-1",
                "threadId": "thread-1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Client <client@example.com>"},
                        {"name": "Subject", "value": "Client follow up"},
                    ]
                },
                "snippet": "Can we meet Tuesday?",
            }
        )


class FakeThreadsResource:
    def __init__(self):
        self.get_calls = []

    def get(self, *, userId, id, format):
        self.get_calls.append({"userId": userId, "id": id, "format": format})
        return FakeExecute(
            {
                "id": "thread-1",
                "messages": [
                    {
                        "id": "msg-1",
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "Client <client@example.com>"},
                                {"name": "Subject", "value": "Client follow up"},
                            ]
                        },
                        "snippet": "Can we meet Tuesday?",
                    },
                    {
                        "id": "msg-2",
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "mark@example.com"},
                                {"name": "Subject", "value": "Re: Client follow up"},
                            ]
                        },
                        "snippet": "Tuesday works.",
                    },
                ],
            }
        )


class FakeUsersResource:
    def __init__(self):
        self.messages_resource = FakeMessagesResource()
        self.threads_resource = FakeThreadsResource()

    def messages(self):
        return self.messages_resource

    def threads(self):
        return self.threads_resource


class FakeGmailService:
    def __init__(self):
        self.users_resource = FakeUsersResource()

    def users(self):
        return self.users_resource


def test_real_gmail_client_search_maps_gmail_messages_to_email_threads():
    service = FakeGmailService()
    gmail = RealGmailClient(service=service, max_results=5)

    threads = gmail.search("newer_than:7d")

    assert threads == [
        EmailThread(
            thread_id="thread-1",
            subject="Client follow up",
            messages=[EmailMessage(sender="Client <client@example.com>", body="Can we meet Tuesday?")],
        )
    ]
    assert service.users_resource.messages_resource.list_calls == [
        {"userId": "me", "q": "newer_than:7d", "maxResults": 5}
    ]
    assert service.users_resource.messages_resource.get_calls[0]["format"] == "metadata"


def test_real_gmail_client_read_thread_maps_messages_without_full_body_secret_exposure():
    service = FakeGmailService()
    gmail = RealGmailClient(service=service)

    thread = gmail.read_thread("thread-1")

    assert thread.thread_id == "thread-1"
    assert thread.subject == "Client follow up"
    assert [message.sender for message in thread.messages] == ["Client <client@example.com>", "mark@example.com"]
    assert [message.body for message in thread.messages] == ["Can we meet Tuesday?", "Tuesday works."]
    assert service.users_resource.threads_resource.get_calls == [
        {"userId": "me", "id": "thread-1", "format": "full"}
    ]


def test_real_gmail_client_refuses_send_even_when_real_adapter_is_used():
    gmail = RealGmailClient(service=FakeGmailService())

    with pytest.raises(RuntimeError, match="disabled"):
        gmail.send(to="x@example.com", subject="Nope", body="No send")


def test_real_gmail_client_requires_existing_token_for_default_construction(tmp_path):
    missing_token = tmp_path / "missing-token.json"

    with pytest.raises(FileNotFoundError):
        RealGmailClient.from_token_file(missing_token)
