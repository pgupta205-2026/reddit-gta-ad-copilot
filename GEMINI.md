# GEMINI.md — Developer Guidance for `reddit-gta-ad-copilot`

## Project Conventions
- **Agent Directory:** `app/` (`App(name="app", root_agent=root_agent)` must always match the directory name).
- **Model Routing:** Preserve the dual-tier routing in `app/config.py` (`COPILOT_FAST_MODEL` for scouts/self-eval/compaction, `COPILOT_REASONING_MODEL` for coordinator/strategist).
- **Logging:** Never use bare `print()` inside `app/`. Always use `get_logger(__name__)` from `app.observability.logging`.
- **PII Hygiene:** Never log or persist unredacted user content. Route all raw strings through `PiiRedactor.redact_text()` or `PiiRedactor.redact_mapping()`.
- **Secrets:** Never hardcode credentials or tokens. Always retrieve via `SecretManagerProvider.get_secret()`.
- **HITL Safety:** Keep `require_confirmation=True` and `tool_context.request_confirmation(...)` on `issue_campaign_pause_recommendation` and `dispatch_advertiser_pitch_brief`.
- **Testing vs Evaluation:** Use `pytest` (`tests/unit`, `tests/integration`) for deterministic code contracts, schemas, redaction, HITL gates, and observability. Use `adk eval` / `agents-cli eval run` (`tests/eval/evalsets/`) for LLM behavioral evaluation.
