"""Unit tests for app/services/remote_config_service.py — T-244.
_fetch_template_sync (the actual network I/O: google.auth + urllib) is
monkeypatched at the boundary, same testing strategy already used for
bq_streaming.run_dml/run_select — tests exercise the caching/fallback/cast
logic layered on top, not google.auth or urllib internals.

Each test uses a distinct project_id to avoid cross-test pollution of the
module-level _template_cache (keyed by project_id, TTL-based, shared
module state)."""

from app.services import remote_config_service


def _fake_template(params: dict):
    """Builds a Remote Config template shape: {key: {"defaultValue": {"value": "..."}}}."""
    return {"parameters": {k: {"defaultValue": {"value": v}} for k, v in params.items()}}


async def test_get_value_returns_cast_value_from_template(monkeypatch):
    monkeypatch.setattr(
        remote_config_service, "_fetch_template_sync",
        lambda project_id: _fake_template({"regen_interval_secs": "900"}),
    )
    value = await remote_config_service.get_value(
        "proj-1", "regen_interval_secs", default=1800, cast=int
    )
    assert value == 900


async def test_get_value_falls_back_when_fetch_fails(monkeypatch):
    def _raise(project_id):
        raise RuntimeError("Remote Config API 503: unavailable")

    monkeypatch.setattr(remote_config_service, "_fetch_template_sync", _raise)
    value = await remote_config_service.get_value("proj-2", "regen_interval_secs", default=1800, cast=int)
    assert value == 1800


async def test_get_value_falls_back_when_key_missing(monkeypatch):
    monkeypatch.setattr(
        remote_config_service, "_fetch_template_sync",
        lambda project_id: _fake_template({"some_other_key": "5"}),
    )
    value = await remote_config_service.get_value("proj-3", "default_max_lives", default=5, cast=int)
    assert value == 5


async def test_get_value_falls_back_when_cast_fails(monkeypatch):
    monkeypatch.setattr(
        remote_config_service, "_fetch_template_sync",
        lambda project_id: _fake_template({"default_max_lives": "not-a-number"}),
    )
    value = await remote_config_service.get_value("proj-4", "default_max_lives", default=5, cast=int)
    assert value == 5


async def test_get_value_default_cast_is_str(monkeypatch):
    monkeypatch.setattr(
        remote_config_service, "_fetch_template_sync",
        lambda project_id: _fake_template({"some_key": "hello"}),
    )
    value = await remote_config_service.get_value("proj-5", "some_key", default="fallback")
    assert value == "hello"


async def test_get_value_empty_template_uses_default(monkeypatch):
    monkeypatch.setattr(remote_config_service, "_fetch_template_sync", lambda project_id: {})
    value = await remote_config_service.get_value("proj-6", "default_max_lives", default=5, cast=int)
    assert value == 5


async def test_template_is_cached_within_ttl(monkeypatch):
    calls = {"n": 0}

    def _fetch(project_id):
        calls["n"] += 1
        return _fake_template({"regen_interval_secs": "900"})

    monkeypatch.setattr(remote_config_service, "_fetch_template_sync", _fetch)

    await remote_config_service.get_value("proj-7", "regen_interval_secs", default=1800, cast=int)
    await remote_config_service.get_value("proj-7", "default_max_lives", default=5, cast=int)
    await remote_config_service.get_value("proj-7", "regen_interval_secs", default=1800, cast=int)

    assert calls["n"] == 1  # only the first call actually hit the network
