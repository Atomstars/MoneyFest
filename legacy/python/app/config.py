"""Central configuration for the Stock Impact Explainer (Phase 1).

Everything tunable lives here in one versioned dataclass. Every ``daily_metric``
row stamps ``gate_inputs_json`` with the exact inputs *and* ``config_version`` used,
so any output is reproducible from the row alone.

Bump ``GATE_CONFIG_VERSION`` whenever any threshold below changes. Never mutate a
published config in place -- that would silently break "same inputs + same config
version => byte-identical results".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, asdict, field
from pathlib import Path

# --- Paths -----------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
FACTORS_YAML = DATA_DIR / "factors.yaml"
SECTOR_TEMPLATES_YAML = DATA_DIR / "sector_templates.yaml"

# DB path is overridable via env so tests can point at a temp file / :memory:.
DB_PATH = os.environ.get("STOCK_EXPLAINER_DB", str(ROOT_DIR / "stock_explainer.db"))

# Timezone the whole system reasons in. All "same-day window" logic is IST.
MARKET_TZ = "Asia/Kolkata"

# Tier-3 items first seen after this local time on a move day are suspect-reactive.
SUSPECT_REACTIVE_CUTOFF = "09:30"  # IST, HH:MM

# The benchmark index used for beta / market classification.
INDEX_TICKER = "^NSEI"  # NIFTY 50 on Yahoo Finance
INDEX_FACTOR_ID = "NIFTY50"


# --- The versioned gate config --------------------------------------------

GATE_CONFIG_VERSION = "gate-v1.1.0"  # bumped for the Phase-2 config-module revision


@dataclass(frozen=True)
class GateConfig:
    """Immutable, versioned bundle of every threshold the quant gate uses.

    Frozen so it can be hashed and safely shared; ``version`` is stamped into
    every ``daily_metric.gate_inputs_json``.
    """

    version: str = GATE_CONFIG_VERSION

    # Lookback windows (trading days).
    lookback: int = 60
    min_lookback: int = 40

    # Gate 0 -- sanity.
    sanity_move_threshold: float = 0.15          # |move| > 15% => corp-action check
    winsor_sigma: float = 3.0                     # estimation windows only
    second_source_max_disagreement: float = 0.01  # >1% price disagreement => DATA_ISSUE

    # Gate 1 -- noise.
    noise_sigma_mult: float = 1.0                 # |r| < 1.0 sigma and no T1 => NOISE

    # Gate 2 -- market.
    beta_clamp_low: float = -1.0
    beta_clamp_high: float = 3.0
    market_idio_sigma_mult: float = 1.0           # |idio| < 1.0 sigma_idio => market-explained
    market_index_min_move: float = 0.005          # AND |r_index| >= 0.5%

    # Gate 3 -- dispatch.
    investigate_idio_sigma_mult: float = 1.5      # |idio| >= 1.5 sigma_idio => INVESTIGATE
    mixed_idio_sigma_mult: float = 1.0            # 1.0..1.5 => MIXED

    # Volume context (never changes the gate result).
    vol_z_material: float = 2.0

    def to_json_dict(self) -> dict:
        return asdict(self)


# The single active config instance used across the app.
GATE_CONFIG = GateConfig()


# --- Ingestion / source config --------------------------------------------

# NSE / BSE corporate announcement endpoints (Tier-1).
NSE_ANNOUNCEMENTS_URL = "https://www.nseindia.com/api/corporate-announcements?index=equities"
# BSE announcements live behind AnnSubCategoryGetData. The older AnnGetData path
# returns the HTML landing page (HTTP 200 + text/html), which silently parsed as
# "no announcements" -- that is why Tier-1 ingested zero rows for the whole of Phase 1-4.
BSE_ANNOUNCEMENTS_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_SCRIP_HEADER_URL = "https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w"
BSE_CORP_ACTIONS_URL = "https://api.bseindia.com/BseIndiaAPI/api/CorpactCategory/w"

# A polite default header set; NSE in particular rejects bare clients.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# api.bseindia.com serves JSON only when the request looks like it came from the
# site itself; without these it returns the HTML landing page with a 200.
BSE_HTTP_HEADERS = {
    **HTTP_HEADERS,
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
}

# Tier-3 RSS feeds (business press). Small, curated set.
NEWS_RSS_FEEDS: list[str] = [
    "https://www.moneycontrol.com/rss/business.xml",
    "https://www.business-standard.com/rss/markets-106.rss",
    "https://www.livemint.com/rss/markets",
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
]

# EOD scheduler: weekdays, IST.
EOD_HOUR = 18
EOD_MINUTE = 30


# --- Phase 2: reasoning layer config --------------------------------------

ATTRIBUTION_CONFIG_VERSION = "attrib-v1.0.0"

# Master switch: the daily loop only runs the reasoning layer when this is true.
# Default False until Phase-2 acceptance passes. Overridable via env.
ATTRIBUTION_ENABLED = os.environ.get("ATTRIBUTION_ENABLED", "false").lower() == "true"

# Which LLM backend app/llm.py talks to. "groq" (free tier, OpenAI-compatible,
# api.groq.com) or "anthropic" (paid, forced-tool-use via the anthropic SDK).
# Defaults to groq -- this project has no Anthropic budget. Switch back at any time
# by setting LLM_PROVIDER=anthropic (and ANTHROPIC_API_KEY) with no code changes.
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").strip().lower()

# Exactly two LLM calls per pending bundle. Defaults depend on the provider; override
# either independently via env if you want a different model on the same provider.
_MODEL_DEFAULTS = {
    "groq": {
        # Both the agent and the narrow verifier default to the same 70B model:
        # the verifier's job (entailment-checking each claim against its cited
        # evidence) is where a weaker model most directly weakens the whole
        # reliability story, so this is not the place to reach for a smaller/
        # faster model without first validating it against the golden set.
        "attribution": "llama-3.3-70b-versatile",
        "verifier": "llama-3.3-70b-versatile",
    },
    "anthropic": {
        "attribution": "claude-opus-4-8",
        "verifier": "claude-sonnet-5",
    },
}
_model_defaults = _MODEL_DEFAULTS.get(LLM_PROVIDER, _MODEL_DEFAULTS["anthropic"])

ATTRIBUTION_MODEL = os.environ.get("ATTRIBUTION_MODEL", _model_defaults["attribution"])
VERIFIER_MODEL = os.environ.get("VERIFIER_MODEL", _model_defaults["verifier"])
AGENT_PROMPT_VERSION = "v1"

# How many drivers to render in ATTRIBUTED output.
MAX_RENDERED_DRIVERS = 3

# --- Phase 3: delivery layer config ---------------------------------------

DELIVERY_CONFIG_VERSION = "delivery-v1.0.0"

# Fixed disclaimer, appended at delivery time (never stored, never advice).
DISCLAIMER = "Explanation only — not investment advice."

# Default user preferences (stored per-user in user.prefs_json).
MIN_ALERT_LEVELS = ("ALL", "EXPLAINED_ONLY", "HIGH_ONLY")
DEFAULT_PREFS = {
    "min_alert_level": "ALL",     # ALL | EXPLAINED_ONLY | HIGH_ONLY
    "quiet_market_days": False,    # True suppresses MARKET-outcome alerts
    "daily_digest": False,
}

# Telegram Bot API. Token ONLY from env; never stored, never logged.
TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_MESSAGE_LIMIT = 4096      # hard Telegram per-message character cap
TELEGRAM_POLL_TIMEOUT = 25         # long-poll seconds for getUpdates

# Data-sanity / index-fetch retry policy for the hardened EOD job.
INDEX_FETCH_RETRIES = 2
INDEX_FETCH_BACKOFF_SEC = 3

# Hand-maintained data files.
SECTOR_MAP_YAML = DATA_DIR / "sector_map.yaml"
NSE_HOLIDAYS_YAML = DATA_DIR / "nse_holidays.yaml"
BSE_SCRIP_MAP_YAML = DATA_DIR / "bse_scrip_map.yaml"

# API bind address (localhost only, no auth in this phase).
API_HOST = "127.0.0.1"
API_PORT = 8000


# --- Phase 4: web UI config -----------------------------------------------

WEB_CONFIG_VERSION = "web-v1.0.0"

# Single shared login token (a seatbelt for a localhost product, not a fortress).
# Read only from env; if unset, the UI runs in an explicit dev-open mode with a warning.
WEB_TOKEN = os.environ.get("WEB_TOKEN")
WEB_COOKIE_NAME = "sa_session"
WEB_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

# History strip / ops windows.
HISTORY_DAYS = 30
OUTCOMES_WINDOW_DAYS = 90
NO_DRIVER_ZERO_WINDOW = 30  # trailing eventful days for the "rubric bar too low" callout


# Event-class keyword map for the rubric's "direction-unambiguous" HIGH gate.
# Keys are event classes; values are lowercase keyword fragments matched on the
# Tier-1 headline/body. Presence of any keyword => the item is a recognised,
# direction-unambiguous event class.
EVENT_KEYWORDS: dict[str, list[str]] = {
    "results": ["results", "profit", "net profit", "revenue", "earnings", "quarterly",
                "q1 ", "q2 ", "q3 ", "q4 ", "beat estimates", "miss estimates"],
    "order_win": ["order", "contract", "bags order", "order win", "won a", "awarded",
                  "purchase order", "loi", "letter of intent"],
    "regulatory": ["approval", "approved", "rejected", "clearance", "usfda", "fda",
                   "licence", "license", "sebi", "cci", "regulatory", "sanction"],
    "mgmt_change": ["resignation", "resigns", "appointed", "appointment", "steps down",
                    "ceo", "cfo", "managing director", "board change"],
    "ratings": ["rating", "upgrade", "downgrade", "outlook", "crisil", "icra",
                "moody", "s&p", "fitch"],
}
