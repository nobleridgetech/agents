import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_iris_cli_real_gmail_requires_existing_token(tmp_path):
    missing_token = tmp_path / "missing-token.json"
    db_path = tmp_path / "jobs.db"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "noble_ridge_agents.cli",
            "iris",
            "inbox-summary",
            "--gmail",
            "real",
            "--token",
            str(missing_token),
            "--db",
            str(db_path),
        ],
        check=False,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 1
    assert "Gmail token file not found" in completed.stderr
    assert str(missing_token) in completed.stderr
    assert "client_secret" not in completed.stderr.lower()
    assert "refresh_token" not in completed.stderr.lower()
