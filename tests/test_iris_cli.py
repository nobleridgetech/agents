import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "noble_ridge_agents.cli", *args],
        check=False,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )


def test_iris_cli_inbox_summary_outputs_json_and_records_job(tmp_path):
    db_path = tmp_path / "jobs.db"

    completed = run_cli(
        "iris",
        "inbox-summary",
        "--query",
        "newer_than:7d",
        "--db",
        str(db_path),
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "completed"
    assert payload["approval_required"] is False
    assert payload["artifacts"][0]["kind"] == "inbox_summary"
    assert "Iris inbox summary" in payload["artifacts"][0]["body"]
    assert payload["job_id"]

    status = run_cli("status", payload["job_id"], "--db", str(db_path))
    assert status.returncode == 0, status.stderr
    saved = json.loads(status.stdout)
    assert saved["job_id"] == payload["job_id"]
    assert saved["status"] == "completed"
    assert saved["tool_calls"] == ["gmail.search"]


def test_iris_cli_defaults_to_fake_gmail_adapter(tmp_path):
    db_path = tmp_path / "jobs.db"

    completed = run_cli("iris", "find-email", "--query", "anything", "--db", str(db_path))

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "completed"
    assert "thread-123" in payload["artifacts"][0]["body"]


def test_iris_cli_draft_reply_requires_approval_and_does_not_send(tmp_path):
    db_path = tmp_path / "jobs.db"

    completed = run_cli(
        "iris",
        "draft-reply",
        "--thread-id",
        "thread-123",
        "--intent",
        "send next steps tomorrow",
        "--db",
        str(db_path),
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "approval_required"
    assert payload["approval_required"] is True
    assert payload["artifacts"][0]["kind"] == "reply_draft"
    assert payload["artifacts"][0]["approval_channel"] == "email-approvals"
    assert "Draft only" in payload["artifacts"][0]["body"]
    assert "gmail.send" not in payload["tool_calls"]
