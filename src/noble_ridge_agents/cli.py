from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from noble_ridge_agents.agents.iris import IrisAgent
from noble_ridge_agents.fixtures import demo_gmail_client
from noble_ridge_agents.jobs.schema import AgentResult, JobEnvelope
from noble_ridge_agents.jobs.sqlite_store import SQLiteJobStore
from noble_ridge_agents.tools.gmail import RealGmailClient


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "iris":
        return run_iris(args)
    if args.command == "status":
        return run_status(args)

    parser.print_help()
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="noble-ridge-agents")
    parser.add_argument("--db", default=".noble-ridge-agents/jobs.db", help="SQLite job store path")
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument("--db", default=None, help="SQLite job store path")
    subparsers = parser.add_subparsers(dest="command")

    iris = subparsers.add_parser("iris", help="Run Iris email workflows")
    iris.add_argument("--db", default=None, help="SQLite job store path")
    iris_sub = iris.add_subparsers(dest="iris_command", required=True)

    inbox = iris_sub.add_parser("inbox-summary", parents=[db_parent], help="Create an inbox summary")
    inbox.add_argument("--query", default="newer_than:7d")
    add_gmail_options(inbox)

    find = iris_sub.add_parser("find-email", parents=[db_parent], help="Find matching email threads")
    find.add_argument("--query", required=True)
    add_gmail_options(find)

    draft = iris_sub.add_parser("draft-reply", parents=[db_parent], help="Draft a reply for approval")
    draft.add_argument("--thread-id", required=True)
    draft.add_argument("--intent", default="respond helpfully")
    add_gmail_options(draft)

    thread_summary = iris_sub.add_parser("thread-summary", parents=[db_parent], help="Summarize a Gmail thread")
    thread_summary.add_argument("--thread-id", required=True)
    add_gmail_options(thread_summary)

    action_items = iris_sub.add_parser("action-items", parents=[db_parent], help="Extract action items from a Gmail thread")
    action_items.add_argument("--thread-id", required=True)
    add_gmail_options(action_items)

    status = subparsers.add_parser("status", parents=[db_parent], help="Read a job from the SQLite store")
    status.add_argument("job_id")
    return parser


def run_iris(args: argparse.Namespace) -> int:
    job_type, payload = iris_job(args)
    job = JobEnvelope.create(
        requester="local-cli",
        source="cli",
        channel="local",
        assigned_agent="iris",
        job_type=job_type,
        payload=payload,
    )
    store = SQLiteJobStore(resolve_db_path(args))
    try:
        store.create(job)
        result = IrisAgent(gmail_client=gmail_client_from_args(args)).handle(job)
        for tool_call in result.tool_calls:
            store.record_tool_call(job.job_id, tool_call)
        for artifact in result.artifacts:
            store.add_artifact(job.job_id, artifact)
        store.set_status(job.job_id, result.status)
        print(json.dumps(result_payload(job.job_id, result), indent=2, sort_keys=True))
        return 0
    finally:
        store.close()


def run_status(args: argparse.Namespace) -> int:
    store = SQLiteJobStore(resolve_db_path(args))
    try:
        job = store.get(args.job_id)
        if job is None:
            print(json.dumps({"error": "job_not_found", "job_id": args.job_id}, sort_keys=True))
            return 1
        print(json.dumps(asdict(job), indent=2, sort_keys=True))
        return 0
    finally:
        store.close()


def iris_job(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.iris_command == "inbox-summary":
        return "iris.inbox_summary", {"query": args.query}
    if args.iris_command == "find-email":
        return "iris.find_email", {"query": args.query}
    if args.iris_command == "draft-reply":
        return "iris.draft_reply", {"thread_id": args.thread_id, "intent": args.intent}
    if args.iris_command == "thread-summary":
        return "iris.thread_summary", {"thread_id": args.thread_id}
    if args.iris_command == "action-items":
        return "iris.action_items", {"thread_id": args.thread_id}
    raise ValueError(f"Unsupported Iris command: {args.iris_command}")


def add_gmail_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gmail", choices=["fake", "real"], default="fake", help="Gmail adapter to use")
    parser.add_argument(
        "--token",
        default=".secrets/google_token.json",
        help="Google OAuth token path for --gmail real",
    )
    parser.add_argument("--max-results", type=int, default=10, help="Maximum Gmail search results")


def gmail_client_from_args(args: argparse.Namespace):
    if getattr(args, "gmail", "fake") == "real":
        try:
            return RealGmailClient.from_token_file(args.token, max_results=args.max_results)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
    return demo_gmail_client()


def resolve_db_path(args: argparse.Namespace) -> Path:
    db_path = getattr(args, "db", None) or ".noble-ridge-agents/jobs.db"
    return Path(db_path)


def result_payload(job_id: str, result: AgentResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["job_id"] = job_id
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
