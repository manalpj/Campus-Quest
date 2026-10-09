"""Tests for deployment configuration and Procfile specification."""

from pathlib import Path
import config


def test_procfile_exists_and_contains_valid_start_command():
    """Procfile must exist in repo root and define the uvicorn start command."""
    procfile_path = Path(__file__).parent.parent / "Procfile"
    assert procfile_path.is_file(), "Procfile must exist in repository root"

    content = procfile_path.read_text(encoding="utf-8").strip()
    expected_command = "web: uvicorn main:app --host 0.0.0.0 --port $PORT"
    assert content == expected_command, (
        f"Procfile content mismatch. Expected '{expected_command}', got '{content}'"
    )


def test_production_environment_variables_parsed_correctly(monkeypatch):
    """config helpers must parse production PORT, ENV, and DB_PATH with whitespace stripping."""
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("PORT", " 8080 ")
    monkeypatch.setenv("DB_PATH", " /data/quest.db ")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", " * ")

    env_val = config._get_str("ENV", "development").lower()
    port_val = config._get_int("PORT", 8000)
    db_path_val = config._get_str("DB_PATH", "data/quest.db")
    ips_val = config._get_str("FORWARDED_ALLOW_IPS", "*")

    assert env_val == "production"
    assert port_val == 8080
    assert db_path_val == "/data/quest.db"
    assert ips_val == "*"


def test_deploy_doc_exists_and_has_troubleshooting():
    """docs/DEPLOY.md must exist and contain key deployment instructions."""
    deploy_doc = Path(__file__).parent.parent / "docs" / "DEPLOY.md"
    assert deploy_doc.is_file()

    content = deploy_doc.read_text(encoding="utf-8")
    assert "Railway" in content
    assert "FORWARDED_ALLOW_IPS" in content
    assert "/data/quest.db" in content
    assert "Troubleshooting" in content
    assert "502" in content
