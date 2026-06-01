"""Tests for lazy environment configuration."""

import subprocess
import sys
from pathlib import Path


def test_settings_import_does_not_require_all_credentials(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import config.settings; print('ok')",
        ],
        cwd=tmp_path,
        env={"PYTHONPATH": str(repo_root)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "ok"


def test_require_env_raises_clear_error(monkeypatch):
    from config.settings import require_env

    monkeypatch.delenv("BOOK_PIPELINE_TEST_REQUIRED", raising=False)

    try:
        require_env("BOOK_PIPELINE_TEST_REQUIRED")
    except EnvironmentError as exc:
        assert str(exc) == (
            "Missing required environment variable: BOOK_PIPELINE_TEST_REQUIRED"
        )
    else:
        raise AssertionError("require_env should raise for missing values")


def test_require_env_returns_existing_value(monkeypatch):
    from config.settings import require_env

    monkeypatch.setenv("BOOK_PIPELINE_TEST_REQUIRED", "present")
    assert require_env("BOOK_PIPELINE_TEST_REQUIRED") == "present"
