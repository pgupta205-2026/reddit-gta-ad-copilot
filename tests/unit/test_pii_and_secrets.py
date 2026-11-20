"""Unit tests for Cloud DLP/local PII redaction and GCP Secret Manager hygiene."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.security.pii_redactor import PiiRedactor
from app.security.secrets import SecretLookupError, SecretManagerProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_PATTERNS = (
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
)


def test_local_pii_redactor_scrubs_all_sensitive_entities() -> None:
    redactor = PiiRedactor(enable_cloud_dlp=False)
    raw = (
        "Email lead@example.com, phone (415) 555-0199, IP 198.51.100.7, "
        "SSN 123-45-6789, user u/vicecity_fan, token Bearer eyJhbGciOiJIUzI1NiJ9.abc"
    )
    report = redactor.redact_with_report(raw)
    assert report.findings_count >= 5
    for forbidden in (
        "lead@example.com",
        "415",
        "198.51.100.7",
        "123-45-6789",
        "u/vicecity_fan",
        "eyJhbGciOiJIUzI1NiJ9",
    ):
        assert forbidden not in report.redacted_text


def test_cloud_dlp_backend_invoked_when_enabled() -> None:
    class FakeDlpClient:
        def __init__(self) -> None:
            self.called = False

        def deidentify_content(self, *, request: dict) -> SimpleNamespace:
            self.called = True
            value = request["item"]["value"].replace("Alice Smith", "[PERSON_NAME]")
            return SimpleNamespace(item=SimpleNamespace(value=value))

    fake_client = FakeDlpClient()
    redactor = PiiRedactor(
        gcp_project_id="demo-gcp-project",
        enable_cloud_dlp=True,
        dlp_client=fake_client,
    )
    report = redactor.redact_with_report("Contact Alice Smith via u/test_account")
    assert fake_client.called is True
    assert report.backend == "cloud_dlp+local"
    assert "Alice Smith" not in report.redacted_text
    assert "u/test_account" not in report.redacted_text


def test_secret_manager_provider_prefers_gcp_then_env_and_caches(monkeypatch) -> None:
    class FakeSmClient:
        def __init__(self) -> None:
            self.calls = 0

        def access_secret_version(self, *, request: dict) -> SimpleNamespace:
            self.calls += 1
            assert request["name"] == "projects/demo-proj/secrets/reddit-client-id/versions/latest"
            return SimpleNamespace(payload=SimpleNamespace(data=b"gcp-secret-value"))

    client = FakeSmClient()
    provider = SecretManagerProvider(project_id="demo-proj", client=client)
    assert provider.get_secret("reddit-client-id", env_fallback="REDDIT_CLIENT_ID") == "gcp-secret-value"
    # Second lookup hits in-memory cache
    assert provider.get_secret("reddit-client-id", env_fallback="REDDIT_CLIENT_ID") == "gcp-secret-value"
    assert client.calls == 1

    # Fallback to environment variable when Secret Manager disabled
    monkeypatch.setenv("TEST_LOCAL_SECRET", "env-dev-val")
    local_provider = SecretManagerProvider(project_id=None, prefer_secret_manager=False)
    assert local_provider.get_secret("missing", env_fallback="TEST_LOCAL_SECRET") == "env-dev-val"

    with pytest.raises(SecretLookupError):
        local_provider.get_secret("missing", env_fallback="DEFINITELY_UNSET_VAR", required=True)


def test_repository_contains_zero_hardcoded_secrets() -> None:
    scanned_dirs = ("app", "deployment", ".github")
    for rel_dir in scanned_dirs:
        base = REPO_ROOT / rel_dir
        for path in base.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in SECRET_PATTERNS:
                assert not pattern.search(text), f"Potential hardcoded secret in {path}"
