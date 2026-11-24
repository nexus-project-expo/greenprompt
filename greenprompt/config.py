"""All settings and thresholds. The only module that reads .env."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _s(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def _f(name: str, default: float) -> float:
    v = _s(name)
    return float(v) if v else default


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    model: str
    api_key: str
    backend: str  # "ollama" | "cloud"


SMALL_BACKEND = _s("SMALL_BACKEND", "ollama")
OLLAMA = Endpoint(_s("SMALL_BASE_URL", "http://127.0.0.1:11434/v1"), _s("SMALL_MODEL", "qwen2.5:3b"),
                  _s("SMALL_API_KEY", "ollama"), "ollama")
CLOUD_SMALL = Endpoint(_s("CLOUD_SMALL_BASE_URL"), _s("CLOUD_SMALL_MODEL"), _s("CLOUD_SMALL_API_KEY"), "cloud")
LARGE = Endpoint(_s("LARGE_BASE_URL"), _s("LARGE_MODEL"), _s("LARGE_API_KEY"), "cloud")
LARGE_FALLBACK = Endpoint(_s("LARGE_FALLBACK_BASE_URL"), _s("LARGE_FALLBACK_MODEL"), _s("LARGE_FALLBACK_API_KEY"), "cloud")
JUDGE = Endpoint(_s("JUDGE_BASE_URL"), _s("JUDGE_MODEL"), _s("JUDGE_API_KEY"), "cloud")


def endpoints(tier: str) -> list[Endpoint]:
    """Endpoints to try for a tier, in order. Unconfigured ones (no model) are skipped."""
    if tier == "small":
        eps = [OLLAMA, CLOUD_SMALL] if SMALL_BACKEND == "ollama" else [CLOUD_SMALL]
    elif tier == "large":
        eps = [LARGE, LARGE_FALLBACK]
    elif tier == "judge":
        eps = [JUDGE, LARGE]
    else:
        raise ValueError(f"unknown tier {tier!r}")
    return [e for e in eps if e.model and e.base_url]


REQUEST_TIMEOUT_S = _f("REQUEST_TIMEOUT_S", 30)
CACHE_SIM_THRESHOLD = _f("CACHE_SIM_THRESHOLD", 0.92)
CACHE_TTL_HOURS = _f("CACHE_TTL_HOURS", 24)
ROUTER_HARD_THRESHOLD = _f("ROUTER_HARD_THRESHOLD", 0.5)
ROUTER_UNSURE_BAND = _f("ROUTER_UNSURE_BAND", 0.10)
GRID_EF_G_PER_KWH = _f("GRID_EF_G_PER_KWH", 0.0)  # 0 = not set; energy.py must label CO2 as unavailable
CPU_ASSUMED_W = _f("CPU_ASSUMED_W", 15)

DATA_DIR = ROOT / "data"
RESULTS_DIR = ROOT / "results"
DB_PATH = Path(_s("DB_PATH", str(ROOT / "greenprompt.db")))
