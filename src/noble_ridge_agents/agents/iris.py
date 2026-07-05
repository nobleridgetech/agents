from __future__ import annotations

from noble_ridge_agents.content_safety import safe_display_text
from noble_ridge_agents.jobs.schema import AgentResult, Artifact, JobEnvelope
from noble_ridge_agents.policy.permissions import PermissionPolicy
from noble_ridge_agents.tools.gmail import FakeGmailClient, EmailMessage, EmailThread


class IrisAgent:
    """Iris, the Email Admin Agent.

    V1 is intentionally read-only plus draft-only. It never sends email.
    """

    allowed_job_types = {
        "iris.inbox_summary",
        "iris.monitor_inbox",
        "iris.draft_reply",
        "iris.find_email",
        "iris.thread_summary",
        "iris.action_items",
    }

    def __init__(self, gmail_client: FakeGmailClient, policy: PermissionPolicy | None = None) -> None:
        self.gmail_client = gmail_client
        self.policy = policy or PermissionPolicy.default()

    def handle(self, job: JobEnvelope) -> AgentResult:
        if job.assigned_agent != "iris" or job.job_type not in self.allowed_job_types:
            return AgentResult(
                status="rejected",
                message="Request is outside Iris's email administration swimlane.",
            )

        if job.job_type == "iris.inbox_summary":
            return self._inbox_summary(job)
        if job.job_type == "iris.monitor_inbox":
            return self._monitor_inbox(job)
        if job.job_type == "iris.find_email":
            return self._find_email(job)
        if job.job_type == "iris.draft_reply":
            return self._draft_reply(job)
        if job.job_type == "iris.thread_summary":
            return self._thread_summary(job)
        if job.job_type == "iris.action_items":
            return self._action_items(job)

        return AgentResult(status="rejected", message="Unsupported Iris job type.")

    def _inbox_summary(self, job: JobEnvelope) -> AgentResult:
        self._require("gmail.search")
        query = str(job.payload.get("query", ""))
        threads = self.gmail_client.search(query)
        body = self._summarize_threads(threads)
        return AgentResult(
            status="completed",
            message="Inbox summary created.",
            artifacts=[Artifact(kind="inbox_summary", body=body)],
            tool_calls=["gmail.search"],
        )

    def _find_email(self, job: JobEnvelope) -> AgentResult:
        self._require("gmail.search")
        query = str(job.payload.get("query", ""))
        threads = self.gmail_client.search(query)
        body = self._format_thread_list(threads)
        return AgentResult(
            status="completed",
            message="Email search completed.",
            artifacts=[Artifact(kind="email_search_results", body=body)],
            tool_calls=["gmail.search"],
        )

    def _monitor_inbox(self, job: JobEnvelope) -> AgentResult:
        self._require("gmail.search")
        query = str(job.payload.get("query", "in:inbox newer_than:1d"))
        threads = self.gmail_client.search(query)
        actionable_threads = [
            thread for thread in threads if self._extract_action_messages(thread.messages)
        ]
        body = self._monitor_body(query=query, threads=threads, actionable_threads=actionable_threads)
        artifact = Artifact(
            kind="inbox_triage",
            body=body,
            approval_channel="email-approvals" if actionable_threads else None,
            metadata={
                "actionable_threads": str(len(actionable_threads)),
                "threads_reviewed": str(len(threads)),
            },
        )
        if actionable_threads:
            return AgentResult(
                status="approval_required",
                message="Active inbox monitor found threads needing human review.",
                artifacts=[artifact],
                tool_calls=["gmail.search", "discord.post_approval"],
                approval_required=True,
            )
        return AgentResult(
            status="completed",
            message="Active inbox monitor completed with no actionable threads.",
            artifacts=[artifact],
            tool_calls=["gmail.search"],
        )

    def _draft_reply(self, job: JobEnvelope) -> AgentResult:
        self._require("gmail.thread_read")
        self._require("gmail.draft_reply")
        thread_id = str(job.payload["thread_id"])
        intent = str(job.payload.get("intent", "respond helpfully"))
        thread = self.gmail_client.read_thread(thread_id)
        draft = self._draft_body(thread, intent)
        return AgentResult(
            status="approval_required",
            message="Reply draft created for human approval. No email was sent.",
            artifacts=[
                Artifact(
                    kind="reply_draft",
                    body=draft,
                    approval_channel="email-approvals",
                    metadata={"thread_id": thread.thread_id},
                )
            ],
            tool_calls=["gmail.thread_read", "gmail.draft_reply", "discord.post_approval"],
            approval_required=True,
        )

    def _thread_summary(self, job: JobEnvelope) -> AgentResult:
        self._require("gmail.thread_read")
        thread_id = str(job.payload["thread_id"])
        thread = self.gmail_client.read_thread(thread_id)
        return AgentResult(
            status="completed",
            message="Thread summary created.",
            artifacts=[Artifact(kind="thread_summary", body=self._thread_summary_body(thread))],
            tool_calls=["gmail.thread_read"],
        )

    def _action_items(self, job: JobEnvelope) -> AgentResult:
        self._require("gmail.thread_read")
        thread_id = str(job.payload["thread_id"])
        thread = self.gmail_client.read_thread(thread_id)
        return AgentResult(
            status="completed",
            message="Action items extracted.",
            artifacts=[Artifact(kind="action_items", body=self._action_items_body(thread))],
            tool_calls=["gmail.thread_read"],
        )

    def _require(self, capability: str) -> None:
        if not self.policy.is_allowed("iris", capability):
            raise PermissionError(f"Iris is not allowed to use {capability}")

    def _summarize_threads(self, threads: list[EmailThread]) -> str:
        if not threads:
            return "No matching email threads found."
        lines = ["Iris inbox summary:"]
        for thread in threads:
            latest = thread.messages[-1].body if thread.messages else ""
            lines.append(
                f"- {safe_display_text(thread.subject, max_chars=120)} "
                f"({safe_display_text(thread.thread_id, max_chars=80)}): "
                f"{safe_display_text(latest)}"
            )
        return "\n".join(lines)

    def _format_thread_list(self, threads: list[EmailThread]) -> str:
        if not threads:
            return "No matching email threads found."
        return "\n".join(
            f"- {safe_display_text(thread.thread_id, max_chars=80)}: {safe_display_text(thread.subject, max_chars=160)}"
            for thread in threads
        )

    def _thread_summary_body(self, thread: EmailThread) -> str:
        lines = [
            "Thread summary:",
            f"- Thread: {safe_display_text(thread.thread_id, max_chars=80)}",
            f"- Subject: {safe_display_text(thread.subject, max_chars=160)}",
            f"- Messages: {len(thread.messages)} messages",
        ]
        if thread.messages:
            participants = sorted({safe_display_text(message.sender, max_chars=120) for message in thread.messages})
            lines.append(f"- Participants: {', '.join(participants)}")
            lines.append("- Recent context:")
            for message in thread.messages[-3:]:
                lines.append(f"  - {safe_display_text(message.sender, max_chars=80)}: {safe_display_text(message.body)}")
        return "\n".join(lines)

    def _action_items_body(self, thread: EmailThread) -> str:
        action_items = self._extract_action_messages(thread.messages)
        lines = [
            "Action items:",
            f"- Thread: {safe_display_text(thread.thread_id, max_chars=80)}",
            f"- Subject: {safe_display_text(thread.subject, max_chars=160)}",
        ]
        if not action_items:
            lines.append("- No clear action items found.")
            return "\n".join(lines)
        for item in action_items:
            lines.append(f"- {safe_display_text(item.body)}")
        return "\n".join(lines)

    def _monitor_body(
        self,
        *,
        query: str,
        threads: list[EmailThread],
        actionable_threads: list[EmailThread],
    ) -> str:
        lines = [
            "Iris active inbox monitor:",
            f"- Query: {safe_display_text(query, max_chars=160)}",
            f"- Threads reviewed: {len(threads)}",
            f"- Needs human review: {len(actionable_threads)}",
        ]
        if not actionable_threads:
            lines.append("- No actionable inbox threads found.")
            return "\n".join(lines)

        lines.append("")
        lines.append("Recommended actions:")
        for thread in actionable_threads:
            action_messages = self._extract_action_messages(thread.messages)
            latest_action = action_messages[-1].body if action_messages else ""
            lines.append(
                f"- {safe_display_text(thread.thread_id, max_chars=80)}: "
                f"{safe_display_text(thread.subject, max_chars=160)} — "
                f"{safe_display_text(latest_action)}"
            )
        return "\n".join(lines)

    def _extract_action_messages(self, messages: list[EmailMessage]) -> list[EmailMessage]:
        keywords = ("please ", "can we ", "could you ", "need ", "follow up", "schedule", "action")
        action_messages: list[EmailMessage] = []
        for message in messages:
            body_lower = message.body.lower()
            if any(keyword in body_lower for keyword in keywords):
                action_messages.append(message)
        return action_messages

    def _draft_body(self, thread: EmailThread, intent: str) -> str:
        recipient = thread.messages[-1].sender if thread.messages else "recipient"
        return "\n".join(
            [
                "Draft only — do not send without human approval.",
                f"To: {recipient}",
                f"Subject: Re: {thread.subject}",
                "",
                "Hi,",
                "",
                f"Thanks for your note. We will {intent}.",
                "",
                "Best,",
                "Noble Ridge Technologies",
            ]
        )
