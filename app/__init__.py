"""ADK package entrypoint lazily exporting `app` and `root_agent` (PEP 562).

Lazy re-export keeps submodule imports (e.g., `app.config`, `app.security`)
side-effect-free while preserving ADK CLI discovery of `app` and `root_agent`.
"""

from __future__ import annotations

from typing import Any

__all__ = ["app", "root_agent"]


def __getattr__(name: str) -> Any:
    if name in {"app", "root_agent", "memory_consolidator"}:
        from app import agent as agent_module

        return getattr(agent_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

