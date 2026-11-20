"""Secure secret retrieval via Google Cloud Secret Manager with local dev fallback.

Never hardcode API keys, OAuth tokens, or webhook URLs in source code.
In production on GCP, this provider resolves secrets from Secret Manager using
Application Default Credentials (ADC) attached to the Cloud Run service account.
In local development or CI without GCP access, it safely falls back to
explicitly named environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol


class SecretLookupError(RuntimeError):
    """Raised when a required secret cannot be retrieved from any backend."""


class _SecretManagerClientProtocol(Protocol):
    def access_secret_version(self, *, request: dict[str, str]) -> object: ...


@dataclass
class SecretManagerProvider:
    """Retrieves secrets from GCP Secret Manager with in-memory caching.

    Attributes:
        project_id: Target GCP project ID hosting Secret Manager secrets.
        prefer_secret_manager: When True and project_id is configured, query
            GCP Secret Manager before falling back to local environment variables.
        client: Optional injected Secret Manager client for unit testing.
    """

    project_id: str | None = None
    prefer_secret_manager: bool = True
    client: _SecretManagerClientProtocol | None = None
    _cache: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def _get_gcp_client(self) -> _SecretManagerClientProtocol | None:
        if self.client is not None:
            return self.client
        if not self.prefer_secret_manager or not self.project_id:
            return None
        if self.project_id in {"", "your-gcp-project-id", "local-dev"}:
            return None
        try:
            from google.cloud import secretmanager  # type: ignore[import-untyped]

            self.client = secretmanager.SecretManagerServiceClient()
            return self.client
        except Exception:
            return None

    def get_secret(
        self,
        secret_id: str,
        *,
        env_fallback: str | None = None,
        version: str = "latest",
        required: bool = False,
    ) -> str | None:
        """Retrieve a secret value securely without logging its payload.

        Args:
            secret_id: Secret name in Google Cloud Secret Manager.
            env_fallback: Local development environment variable name.
            version: Secret version identifier (defaults to "latest").
            required: If True, raise SecretLookupError when no value is found.

        Returns:
            The resolved secret string, or None when optional and unavailable.
        """
        cache_key = f"{secret_id}:{version}:{env_fallback or ''}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        gcp_client = self._get_gcp_client()
        if gcp_client is not None and self.project_id:
            resource_name = (
                f"projects/{self.project_id}/secrets/{secret_id}/versions/{version}"
            )
            try:
                response = gcp_client.access_secret_version(
                    request={"name": resource_name}
                )
                payload = getattr(response, "payload", None)
                data = getattr(payload, "data", b"")
                value = data.decode("utf-8").strip() if isinstance(data, bytes) else str(data).strip()
                if value:
                    self._cache[cache_key] = value
                    return value
            except Exception:
                # Fall through to local environment fallback for dev/CI resilience.
                pass

        if env_fallback:
            env_val = os.environ.get(env_fallback, "").strip()
            if env_val:
                self._cache[cache_key] = env_val
                return env_val

        if required:
            raise SecretLookupError(
                f"Required secret '{secret_id}' was not found in Secret Manager "
                f"(project={self.project_id!r}) or fallback env var '{env_fallback}'."
            )
        return None

    def clear_cache(self) -> None:
        """Clear cached secret values (useful during key rotation or tests)."""
        self._cache.clear()
