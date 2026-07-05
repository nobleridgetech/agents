import asyncio

import pytest

from noble_ridge_agents.jobs.sqlite_store import SQLiteJobStore
from noble_ridge_agents.tools.gmail import EmailMessage, EmailThread, FakeGmailClient


class FakeResponder:
    def __init__(self):
        self.messages = []

    async def send(self, content: str, *, ephemeral: bool = False):
        self.messages.append({"content": content, "ephemeral": ephemeral})


def secret_gmail_client() -> FakeGmailClient:
    return FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-123",
                subject="Reset for client@example.com",
                messages=[
                    EmailMessage(
                        sender="client@example.com",
                        body="Please review https://example.com/private?token=abc and call 555-123-4567.",
                    )
                ],
            )
        ]
    )


def test_discord_token_must_come_from_environment(monkeypatch):
    from noble_ridge_agents.discord_gateway import require_discord_token

    monkeypatch.delenv("NRT_DISCORD_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="NRT_DISCORD_TOKEN"):
        require_discord_token()

    monkeypatch.setenv("NRT_DISCORD_TOKEN", "super-secret-token")

    assert require_discord_token() == "super-secret-token"


def test_discord_iris_inbox_summary_posts_masked_output_and_persists_job(tmp_path):
    from noble_ridge_agents.discord_gateway import DiscordIrisGateway

    db_path = tmp_path / "jobs.db"
    responder = FakeResponder()
    gateway = DiscordIrisGateway(db_path=db_path, gmail_client=secret_gmail_client())

    job_id = asyncio.run(
        gateway.handle_iris_command(
            command="inbox-summary",
            requester="discord-user-1",
            channel="agent-email",
            responder=responder,
            query="newer_than:7d",
        )
    )

    assert len(responder.messages) == 1
    posted = responder.messages[0]["content"]
    assert "Iris inbox summary" in posted
    assert "client@example.com" not in posted
    assert "https://example.com" not in posted
    assert "555-123-4567" not in posted
    assert "[redacted-email]" in posted
    assert "[redacted-url]" in posted
    assert "[redacted-phone]" in posted

    store = SQLiteJobStore(db_path)
    try:
        saved = store.get(job_id)
    finally:
        store.close()
    assert saved is not None
    assert saved.source == "discord"
    assert saved.channel == "agent-email"
    assert saved.job_type == "iris.inbox_summary"
    assert saved.status == "completed"
    assert saved.tool_calls == ["gmail.search"]
    assert saved.artifacts[0].body == posted


@pytest.mark.parametrize(
    ("command", "expected_job_type", "expected_kind", "kwargs"),
    [
        ("find-email", "iris.find_email", "email_search_results", {"query": "from:anyone"}),
        ("thread-summary", "iris.thread_summary", "thread_summary", {"thread_id": "thread-123"}),
        ("action-items", "iris.action_items", "action_items", {"thread_id": "thread-123"}),
    ],
)
def test_discord_iris_read_only_commands_are_persisted(tmp_path, command, expected_job_type, expected_kind, kwargs):
    from noble_ridge_agents.discord_gateway import DiscordIrisGateway

    db_path = tmp_path / "jobs.db"
    responder = FakeResponder()
    gateway = DiscordIrisGateway(db_path=db_path, gmail_client=secret_gmail_client())

    job_id = asyncio.run(
        gateway.handle_iris_command(
            command=command,
            requester="discord-user-1",
            channel="agent-email",
            responder=responder,
            **kwargs,
        )
    )

    assert len(responder.messages) == 1
    store = SQLiteJobStore(db_path)
    try:
        saved = store.get(job_id)
    finally:
        store.close()
    assert saved is not None
    assert saved.job_type == expected_job_type
    assert saved.artifacts[0].kind == expected_kind
    assert saved.artifacts[0].body == responder.messages[0]["content"]


def test_discord_iris_draft_reply_routes_to_approval_channel_and_does_not_send(tmp_path):
    from noble_ridge_agents.discord_gateway import DiscordIrisGateway

    db_path = tmp_path / "jobs.db"
    responder = FakeResponder()
    approval_responder = FakeResponder()
    gateway = DiscordIrisGateway(
        db_path=db_path,
        gmail_client=secret_gmail_client(),
        approval_responder=approval_responder,
    )

    job_id = asyncio.run(
        gateway.handle_iris_command(
            command="draft-reply",
            requester="discord-user-1",
            channel="agent-email",
            responder=responder,
            thread_id="thread-123",
            intent="send next steps tomorrow",
        )
    )

    assert responder.messages == []
    assert len(approval_responder.messages) == 1
    posted = approval_responder.messages[0]["content"]
    assert "Draft only" in posted
    assert "gmail.send" not in posted
    assert "client@example.com" not in posted
    assert "[redacted-email]" in posted

    store = SQLiteJobStore(db_path)
    try:
        saved = store.get(job_id)
    finally:
        store.close()
    assert saved is not None
    assert saved.status == "approval_required"
    assert saved.artifacts[0].approval_channel == "email-approvals"
    assert "gmail.send" not in saved.tool_calls


def test_discord_gateway_does_not_log_or_print_token(monkeypatch, capsys):
    from noble_ridge_agents.discord_gateway import startup_message

    monkeypatch.setenv("NRT_DISCORD_TOKEN", "super-secret-token")

    message = startup_message()
    captured = capsys.readouterr()

    assert "super-secret-token" not in message
    assert "super-secret-token" not in captured.out
    assert "super-secret-token" not in captured.err
    assert "Discord gateway configured" in message


def test_discord_gateway_config_reads_runtime_values_from_environment(monkeypatch, tmp_path):
    from noble_ridge_agents.discord_gateway import DiscordGatewayConfig

    db_path = tmp_path / "discord-jobs.db"
    token_path = tmp_path / "gmail-token.json"
    token_path.write_text("{}")
    monkeypatch.setenv("NRT_JOB_DB_PATH", str(db_path))
    monkeypatch.setenv("NRT_GMAIL_ADAPTER", "real")
    monkeypatch.setenv("NRT_GMAIL_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("NRT_GMAIL_MAX_RESULTS", "7")
    monkeypatch.setenv("NRT_DISCORD_IRIS_CHANNEL_ID", "1521672682347692073")
    monkeypatch.setenv("NRT_DISCORD_APPROVAL_CHANNEL_ID", "123456789")
    monkeypatch.setenv("NRT_IRIS_MONITOR_ENABLED", "true")
    monkeypatch.setenv("NRT_IRIS_MONITOR_QUERY", "in:inbox newer_than:2d")
    monkeypatch.setenv("NRT_IRIS_MONITOR_INTERVAL_SECONDS", "120")

    config = DiscordGatewayConfig.from_env()

    assert config.db_path == db_path
    assert config.gmail_adapter == "real"
    assert config.gmail_token_path == token_path
    assert config.gmail_max_results == 7
    assert config.iris_channel_id == 1521672682347692073
    assert config.approval_channel_id == 123456789
    assert config.iris_monitor_enabled is True
    assert config.iris_monitor_query == "in:inbox newer_than:2d"
    assert config.iris_monitor_interval_seconds == 120


def test_discord_iris_gateway_rejects_commands_outside_configured_channel(tmp_path):
    from noble_ridge_agents.discord_gateway import DiscordIrisGateway

    db_path = tmp_path / "jobs.db"
    responder = FakeResponder()
    gateway = DiscordIrisGateway(
        db_path=db_path,
        gmail_client=secret_gmail_client(),
        iris_channel_id=1521672682347692073,
    )

    job_id = asyncio.run(
        gateway.handle_iris_command(
            command="inbox-summary",
            requester="discord-user-1",
            channel="999999999999999999",
            responder=responder,
            query="newer_than:7d",
        )
    )

    assert job_id is None
    assert responder.messages == [
        {
            "content": "Iris commands are only enabled in the configured Iris channel.",
            "ephemeral": True,
        }
    ]
    store = SQLiteJobStore(db_path)
    try:
        assert store.get("999999999999999999") is None
    finally:
        store.close()


def test_discord_iris_monitor_run_posts_to_approval_channel_and_persists_job(tmp_path):
    from noble_ridge_agents.discord_gateway import DiscordIrisGateway

    db_path = tmp_path / "jobs.db"
    responder = FakeResponder()
    gateway = DiscordIrisGateway(db_path=db_path, gmail_client=secret_gmail_client())

    job_id = asyncio.run(
        gateway.run_iris_monitor_once(
            responder=responder,
            channel="agent-email",
            query="in:inbox newer_than:1d",
        )
    )

    assert len(responder.messages) == 1
    posted = responder.messages[0]["content"]
    assert "Iris active inbox monitor" in posted
    assert "Needs human review: 1" in posted
    assert "client@example.com" not in posted
    assert "[redacted-email]" in posted

    store = SQLiteJobStore(db_path)
    try:
        saved = store.get(job_id)
    finally:
        store.close()
    assert saved is not None
    assert saved.requester == "iris-monitor"
    assert saved.source == "discord-monitor"
    assert saved.job_type == "iris.monitor_inbox"
    assert saved.status == "approval_required"
    assert saved.tool_calls == ["gmail.search", "discord.post_approval"]
    assert saved.artifacts[0].kind == "inbox_triage"


def test_discord_iris_monitor_quiet_run_is_persisted_without_discord_noise(tmp_path):
    from noble_ridge_agents.discord_gateway import DiscordIrisGateway

    db_path = tmp_path / "jobs.db"
    responder = FakeResponder()
    gmail = FakeGmailClient(
        threads=[
            EmailThread(
                thread_id="thread-456",
                subject="Newsletter",
                messages=[EmailMessage(sender="news@example.com", body="FYI only.")],
            )
        ]
    )
    gateway = DiscordIrisGateway(db_path=db_path, gmail_client=gmail)

    job_id = asyncio.run(
        gateway.run_iris_monitor_once(
            responder=responder,
            channel="agent-email",
            query="in:inbox newer_than:1d",
        )
    )

    assert responder.messages == []
    store = SQLiteJobStore(db_path)
    try:
        saved = store.get(job_id)
    finally:
        store.close()
    assert saved is not None
    assert saved.status == "completed"
    assert saved.artifacts[0].kind == "inbox_triage"


def test_discord_gateway_config_rejects_invalid_gmail_adapter(monkeypatch):
    from noble_ridge_agents.discord_gateway import DiscordGatewayConfig

    monkeypatch.setenv("NRT_GMAIL_ADAPTER", "send-enabled")

    with pytest.raises(ValueError, match="NRT_GMAIL_ADAPTER"):
        DiscordGatewayConfig.from_env()


def test_build_gateway_from_env_defaults_to_fake_gmail_and_configured_db(monkeypatch, tmp_path):
    from noble_ridge_agents.discord_gateway import build_gateway_from_env

    db_path = tmp_path / "discord-jobs.db"
    monkeypatch.setenv("NRT_JOB_DB_PATH", str(db_path))
    monkeypatch.delenv("NRT_GMAIL_ADAPTER", raising=False)

    gateway = build_gateway_from_env()

    assert gateway.db_path == db_path
    assert isinstance(gateway.gmail_client, FakeGmailClient)


def test_build_gateway_from_env_uses_real_gmail_when_configured(monkeypatch, tmp_path):
    from noble_ridge_agents.discord_gateway import build_gateway_from_env
    from noble_ridge_agents.tools.gmail import RealGmailClient

    db_path = tmp_path / "discord-jobs.db"
    token_path = tmp_path / "gmail-token.json"
    token_path.write_text("{}")
    constructed = {}

    class SentinelRealGmailClient:
        pass

    def fake_from_token_file(path, max_results):
        constructed["path"] = path
        constructed["max_results"] = max_results
        return SentinelRealGmailClient()

    monkeypatch.setenv("NRT_JOB_DB_PATH", str(db_path))
    monkeypatch.setenv("NRT_GMAIL_ADAPTER", "real")
    monkeypatch.setenv("NRT_GMAIL_TOKEN_PATH", str(token_path))
    monkeypatch.setenv("NRT_GMAIL_MAX_RESULTS", "3")
    monkeypatch.setattr(RealGmailClient, "from_token_file", fake_from_token_file)

    gateway = build_gateway_from_env()

    assert gateway.db_path == db_path
    assert isinstance(gateway.gmail_client, SentinelRealGmailClient)
    assert constructed == {"path": token_path, "max_results": 3}


def test_build_gateway_from_env_requires_real_gmail_token_path(monkeypatch):
    from noble_ridge_agents.discord_gateway import build_gateway_from_env

    monkeypatch.setenv("NRT_GMAIL_ADAPTER", "real")
    monkeypatch.delenv("NRT_GMAIL_TOKEN_PATH", raising=False)

    with pytest.raises(RuntimeError, match="NRT_GMAIL_TOKEN_PATH"):
        build_gateway_from_env()


class FakeDiscordChannel:
    def __init__(self):
        self.messages = []

    async def send(self, content: str):
        self.messages.append(content)


class FakeDiscordBot:
    def __init__(self):
        self.fetched_channel_ids = []
        self.channel = FakeDiscordChannel()

    async def fetch_channel(self, channel_id: int):
        self.fetched_channel_ids.append(channel_id)
        return self.channel


def test_approval_channel_responder_posts_to_configured_discord_channel():
    from noble_ridge_agents.discord_gateway import ApprovalChannelResponder

    bot = FakeDiscordBot()
    responder = ApprovalChannelResponder(bot=bot, channel_id=123456789)

    asyncio.run(responder.send("Approval needed", ephemeral=True))

    assert bot.fetched_channel_ids == [123456789]
    assert bot.channel.messages == ["Approval needed"]


def test_build_discord_bot_registers_ready_sync_handler():
    from noble_ridge_agents.discord_gateway import DiscordGatewayConfig, build_discord_bot, build_gateway_from_env

    env = {"NRT_JOB_DB_PATH": "/tmp/nrt-test-discord.db", "NRT_GMAIL_ADAPTER": "fake"}
    gateway = build_gateway_from_env(env)
    config = DiscordGatewayConfig.from_env(env)

    bot = build_discord_bot(gateway=gateway, config=config)

    assert "on_ready" in bot.extra_events
