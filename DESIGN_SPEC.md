# DESIGN_SPEC.md — Reddit Gaming Advertiser & Brand-Safety Copilot (`reddit-gta-ad-copilot`)

## 1. Overview
**Problem:** During the launch week of *Grand Theft Auto VI* (released November 19, 2026 on PS5 and Xbox Series X|S), Reddit gaming and adjacent consumer-tech communities (`r/GTA6`, `r/gaming`, `r/PS5`, `r/xbox`, `r/OLED_Gaming`, `r/4kTV`, `r/buildapc`) experience extreme conversational velocity. A Reddit Account Lead managing gaming, hardware, and CPG advertisers cannot manually monitor thousands of threads to identify high-intent ad placement opportunities (such as OLED displays for night-time lighting or NVMe SSDs for the ~212 GB install) while simultaneously detecting GARM brand-safety risks (refund waves, game-breaking bug outrage, or toxic threads).

**Solution:** `reddit-gta-ad-copilot` is a production-ready multi-agent **Google ADK (Python)** copilot engineered for **Cloud Run** and **GitHub Actions CI/CD** with full **Terraform IaC**. It combines:
1. Live/sanctioned Reddit Data API ingestion (secrets managed via GCP Secret Manager) with a realistic deterministic GTA VI launch dataset fallback for offline testing and CI.
2. Parallel specialist analysis (`AdvertiserOpportunityScout` + `BrandSafetyAuditor` on `gemini-2.5-flash`) feeding strategic synthesis (`CampaignStrategistAgent` on `gemini-2.5-pro`) and automated self-evaluation (`SelfEvalGuardrailAgent` with strict Pydantic `output_schema`).
3. Persistent session & campaign benchmark memory (`DatabaseSessionService` + `CampaignMemoryStore` / `VertexAiMemoryBankService`), ADK history compaction (`EventsCompactionConfig` + `ContextCacheConfig`), and non-blocking async background memory consolidation.
4. Defense-in-depth safety & observability: ADK `BasePlugin` policy guardrails (with Google Cloud Model Armor hook), explicit **Human-in-the-Loop (HITL)** confirmation gates (`ToolConfirmation` / `request_confirmation`), **Cloud DLP PII redaction** (with deterministic local fallback), **structured JSON intent-vs-outcome logging**, and **OpenTelemetry distributed tracing** (`CloudTraceSpanExporter` + `otel_to_cloud=True`).

---

## 2. Architecture & Multi-Agent Pattern

```text
User Query (Account Lead)
   │
   ▼
[ADK App + Global Plugins]
   ├── PolicyGuardrailPlugin (Prompt injection, Model Armor hook, schema/domain policy, PII output check)
   ├── ObservabilityIntentOutcomePlugin (Structured JSON intent-before / outcome-after + OTel spans)
   ├── EventsCompactionConfig (LlmEventSummarizer sliding-window + token threshold compaction)
   └── ContextCacheConfig (Google Cloud context caching)
   │
   ▼
AccountCopilotCoordinator (LlmAgent · gemini-2.5-pro)
   ├── retrieve_historical_campaign_benchmarks (Persistent DB / Memory Bank recall)
   └── StrategyAndVerificationPipeline (SequentialAgent)
         ├── 1. ParallelMarketResearchSquad (ParallelAgent)
         │     ├── AdvertiserOpportunityScout (LlmAgent · gemini-2.5-flash, output_key="opportunity_findings")
         │     │     └── Tools: fetch_gta6_subreddit_discussions, score_advertiser_category_opportunity
         │     └── BrandSafetyAuditor (LlmAgent · gemini-2.5-flash, output_key="brand_safety_findings")
         │           └── Tools: fetch_gta6_subreddit_discussions, audit_subreddit_brand_safety_risks
         ├── 2. CampaignStrategistAgent (LlmAgent · gemini-2.5-pro, output_key="strategy_draft")
         │     └── HITL-Gated Tools (ADK ToolConfirmation / request_confirmation):
         │           ├── issue_campaign_pause_recommendation
         │           └── dispatch_advertiser_pitch_brief
         └── 3. SelfEvalGuardrailAgent (LlmAgent · gemini-2.5-flash, output_schema=SelfEvalVerdict)
               └── Evaluates citations, policy adherence, and zero PII leakage

Async Background Task (after_run_callback):
   └── AsyncMemoryConsolidator → PiiRedactor (Cloud DLP / local) → Persistent Campaign Memory Store
```

---

## 3. Tools Required

| Tool Name | Purpose | Auth / Source | HITL Confirmation |
| --- | --- | --- | --- |
| `fetch_gta6_subreddit_discussions` | Fetches GTA VI launch posts & top comments from targeted subreddits with rate-limit guidance. | Reddit OAuth via GCP Secret Manager (deterministic local fixture fallback). | No |
| `score_advertiser_category_opportunity` | Scores purchase intent, engagement velocity, and placement fit per vertical (`oled_displays`, `ssd_storage`, `console_hardware`, `gaming_peripherals`, `cpg_beverages`). | Deterministic scoring engine over fetched discussions. | No |
| `audit_subreddit_brand_safety_risks` | Classifies GARM brand-safety risk tiers (refund waves, toxicity, bug outrage, sensitive content) with cited thread IDs. | Deterministic GARM audit rules over fetched discussions. | No |
| `retrieve_historical_campaign_benchmarks` | Queries persistent session/campaign memory for historical launch baselines and sentiment deltas. | SQLite (dev) / Cloud SQL + Vertex AI Memory Bank (GCP). | No |
| `issue_campaign_pause_recommendation` | Dispatches a structured brand-safety campaign pause alert to an account webhook/audit sink. | Webhook URL via GCP Secret Manager. | **Required (ADK HITL)** |
| `dispatch_advertiser_pitch_brief` | Publishes an executive advertiser pitch brief with verified citations. | Destination config via GCP Secret Manager. | **Required (ADK HITL)** |

---

## 4. Constraints & Safety Rules
1. **Strict Public-Repo Hygiene:** Zero hardcoded secrets, zero proprietary/internal account contracts, zero raw personal data.
2. **Mandatory HITL Gates:** High-stakes actions (`issue_campaign_pause_recommendation`, `dispatch_advertiser_pitch_brief`) must pause for explicit human approval via ADK `ToolConfirmation`.
3. **Active PII Redaction:** All logs and persisted memory entries pass through `PiiRedactor` (Cloud DLP + deterministic regex fallback) scrubbing emails, phone numbers, IP addresses, API tokens, credit cards, and Reddit `u/` handles.
4. **Grounded Citations Only:** Recommendations must reference concrete subreddit thread IDs returned by tools.
5. **Prompt Injection Defense:** `PolicyGuardrailPlugin` intercepts adversarial override attempts before LLM invocation.

---

## 5. Success Criteria & Reference Samples
* **Unit & Contract Suite (`pytest`):** Validates Pydantic schemas, guided error recovery, PII redaction, HITL pause/approve/reject lifecycle, intent-vs-outcome structured JSON logging, OpenTelemetry spans, async memory consolidation, secret management, and zero leaked secrets.
* **Behavioral Evaluation Suite (`tests/eval/`):** ADK golden `.evalset.json` cases with dedicated `eval_id` per behavioral criterion and `eval_config.json` thresholds.
* **Reference Samples Applied (`google/adk-samples`):** `safety-plugins` (Model Armor + Agent-as-a-Judge `BasePlugin`), `memory-bank` (cross-session memory consolidation & recall), `deep-search` (parallel grounded research with citations).
