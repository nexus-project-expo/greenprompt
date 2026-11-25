import time

import pytest

from greenprompt import config, energy
from greenprompt.energy import CallEnergy, PowerSampler, compute_receipt

LARGE = energy.FACTORS["models"]["openai/gpt-oss-120b"]


@pytest.fixture(autouse=True)
def grid(monkeypatch):
    monkeypatch.setattr(config, "GRID_EF_G_PER_KWH", 675.0)
    monkeypatch.setattr(config, "CPU_ASSUMED_W", 15.0)


def test_every_factor_has_a_source():
    for name, f in energy.FACTORS["models"].items():
        assert f["source"] and f["label"], name
        assert f["low"] <= f["wh_per_prompt"] <= f["high"], name
    assert "Central Electricity Authority" in energy.FACTORS["grid"]["source"]


def test_sampler_integrates_power_above_idle():
    readings = iter([60.0] * 1000)
    with PowerSampler(interval_s=0.01, reader=lambda: next(readings), idle_w=20.0) as s:
        time.sleep(0.2)
    assert s.available
    assert s.joules_above_idle == pytest.approx(40.0 * s.duration_s)
    assert len(s.trace) >= 5 and energy.ACTIVE is None


def test_sampler_tail_extends_measurement():
    with PowerSampler(interval_s=0.01, reader=lambda: 50.0, idle_w=20.0) as s:
        s.tail_s = 0.1
    assert s.duration_s >= 0.1 and s.joules_above_idle == pytest.approx(30.0 * s.duration_s)


def test_sampler_never_counts_below_idle():
    with PowerSampler(interval_s=0.01, reader=lambda: 10.0, idle_w=20.0) as s:
        time.sleep(0.05)
    assert s.joules_above_idle == 0.0


def test_sampler_without_gpu_is_unavailable():
    with PowerSampler(interval_s=0.01, reader=lambda: None, idle_w=20.0) as s:
        time.sleep(0.03)
    assert not s.available and s.joules_above_idle == 0.0


def test_local_measured_receipt():
    r = compute_receipt("small", [CallEnergy("qwen2.5:3b", "ollama", "small", 36.0)], overhead_s=0.024, latency_s=0.5)
    assert r.measured
    assert r.wh == pytest.approx(36 / 3600 + 15 * 0.024 / 3600)
    assert r.wh_low == r.wh == r.wh_high
    assert r.ml_water == 0.0
    assert r.g_co2 == pytest.approx(r.wh / 1000 * 675)
    assert r.baseline_wh == LARGE["wh_per_prompt"] and r.saved_wh == pytest.approx(r.baseline_wh - r.wh)
    assert any("measured" in s for s in r.sources)


def test_cloud_large_receipt_is_estimated_with_range():
    r = compute_receipt("large", [CallEnergy("openai/gpt-oss-120b", "cloud", "large", None)], 0.0, 1.0)
    assert not r.measured
    assert (r.wh, r.wh_low, r.wh_high) == (LARGE["wh_per_prompt"], LARGE["low"], LARGE["high"])
    assert r.ml_water == LARGE["ml_water_per_prompt"] and r.saved_wh == 0.0
    assert "location unknown" in r.grid_note


def test_escalation_counts_both_calls():
    calls = [CallEnergy("qwen2.5:3b", "ollama", "small", 18.0), CallEnergy("openai/gpt-oss-120b", "cloud", "large", None)]
    r = compute_receipt("small+large", calls, 0.0, 2.0)
    assert r.escalated and not r.measured
    assert r.wh == pytest.approx(18 / 3600 + LARGE["wh_per_prompt"])
    assert r.saved_wh < 0  # escalation costs more than going straight to large, and we show it


def test_cache_hit_costs_only_overhead():
    r = compute_receipt("cache", [], overhead_s=0.03, latency_s=0.03)
    assert 0 < r.wh < 0.001 and r.saved_pct > 99


def test_unknown_cloud_model_uses_tier_default():
    r = compute_receipt("large", [CallEnergy("some-new-model", "cloud", "large", None)], 0.0, 1.0)
    assert r.wh == LARGE["wh_per_prompt"]


def test_missing_grid_factor_is_labelled(monkeypatch):
    monkeypatch.setattr(config, "GRID_EF_G_PER_KWH", 0.0)
    r = compute_receipt("cache", [], 0.01, 0.01)
    assert r.g_co2 == 0 and r.grid_note == "grid factor not set"


@pytest.mark.parametrize("idle,limit,util,busy", [
    (13.0, 95.0, 30.0, False),   # browser open: high utilisation at idle clocks, low power
    (88.0, 95.0, 29.0, True),    # a game running
    (9.6, None, 30.0, False),    # on battery the limit is hidden: judge by idle watts, not utilisation
    (60.0, None, 30.0, True),    # no limit, but a game is drawing power
    (None, None, 30.0, True),    # no power reading at all: fall back to utilisation
    (None, None, 2.0, False),
])
def test_gpu_busy_uses_idle_power(monkeypatch, idle, limit, util, busy):
    monkeypatch.setattr(energy, "IDLE_W", idle)
    monkeypatch.setattr(energy, "POWER_LIMIT_W", limit)
    monkeypatch.setattr(energy, "IDLE_UTIL_PCT", util)
    assert energy.gpu_busy() is busy
