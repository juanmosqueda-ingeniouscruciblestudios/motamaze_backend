"""Unit tests for level_stats_service — T-447 ST-04. Dummy win-rate numbers
here are test fixtures only; see docs/DATA_MODEL.md#level_stats for why
production level_stats stays empty (guards fail closed) until real T-203
simulation or measured BigQuery data exists."""

from app.services import bq_streaming, level_stats_service


async def test_recalc_writes_levels_above_sample_threshold(fake_db, monkeypatch):
    async def _fake_run_select(query, params):
        return [
            {"level_id": 1, "wins": 80, "attempts": 100},
            {"level_id": 2, "wins": 20, "attempts": 100},
        ]

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    result = await level_stats_service.recalc_level_stats(fake_db, "proj", "ds")

    assert result == {"updated": ["1", "2"], "skipped_low_sample": []}
    level_1 = fake_db._collections["level_stats"]["1"]
    assert level_1["win_rate"] == 80.0
    assert level_1["source"] == "measured"
    assert level_1["sample_size"] == 100

    level_2 = fake_db._collections["level_stats"]["2"]
    assert level_2["win_rate"] == 20.0


async def test_recalc_skips_levels_below_sample_threshold(fake_db, monkeypatch):
    async def _fake_run_select(query, params):
        return [{"level_id": 5, "wins": 10, "attempts": 40}]

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    result = await level_stats_service.recalc_level_stats(fake_db, "proj", "ds")

    assert result == {"updated": [], "skipped_low_sample": ["5"]}
    assert "5" not in fake_db._collections.get("level_stats", {})


async def test_recalc_no_data_is_a_noop(fake_db, monkeypatch):
    async def _fake_run_select(query, params):
        return []

    monkeypatch.setattr(bq_streaming, "run_select", _fake_run_select)

    result = await level_stats_service.recalc_level_stats(fake_db, "proj", "ds")

    assert result == {"updated": [], "skipped_low_sample": []}
