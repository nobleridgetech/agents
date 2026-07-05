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


def test_iris_cli_thread_summary_outputs_json(tmp_path):
    db_path = tmp_path / "jobs.db"

    completed = run_cli("iris", "thread-summary", "--thread-id", "thread-123", "--db", str(db_path))

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "completed"
    assert payload["artifacts"][0]["kind"] == "thread_summary"
    assert "Thread summary" in payload["artifacts"][0]["body"]


def test_iris_cli_action_items_outputs_json(tmp_path):
    db_path = tmp_path / "jobs.db"

    completed = run_cli("iris", "action-items", "--thread-id", "thread-123", "--db", str(db_path))

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "completed"
    assert payload["artifacts"][0]["kind"] == "action_items"
    assert "Action items" in payload["artifacts"][0]["body"]
    assert "gmail.thread_read" in payload["tool_calls"]
