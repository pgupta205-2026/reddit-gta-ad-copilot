"""Active PII redaction via Google Cloud DLP with deterministic local fallback.

Scrubs sensitive data (emails, phone numbers, IP addresses, credit card numbers,
SSNs, API/Bearer tokens, and Reddit user handles) before content reaches
structured logs, traces, or persistent memory stores.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Deterministic redaction patterns used both as a fast pre-pass and as a local
# fallback when Cloud DLP API is disabled or unreachable during local dev/CI.
_PII_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "API_TOKEN",
        re.compile(
            r"\b(?:AIza[0-9A-Za-z\-_]{35}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*)\b"
        ),
        "[REDACTED_TOKEN]",
    ),
    (
        "EMAIL_ADDRESS",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        "CREDIT_CARD_NUMBER",
        re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
        "[REDACTED_CARD]",
    ),
    (
        "US_SOCIAL_SECURITY_NUMBER",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[REDACTED_SSN]",
    ),
    (
        "PHONE_NUMBER",
        re.compile(
            r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]\d{3}[-.\s]\d{4}(?!\w)"
        ),
        "[REDACTED_PHONE]",
    ),
    (
        "IP_ADDRESS",
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
        ),
        "[REDACTED_IP]",
    ),
    (
        "REDDIT_USERNAME",
        re.compile(r"(?<!\w)/?u/[A-Za-z0-9_-]{3,20}\b"),
        "[REDACTED_REDDIT_USER]",
    ),
)

_CLOUD_DLP_INFO_TYPES: tuple[str, ...] = (
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "PERSON_NAME",
    "IP_ADDRESS",
    "CREDIT_CARD_NUMBER",
    "US_SOCIAL_SECURITY_NUMBER",
)


@dataclass(frozen=True)
class RedactionReport:
    """Result returned by PiiRedactor containing scrubbed text and findings."""

    redacted_text: str
    findings_count: int
    info_types_found: tuple[str, ...]
    backend: str


@dataclass
class PiiRedactor:
    """Scrubs PII via Google Cloud Sensitive Data Protection (DLP) or local rules.

    Attributes:
        gcp_project_id: Target GCP project ID for Cloud DLP requests.
        enable_cloud_dlp: When True and gcp_project_id is configured, invoke
            Google Cloud DLP `deidentify_content` before local verification pass.
        dlp_client: Optional injected DLP client for testing.
    """

    gcp_project_id: str | None = None
    enable_cloud_dlp: bool = False
    dlp_client: Any | None = field(default=None, repr=False)

    def _get_dlp_client(self) -> Any | None:
        if self.dlp_client is not None:
            return self.dlp_client
        if not self.enable_cloud_dlp or not self.gcp_project_id:
            return None
        try:
            from google.cloud import dlp_v2  # type: ignore[import-untyped]

            self.dlp_client = dlp_v2.DlpServiceClient()
            return self.dlp_client
        except Exception:
            return None

    def _redact_with_cloud_dlp(self, text: str) -> tuple[str, bool]:
        client = self._get_dlp_client()
        if client is None or not self.gcp_project_id:
            return text, False

        parent = f"projects/{self.gcp_project_id}/locations/global"
        inspect_config = {
            "info_types": [{"name": info_type} for info_type in _CLOUD_DLP_INFO_TYPES],
            "custom_info_types": [
                {
                    "info_type": {"name": "REDDIT_USERNAME"},
                    "regex": {"pattern": r"/?u/[A-Za-z0-9_-]{3,20}"},
                }
            ],
        }
        deidentify_config = {
            "info_type_transformations": {
                "transformations": [
                    {
                        "primitive_transformation": {
                            "replace_with_info_type_config": {}
                        }
                    }
                ]
            }
        }
        try:
            response = client.deidentify_content(
                request={
                    "parent": parent,
                    "deidentify_config": deidentify_config,
                    "inspect_config": inspect_config,
                    "item": {"value": text},
                }
            )
            return str(response.item.value), True
        except Exception:
            return text, False

    def redact_with_report(self, text: str) -> RedactionReport:
        """Scrub PII from text and return detailed redaction telemetry."""
        if not text:
            return RedactionReport(
                redacted_text=text,
                findings_count=0,
                info_types_found=(),
                backend="noop",
            )

        current, used_dlp = self._redact_with_cloud_dlp(text)
        findings_count = 0
        found_types: list[str] = []

        # Always run deterministic regex pass to catch custom handles/tokens and
        # guarantee defense-in-depth even if Cloud DLP is disabled locally.
        for info_type, pattern, replacement in _PII_PATTERNS:
            current, replacements = pattern.subn(replacement, current)
            if replacements > 0:
                findings_count += replacements
                found_types.append(info_type)

        if used_dlp and current != text and findings_count == 0:
            findings_count = 1
            found_types.append("CLOUD_DLP_ENTITY")

        backend = "cloud_dlp+local" if used_dlp else "local_deterministic"
        return RedactionReport(
            redacted_text=current,
            findings_count=findings_count,
            info_types_found=tuple(dict.fromkeys(found_types)),
            backend=backend,
        )

    def redact_text(self, text: str) -> str:
        """Scrub PII from a single string."""
        return self.redact_with_report(text).redacted_text

    def redact_value(self, value: Any) -> Any:
        """Recursively scrub PII from strings, dicts, lists, and tuples."""
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, dict):
            return {str(k): self.redact_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.redact_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self.redact_value(item) for item in value)
        return value
