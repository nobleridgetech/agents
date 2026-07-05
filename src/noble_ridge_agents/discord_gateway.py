from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from noble_ridge_agents.agents.iris import IrisAgent
from noble_ridge_agents.content_safety import mask_sensitive_text
from noble_ridge_agents.fixtures import demo_gmail_client
from noble_ridge_agents.jobs.schema import AgentResult, JobEnvelope
from noble_ridge_agents.jobs.sqlite_store import SQLiteJobStore
from noble_ridge_agents.tools.gmail import FakeGmailClient, RealGmailClient

DEFAULT_DB_PATH = ".noble-ridge-agents/jobs.db"
TOKEN_ENV_VAR = "NRT_DISCORD_TOKEN"


class MessageResponder(Protocol):
    async def send(self, content: str, *, ephemeral: bool = False) -> None: ...


@dataclass(frozen=True, slots=True)
class DiscordGatewayConfig:
    db_path: Path = Path(DEFAULT_DB_PATH)
    gmail_adapter: str = "fake"
    gmail_token_path: Path | None = None
    gmail_max_results: int = 10
    iris_channel_id: int | None = None
    approval_channel_id: int | None = None
    iris_monitor_enabled: bool = False
    iris_monitor_query: str = "in:inbox newer_than:1d"
    iris_monitor_interval_seconds: int = 300

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "DiscordGatewayConfig":
        source = env if env is not None else os.environ
        gmail_adapter = source.get("NRT_GMAIL_ADAPTER", "fake").lower()
        if gmail_adapter not in {"fake", "real"}:
            raise ValueError("NRT_GMAIL_ADAPTER must be 'fake' or 'real'")

        token_path = source.get("NRT_GMAIL_TOKEN_PATH")
        iris_channel = source.get("NRT_DISCORD_IRIS_CHANNEL_ID")
        approval_channel = source.get("NRT_DISCORD_APPROVAL_CHANNEL_ID")
        monitor_enabled = source.get("NRT_IRIS_MONITOR_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        return cls(
            db_path=Path(source.get("NRT_JOB_DB_PATH", DEFAULT_DB_PATH)),
            gmail_adapter=gmail_adapter,
            gmail_token_path=Path(token_path) if token_path else None,
            gmail_max_results=int(source.get("NRT_GMAIL_MAX_RESULTS", "10")),
            iris_channel_id=int(iris_channel) if iris_channel else None,
            approval_channel_id=int(approval_channel) if approval_channel else None,
            iris_monitor_enabled=monitor_enabled,
            iris_monitor_query=source.get("NRT_IRIS_MONITOR_QUERY", "in:inbox newer_than:1d"),
            iris_monitor_interval_seconds=int(source.get("NRT_IRIS_MONITOR_INTERVAL_SECONDS", "300")),
        )


@dataclass(slots=True)
class DiscordIrisGateway:
    db_path: str | Path = DEFAULT_DB_PATH
    gmail_client: Any | None = None
    approval_responder: MessageResponder | None = None
    iris_channel_id: int | None = None

    async def handle_iris_command(
        self,
        *,
        command: str,
        requester: str,
        channel: str,
        responder: MessageResponder,
        query: str | None = None,
        thread_id: str | None = None,
        intent: str | None = None,
    ) -> str | None:
        if self.iris_channel_id is not None and channel != str(self.iris_channel_id):
            await responder.send("Iris commands are only enabled in the configured Iris channel.", ephemeral=True)
            return None

        job_type, payload = iris_job_from_discord_command(
            command=command,
            query=query,
            thread_id=thread_id,
            intent=intent,
        )
        job = JobEnvelope.create(
            requester=requester,
            source="discord",
            channel=channel,
            assigned_agent="iris",
            job_type=job_type,
            payload=payload,
        )
        store = SQLiteJobStore(self.db_path)
        try:
            store.create(job)
            result = IrisAgent(gmail_client=self.gmail_client or demo_gmail_client()).handle(job)
            persist_result(store, job.job_id, result)
        finally:
            store.close()

        await self._post_result(result=result, responder=responder)
        return job.job_id

    async def run_iris_monitor_once(
        self,
        *,
        responder: MessageResponder,
        channel: str,
        query: str = "in:inbox newer_than:1d",
        post_quiet_results: bool = False,
    ) -> str:
        job = JobEnvelope.create(
            requester="iris-monitor",
            source="discord-monitor",
            channel=channel,
            assigned_agent="iris",
            job_type="iris.monitor_inbox",
            payload={"query": query},
        )
        store = SQLiteJobStore(self.db_path)
        try:
            store.create(job)
            result = IrisAgent(gmail_client=self.gmail_client or demo_gmail_client()).handle(job)
            persist_result(store, job.job_id, result)
        finally:
            store.close()

        if result.approval_required or post_quiet_results:
            await self._post_result(result=result, responder=responder)
        return job.job_id

    async def _post_result(self, *, result: AgentResult, responder: MessageResponder) -> None:
        if not result.artifacts:
            await responder.send(mask_sensitive_text(result.message, normalize_whitespace=False))
            return

        artifact = result.artifacts[0]
        content = mask_sensitive_text(artifact.body, normalize_whitespace=False)
        if result.approval_required:
            target = self.approval_responder or responder
            await target.send(content)
            return

        await responder.send(content)


def iris_job_from_discord_command(
    *,
    command: str,
    query: str | None = None,
    thread_id: str | None = None,
    intent: str | None = None,
) -> tuple[str, dict[str, str]]:
    if command == "inbox-summary":
        return "iris.inbox_summary", {"query": query or "newer_than:7d"}
    if command == "find-email":
        if not query:
            raise ValueError("find-email requires query")
        return "iris.find_email", {"query": query}
    if command == "thread-summary":
        if not thread_id:
            raise ValueError("thread-summary requires thread_id")
        return "iris.thread_summary", {"thread_id": thread_id}
    if command == "action-items":
        if not thread_id:
            raise ValueError("action-items requires thread_id")
        return "iris.action_items", {"thread_id": thread_id}
    if command == "draft-reply":
        if not thread_id:
            raise ValueError("draft-reply requires thread_id")
        return "iris.draft_reply", {"thread_id": thread_id, "intent": intent or "respond helpfully"}
    raise ValueError(f"Unsupported Iris Discord command: {command}")


def persist_result(store: SQLiteJobStore, job_id: str, result: AgentResult) -> None:
    for tool_call in result.tool_calls:
        store.record_tool_call(job_id, tool_call)
    for artifact in result.artifacts:
        store.add_artifact(job_id, artifact)
    store.set_status(job_id, result.status)


def require_discord_token(env: dict[str, str] | None = None) -> str:
    source = env if env is not None else os.environ
    token = source.get(TOKEN_ENV_VAR)
    if not token:
        raise RuntimeError(f"{TOKEN_ENV_VAR} must be set to run the Discord gateway")
    return token


def startup_message() -> str:
    require_discord_token()
    return "Discord gateway configured from environment. Token value will not be logged."


def gmail_client_from_config(config: DiscordGatewayConfig) -> Any:
    if config.gmail_adapter == "fake":
        return demo_gmail_client()
    if config.gmail_token_path is None:
        raise RuntimeError("NRT_GMAIL_TOKEN_PATH must be set when NRT_GMAIL_ADAPTER=real")
    return RealGmailClient.from_token_file(config.gmail_token_path, max_results=config.gmail_max_results)


def build_gateway_from_env(env: dict[str, str] | None = None) -> DiscordIrisGateway:
    config = DiscordGatewayConfig.from_env(env)
    return DiscordIrisGateway(
        db_path=config.db_path,
        gmail_client=gmail_client_from_config(config),
        iris_channel_id=config.iris_channel_id,
    )


class InteractionResponder:
    def __init__(self, interaction: Any) -> None:
        self.interaction = interaction

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        if self.interaction.response.is_done():
            await self.interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await self.interaction.response.send_message(content, ephemeral=ephemeral)


class ApprovalChannelResponder:
    def __init__(self, bot: Any, channel_id: int) -> None:
        self.bot = bot
        self.channel_id = channel_id

    async def send(self, content: str, *, ephemeral: bool = False) -> None:
        channel = await self.bot.fetch_channel(self.channel_id)
        await channel.send(content)


async def run_iris_monitor_loop(
    *,
    gateway: DiscordIrisGateway,
    responder: MessageResponder,
    channel: str,
    query: str,
    interval_seconds: int,
) -> None:
    while True:
        await gateway.run_iris_monitor_once(responder=responder, channel=channel, query=query)
        await asyncio.sleep(interval_seconds)


def build_discord_bot(gateway: DiscordIrisGateway | None = None, config: DiscordGatewayConfig | None = None):
    import discord
    from discord import app_commands
    from discord.ext import commands

    config = config or DiscordGatewayConfig.from_env()
    gateway = gateway or DiscordIrisGateway(
        db_path=config.db_path,
        gmail_client=gmail_client_from_config(config),
        iris_channel_id=config.iris_channel_id,
    )
    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="!", intents=intents)
    if config.approval_channel_id is not None and gateway.approval_responder is None:
        gateway.approval_responder = ApprovalChannelResponder(bot=bot, channel_id=config.approval_channel_id)
    iris = app_commands.Group(name="iris", description="Iris email administration workflows")
    synced_once = False
    monitor_task: asyncio.Task | None = None

    @bot.listen("on_ready")
    async def sync_slash_commands_once() -> None:
        nonlocal synced_once, monitor_task
        if synced_once:
            if config.iris_monitor_enabled and (monitor_task is None or monitor_task.done()):
                monitor_task = _start_iris_monitor_task()
            return
        await bot.tree.sync()
        synced_once = True
        if config.iris_monitor_enabled and (monitor_task is None or monitor_task.done()):
            monitor_task = _start_iris_monitor_task()

    def _start_iris_monitor_task() -> asyncio.Task:
        channel_id = config.approval_channel_id or config.iris_channel_id
        if channel_id is None:
            raise RuntimeError("NRT_IRIS_MONITOR_ENABLED requires an approval or Iris channel ID")
        responder = gateway.approval_responder or ApprovalChannelResponder(bot=bot, channel_id=channel_id)
        return asyncio.create_task(
            run_iris_monitor_loop(
                gateway=gateway,
                responder=responder,
                channel=str(channel_id),
                query=config.iris_monitor_query,
                interval_seconds=config.iris_monitor_interval_seconds,
            )
        )

    @iris.command(name="inbox-summary", description="Create a masked Iris inbox summary")
    async def inbox_summary(interaction: discord.Interaction, query: str = "newer_than:7d"):
        await gateway.handle_iris_command(
            command="inbox-summary",
            requester=str(interaction.user.id),
            channel=str(interaction.channel_id),
            responder=InteractionResponder(interaction),
            query=query,
        )

    @iris.command(name="find-email", description="Find matching email threads")
    async def find_email(interaction: discord.Interaction, query: str):
        await gateway.handle_iris_command(
            command="find-email",
            requester=str(interaction.user.id),
            channel=str(interaction.channel_id),
            responder=InteractionResponder(interaction),
            query=query,
        )

    @iris.command(name="thread-summary", description="Summarize a Gmail thread")
    async def thread_summary(interaction: discord.Interaction, thread_id: str):
        await gateway.handle_iris_command(
            command="thread-summary",
            requester=str(interaction.user.id),
            channel=str(interaction.channel_id),
            responder=InteractionResponder(interaction),
            thread_id=thread_id,
        )

    @iris.command(name="action-items", description="Extract action items from a Gmail thread")
    async def action_items(interaction: discord.Interaction, thread_id: str):
        await gateway.handle_iris_command(
            command="action-items",
            requester=str(interaction.user.id),
            channel=str(interaction.channel_id),
            responder=InteractionResponder(interaction),
            thread_id=thread_id,
        )

    @iris.command(name="draft-reply", description="Draft a reply for approval; never sends email")
    async def draft_reply(interaction: discord.Interaction, thread_id: str, intent: str = "respond helpfully"):
        await gateway.handle_iris_command(
            command="draft-reply",
            requester=str(interaction.user.id),
            channel=str(interaction.channel_id),
            responder=InteractionResponder(interaction),
            thread_id=thread_id,
            intent=intent,
        )

    bot.tree.add_command(iris)
    return bot


def main() -> int:
    token = require_discord_token()
    bot = build_discord_bot()
    bot.run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
