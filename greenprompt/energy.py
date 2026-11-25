"""GPU power sampling and the carbon receipt maths. See docs/ENERGY_METHODOLOGY.md."""
import json
import statistics
import subprocess
import threading
import time
from dataclasses import dataclass, field

from greenprompt import config

FACTORS = json.loads((config.DATA_DIR / "energy_factors.json").read_text(encoding="utf-8"))


# ---------- power sampling ----------

def _nvml_reader():
    import pynvml

    pynvml.nvmlInit()
    h = pynvml.nvmlDeviceGetHandleByIndex(0)
    return lambda: pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0  # milliwatts -> watts


def _smi_read() -> float:
    out = subprocess.run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True, timeout=3).stdout
    return float(out.splitlines()[0])


def _make_reader():
    for make in (_nvml_reader, lambda: _smi_read):
        try:
            read = make()
            read()
            return read
        except Exception:
            continue
    return None


_reader = None
_reader_checked = False
IDLE_W: float | None = None  # measured once at startup by measure_idle()
IDLE_UTIL_PCT: float | None = None  # GPU utilisation while idle, for information
POWER_LIMIT_W: float | None = None
# "Idle" above a quarter of the power limit means another app (a game) is drawing power, so "above idle"
# is meaningless. Utilisation is no good for this: at idle clocks a browser alone reads 20-30%.
BUSY_POWER_FRACTION = 0.25
BUSY_UTIL_PCT = 10.0  # fallback only, when the power limit can't be read


def read_power_limit() -> float | None:
    try:
        import pynvml

        pynvml.nvmlInit()
        return pynvml.nvmlDeviceGetEnforcedPowerLimit(pynvml.nvmlDeviceGetHandleByIndex(0)) / 1000.0
    except Exception:
        return None


def gpu_busy() -> bool:
    if IDLE_W is not None and POWER_LIMIT_W:
        return IDLE_W > BUSY_POWER_FRACTION * POWER_LIMIT_W
    if IDLE_W is not None:  # on battery the driver hides the limit; utilisation then misreads a browser as busy
        return IDLE_W > BUSY_IDLE_W
    return IDLE_UTIL_PCT is not None and IDLE_UTIL_PCT > BUSY_UTIL_PCT


BUSY_IDLE_W = 30.0  # no power limit known: an "idle" draw above this means a game or video is running


def read_util() -> float | None:
    try:
        import pynvml

        pynvml.nvmlInit()
        return float(pynvml.nvmlDeviceGetUtilizationRates(pynvml.nvmlDeviceGetHandleByIndex(0)).gpu)
    except Exception:
        return None


def read_watts() -> float | None:
    global _reader, _reader_checked
    if not _reader_checked:
        _reader, _reader_checked = _make_reader(), True
    try:
        return _reader() if _reader else None
    except Exception:
        return None


def measure_idle(seconds: float = 3.0, settle_s: float = 6.0) -> float | None:
    """Average GPU power with nothing generating. Call after the local model is loaded.
    Waits `settle_s` first: the GPU stays in a high power state for ~4 s after generating."""
    global IDLE_W, IDLE_UTIL_PCT, POWER_LIMIT_W
    POWER_LIMIT_W = read_power_limit()
    time.sleep(settle_s)
    samples, utils = [], []
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        w, u = read_watts(), read_util()
        if w is not None:
            samples.append(w)
        if u is not None:
            utils.append(u)
        time.sleep(0.1)
    IDLE_W = statistics.mean(samples) if samples else None
    IDLE_UTIL_PCT = statistics.mean(utils) if utils else None
    return IDLE_W


ACTIVE: "PowerSampler | None" = None  # the sampler currently running, read by the live power stream


class PowerSampler:
    """Polls GPU power in a thread while a local model generates.

    Energy = mean(power above idle) x duration. The driver smooths readings over about a second,
    so the reading lags the real draw; set `tail_s` (~1 s) to keep sampling after the answer ends.
    """

    def __init__(self, interval_s: float = 0.1, reader=read_watts, idle_w: float | None = None):
        self.interval_s, self._read = interval_s, reader
        self.tail_s = 0.0
        self.idle_w = IDLE_W if idle_w is None else idle_w
        self.trace: list[tuple[float, float]] = []  # (seconds since start, watts)
        self.joules_above_idle = 0.0
        self.available = False
        self._stop = threading.Event()

    def _sample(self):
        w = self._read()
        if w is not None:
            self.trace.append((time.perf_counter() - self._t0, w))

    def _loop(self):
        while not self._stop.wait(self.interval_s):
            self._sample()

    def __enter__(self):
        global ACTIVE
        self._t0 = time.perf_counter()
        self._sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        ACTIVE = self
        return self

    def __exit__(self, *exc):
        global ACTIVE
        if self.tail_s:
            time.sleep(self.tail_s)
        self._stop.set()
        self._thread.join(timeout=1)
        self._sample()
        self.duration_s = time.perf_counter() - self._t0
        ACTIVE = None
        self.available = bool(self.trace) and self.idle_w is not None
        if self.available:
            excess = statistics.mean(max(0.0, w - self.idle_w) for _, w in self.trace)
            self.joules_above_idle = excess * self.duration_s
        return False


# ---------- receipt ----------

@dataclass
class CallEnergy:
    model: str
    backend: str               # "ollama" | "cloud"
    tier: str                  # "small" | "large"
    joules: float | None       # measured joules above idle, None if not measured


@dataclass
class Receipt:
    tier: str                  # cache | small | large | small+large
    wh: float
    wh_low: float
    wh_high: float
    g_co2: float
    ml_water: float
    baseline_wh: float         # estimated energy if the large model had answered directly
    saved_wh: float
    measured: bool             # True only when the model energy was measured on the local GPU
    sources: list[str]
    latency_s: float
    model: str = ""
    escalated: bool = False
    overhead_wh: float = 0.0
    baseline_g_co2: float = 0.0
    baseline_ml_water: float = 0.0
    grid_note: str = ""
    idle_w: float | None = None
    power_trace: list = field(default_factory=list)

    @property
    def saved_pct(self) -> float:
        return 100 * self.saved_wh / self.baseline_wh if self.baseline_wh else 0.0


def model_factor(model: str, tier: str) -> dict:
    """Per-prompt estimate for a cloud model; unknown models use the tier default."""
    return FACTORS["models"].get(model) or FACTORS["models"][FACTORS["default"]["large" if tier == "large" else "small"]]


def _g_co2(wh: float) -> float:
    return wh / 1000 * config.GRID_EF_G_PER_KWH


def compute_receipt(tier: str, calls: list[CallEnergy], overhead_s: float, latency_s: float,
                    model: str = "", power_trace: list | None = None) -> Receipt:
    overhead_wh = config.CPU_ASSUMED_W * overhead_s / 3600
    wh = low = high = overhead_wh
    water = 0.0
    sources = [f"Overhead: {FACTORS['cpu_overhead']['source']}"]
    measured_any = cloud_any = False
    for c in calls:
        if c.joules is not None:
            w = c.joules / 3600
            wh, low, high = wh + w, low + w, high + w
            measured_any = True
        else:
            f = model_factor(c.model, c.tier)
            wh, low, high = wh + f["wh_per_prompt"], low + f["low"], high + f["high"]
            water += f["ml_water_per_prompt"]
            cloud_any = True
            src = f"{c.model}: {f['label']}. {f['source']}"
            if src not in sources:
                sources.append(src)
    if measured_any:
        sources.append("Local model: measured GPU power above idle (NVML), GPU only")

    base = model_factor(FACTORS["default"]["large"], "large")
    baseline_wh = base["wh_per_prompt"]
    if not any(base["source"] in s for s in sources):
        sources.append(f"Baseline (all-large): {base['label']}. {base['source']}")
    sources.append(f"CO2: {FACTORS['grid']['source']}")

    if not config.GRID_EF_G_PER_KWH:
        grid_note = "grid factor not set"
    elif cloud_any:
        grid_note = "India grid factor applied; cloud data-centre location unknown"
    else:
        grid_note = "India grid (CEA v22.0)"

    return Receipt(
        tier=tier, wh=wh, wh_low=low, wh_high=high, g_co2=_g_co2(wh), ml_water=water,
        baseline_wh=baseline_wh, saved_wh=baseline_wh - wh, measured=measured_any and not cloud_any,
        sources=sources, latency_s=latency_s, model=model, escalated=tier == "small+large",
        overhead_wh=overhead_wh, baseline_g_co2=_g_co2(baseline_wh), baseline_ml_water=base["ml_water_per_prompt"],
        grid_note=grid_note, idle_w=IDLE_W, power_trace=power_trace or [])
