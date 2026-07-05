from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class EmailMessage:
    sender: str
    body: str


@dataclass(frozen=True, slots=True)
class EmailThread:
    thread_id: str
    subject: str
    messages: list[EmailMessage]


class FakeGmailClient:
    """Test/local Gmail adapter with no external side effects."""

    def __init__(self, threads: list[EmailThread]) -> None:
        self._threads = {thread.thread_id: thread for thread in threads}
        self.sent_messages: list[dict[str, str]] = []

    def search(self, query: str) -> list[EmailThread]:
        # Query is intentionally accepted but not interpreted in the fake adapter.
        return list(self._threads.values())

    def read_thread(self, thread_id: str) -> EmailThread:
        try:
            return self._threads[thread_id]
        except KeyError as exc:
            raise KeyError(f"Unknown Gmail thread: {thread_id}") from exc

    def send(self, *, to: str, subject: str, body: str) -> None:
        raise RuntimeError("Gmail sending is disabled for Iris V1")


class RealGmailClient:
    """Read-only Gmail API adapter for Iris.

    This adapter intentionally exposes the same narrow interface as
    FakeGmailClient and refuses send operations even if credentials are changed
    later. Iris V1 is read/search/draft-only.
    """

    def __init__(self, service: Any, max_results: int = 10) -> None:
        self.service = service
        self.max_results = max_results

    @classmethod
    def from_token_file(cls, token_path: str | Path, max_results: int = 10) -> "RealGmailClient":
        token_path = Path(token_path)
        if not token_path.exists():
            raise FileNotFoundError(f"Gmail token file not found: {token_path}")

        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(
            str(token_path),
            scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        )
        return cls(service=build("gmail", "v1", credentials=creds), max_results=max_results)

    def search(self, query: str) -> list[EmailThread]:
        response = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=self.max_results)
            .execute()
        )
        threads: list[EmailThread] = []
        seen_thread_ids: set[str] = set()
        for message_ref in response.get("messages", []):
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_ref["id"], format="metadata")
                .execute()
            )
            thread_id = message.get("threadId") or message_ref.get("threadId") or message_ref["id"]
            if thread_id in seen_thread_ids:
                continue
            seen_thread_ids.add(thread_id)
            subject = self._header(message, "Subject") or "(no subject)"
            threads.append(
                EmailThread(
                    thread_id=thread_id,
                    subject=subject,
                    messages=[
                        EmailMessage(
                            sender=self._header(message, "From") or "unknown sender",
                            body=message.get("snippet", ""),
                        )
                    ],
                )
            )
        return threads

    def read_thread(self, thread_id: str) -> EmailThread:
        response = (
            self.service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )
        messages = response.get("messages", [])
        subject = "(no subject)"
        email_messages: list[EmailMessage] = []
        for message in messages:
            message_subject = self._header(message, "Subject")
            if subject == "(no subject)" and message_subject:
                subject = self._normalize_subject(message_subject)
            email_messages.append(
                EmailMessage(
                    sender=self._header(message, "From") or "unknown sender",
                    body=message.get("snippet", ""),
                )
            )
        return EmailThread(thread_id=response.get("id", thread_id), subject=subject, messages=email_messages)

    def send(self, *, to: str, subject: str, body: str) -> None:
        raise RuntimeError("Gmail sending is disabled for Iris V1")

    def _header(self, message: dict[str, Any], name: str) -> str | None:
        headers = message.get("payload", {}).get("headers", [])
        for header in headers:
            if header.get("name", "").lower() == name.lower():
                return header.get("value")
        return None

    def _normalize_subject(self, subject: str) -> str:
        normalized = subject.strip()
        while normalized.lower().startswith("re:"):
            normalized = normalized[3:].strip()
        return normalized or "(no subject)"
