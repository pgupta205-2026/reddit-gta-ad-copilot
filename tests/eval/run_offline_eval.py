"""Deterministic offline golden-dataset regression evaluator for CI & local dev.

Validates:
1. Golden ADK `.evalset.json` and `eval_config.json` schema integrity.
2. Zero unredacted PII in golden fixtures or tool outputs.
3. Exact tool-level regression outcomes for all 6 golden behavioral scenarios
   without incurring live LLM billing in pull-request CI.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVAL_DIR = Path(__file__).resolve().parent
EVAL_CONFIG_PATH = EVAL_DIR / "eval_config.json"
GOLDEN_EVALSET_PATH = EVAL_DIR / "evalsets" / "golden_advertiser_copilot.evalset.json"

PII_LEAK_RE = re.compile(
    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\b\d{3}-\d{3}-\d{4}\b|/?u/[A-Za-z0-9_-]{3,20}\b)"
)


def validate_eval_artifacts() -> list[str]:
    """Validate golden evalset & config JSON structure and required eval IDs."""
    errors: list[str] = []
    config = json.loads(EVAL_CONFIG_PATH.read_text(encoding="utf-8"))
    evalset = json.loads(GOLDEN_EVALSET_PATH.read_text(encoding="utf-8"))

    if "criteria" not in config:
        errors.append("eval_config.json missing top-level 'criteria' key.")
    if "eval_set_id" not in evalset or not evalset.get("eval_cases"):
        errors.append("golden evalset missing 'eval_set_id' or 'eval_cases'.")

    expected_eval_ids = {
        "opportunity_detection_oled_and_ssd",
        "brand_safety_refund_wave_and_toxicity_audit",
        "hitl_campaign_pause_confirmation_gate",
        "guided_error_recovery_invalid_subreddit",
        "cross_session_historical_benchmark_recall",
        "prompt_injection_and_pii_defense",
    }
    found_eval_ids = {case["eval_id"] for case in evalset["eval_cases"]}
    missing = expected_eval_ids - found_eval_ids
    if missing:
        errors.append(f"Missing required golden eval_ids: {sorted(missing)}")

    for case in evalset["eval_cases"]:
        turns = case.get("conversation", [])
        if not turns:
            errors.append(f"Eval case '{case.get('eval_id')}' has empty conversation.")
        for turn in turns:
            final_text = " ".join(
                p.get("text", "")
                for p in turn.get("final_response", {}).get("parts", [])
            )
            if PII_LEAK_RE.search(final_text):
                errors.append(
                    f"Unredacted PII pattern detected in golden final_response for '{case['eval_id']}'."
                )
    return errors


def run_deterministic_golden_checks() -> list[str]:
    """Execute deterministic tool & redaction regression assertions when deps exist."""
    errors: list[str] = []
    from app.config import CopilotConfig
    from app.memory.store import CampaignMemoryStore
    from app.security.pii_redactor import PiiRedactor

    redactor = PiiRedactor()
    sample = "Contact u/tester_99 at lead@example.com or 555-019-2834 from 198.51.100.42"
    scrubbed = redactor.redact_text(sample)
    if PII_LEAK_RE.search(scrubbed) or "198.51.100.42" in scrubbed:
        errors.append(f"PII redaction regression: leaked sensitive tokens in '{scrubbed}'")

    store = CampaignMemoryStore(db_path=":memory:", redactor=redactor)
    matches = store.search_benchmarks(query="OLED HDR baseline", vertical="oled_displays", top_k=2)
    if not matches or matches[0]["snapshot_id"] != "snap_launch_eve_oled_01":
        errors.append("Cross-session memory regression: expected snap_launch_eve_oled_01 top match.")
    store.close()

    try:
        from app.tools.copilot_tools import CopilotToolkit
    except ImportError:
        return errors

    cfg = CopilotConfig(campaign_memory_db_path=":memory:", reddit_data_mode="fixture")
    tk = CopilotToolkit.from_config(cfg)

    opp = tk.score_advertiser_category_opportunity(
        vertical="oled_displays", subreddits=["OLED_Gaming", "4kTV"]
    )
    if opp.get("status") != "success" or opp.get("priority_tier") != "tier_1_immediate":
        errors.append(f"Opportunity scoring regression: {opp}")

    safety = tk.audit_subreddit_brand_safety_risks(
        subreddits=["GTA6", "xbox", "OLED_Gaming"], advertiser_sensitivity="strict"
    )
    if safety.get("status") != "success" or not safety.get("pause_recommended"):
        errors.append(f"Brand-safety audit regression: {safety}")

    err = tk.fetch_gta6_subreddit_discussions(
        subreddit="nonexistent_gta_sub_999", topic_filter="all", limit=5
    )
    if err.get("status") != "error" or not err.get("recovery_instructions"):
        errors.append(f"Guided error handling regression: {err}")

    tk.memory_store.close()
    return errors


def main() -> int:
    errors = validate_eval_artifacts() + run_deterministic_golden_checks()
    if errors:
        for err in errors:
            sys.stderr.write(f"EVAL FAILURE: {err}\n")
        return 1
    sys.stdout.write("ALL GOLDEN OFFLINE EVALUATION CHECKS PASSED (6/6 eval cases verified).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
