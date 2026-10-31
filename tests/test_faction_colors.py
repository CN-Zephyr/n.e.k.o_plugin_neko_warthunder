"""可配置小地图敌我颜色：数据层分类、HTTP 接缝、插件配置与动作。"""

from __future__ import annotations

import asyncio
import sys
import tomllib
import types
import urllib.parse
from pathlib import Path

import pytest
from neko_warthunder.adapters.faction_colors_client import (
    build_faction_colors_url,
    set_faction_colors,
)
from neko_warthunder.core.contracts import (
    DEFAULT_ALLY_COLOR,
    DEFAULT_ENEMY_COLOR,
    WtConfig,
    normalize_hex_color,
)
from test_data_layer_http_security import _request, _Service
from test_status_reporting import _plugin_for_action_tests
from wt_server import TelemetryService
from wt_telemetry import (
    DEFAULT_FACTION_COLORS,
    FactionColors,
    WarThunderClient,
    _classify_faction,
    _parse_map_objects,
    format_hex_color,
    parse_hex_color,
)

_ROOT = Path(__file__).resolve().parent.parent
_ACTION_HEADER = {"X-Neko-Warthunder-Action": "1"}

# 8111 实测颜色（local_samples/data_process_20260620）
_REAL_ENEMY = [(250, 12, 0), (240, 12, 0)]
_REAL_ALLY = [(23, 77, 255), (4, 63, 255)]
_REAL_SELF_YELLOW = (250, 200, 30)


# ------------------------------------------------------------------ 颜色解析
@pytest.mark.parametrize(
    ("raw", "expected"),
    [("#174DFF", (0x17, 0x4D, 0xFF)), ("fa0c00", (0xFA, 0x0C, 0x00)), (" #00ff00 ", (0, 255, 0))],
)
def test_parse_hex_color_accepts_common_forms(raw, expected):
    assert parse_hex_color(raw) == expected


_INVALID_HEX = [None, "", "#FFF", "#GGGGGG", "#1234567", "red", "-12345", "+12345", "12_345", "1 2 34", "##123456"]


@pytest.mark.parametrize("raw", _INVALID_HEX)
def test_parse_hex_color_rejects_invalid(raw):
    assert parse_hex_color(raw) is None


@pytest.mark.parametrize("raw", _INVALID_HEX)
def test_normalize_hex_color_rejects_invalid(raw):
    assert normalize_hex_color(raw, "DEFAULT") == "DEFAULT"


def test_format_hex_color_round_trips():
    assert format_hex_color(parse_hex_color("#abcdef")) == "#ABCDEF"


# ------------------------------------------------------------------ 分类
def test_default_colors_are_blue_ally_and_red_enemy():
    assert format_hex_color(DEFAULT_FACTION_COLORS.ally) == DEFAULT_ALLY_COLOR == "#174DFF"
    assert format_hex_color(DEFAULT_FACTION_COLORS.enemy) == DEFAULT_ENEMY_COLOR == "#FA0C00"
    assert DEFAULT_FACTION_COLORS.conflict is False


@pytest.mark.parametrize("rgb", _REAL_ENEMY)
def test_default_colors_classify_real_enemy_samples(rgb):
    assert _classify_faction("Fighter", rgb) == "enemy"


@pytest.mark.parametrize("rgb", _REAL_ALLY)
def test_default_colors_classify_real_ally_samples(rgb):
    assert _classify_faction("Fighter", rgb) == "ally"


def test_player_icon_and_yellow_stay_self_with_any_colors():
    custom = FactionColors(ally=(0, 255, 0), enemy=(255, 0, 255))
    assert _classify_faction("Player", (250, 12, 0), custom) == "self"
    assert _classify_faction("Fighter", _REAL_SELF_YELLOW) == "self"
    assert _classify_faction("Fighter", _REAL_SELF_YELLOW, custom) == "self"


def test_custom_colors_reclassify_units():
    # 玩家在游戏里把队友改成绿、敌人改成紫
    custom = FactionColors(ally=(0, 200, 0), enemy=(160, 0, 200))
    assert _classify_faction("Fighter", (10, 210, 5), custom) == "ally"
    assert _classify_faction("Fighter", (150, 10, 190), custom) == "enemy"
    # 默认的红/蓝此时都不是敌/友，不能沿用旧约定误判
    assert _classify_faction("Fighter", (250, 12, 0), custom) == "other"
    assert _classify_faction("Fighter", (23, 77, 255), custom) == "other"


def test_swapped_colors_swap_factions():
    swapped = FactionColors(ally=DEFAULT_FACTION_COLORS.enemy, enemy=DEFAULT_FACTION_COLORS.ally)
    assert _classify_faction("Fighter", (250, 12, 0), swapped) == "ally"
    assert _classify_faction("Fighter", (23, 77, 255), swapped) == "enemy"


def test_conflicting_colors_disable_ally_enemy_classification():
    same = FactionColors(ally=(250, 12, 0), enemy=(240, 20, 0))
    assert same.conflict is True
    assert _classify_faction("Fighter", (250, 12, 0), same) == "other"
    assert same.to_dict()["conflict"] is True


def test_parse_map_objects_uses_given_colors():
    items = [
        {"type": "aircraft", "icon": "Fighter", "color[]": [0, 200, 0], "x": 0.1, "y": 0.2},
        {"type": "aircraft", "icon": "Fighter", "color[]": [250, 12, 0], "x": 0.3, "y": 0.4},
    ]
    default_factions = [o.faction for o in _parse_map_objects(items)]
    custom_factions = [
        o.faction for o in _parse_map_objects(items, FactionColors(ally=(0, 200, 0), enemy=(250, 12, 0)))
    ]
    assert default_factions == ["other", "enemy"]
    assert custom_factions == ["ally", "enemy"]


# ------------------------------------------------------------------ 数据层服务
def _service() -> TelemetryService:
    return TelemetryService(WarThunderClient())


def test_service_set_faction_colors_updates_client_and_keeps_invalid_side():
    service = _service()
    assert service.get_faction_colors() == {
        "ally_color": "#174DFF",
        "enemy_color": "#FA0C00",
        "conflict": False,
    }
    result = service.set_faction_colors("#00c800", "not-a-color")
    assert result["ally_color"] == "#00C800"
    assert result["enemy_color"] == "#FA0C00"
    assert service.client.faction_colors.ally == (0, 200, 0)


def test_service_constructor_accepts_initial_colors():
    colors = FactionColors(ally=(1, 2, 3), enemy=(200, 0, 0))
    service = TelemetryService(WarThunderClient(), faction_colors=colors)
    assert service.client.faction_colors is colors


# ------------------------------------------------------------------ HTTP 接缝
class _ColorService(_Service):
    def __init__(self) -> None:
        super().__init__()
        self.colors = {"ally_color": "#174DFF", "enemy_color": "#FA0C00", "conflict": False}
        self.set_calls: list[tuple] = []

    def get_faction_colors(self):
        return dict(self.colors)

    def set_faction_colors(self, ally=None, enemy=None):
        self.set_calls.append((ally, enemy))
        if ally:
            self.colors["ally_color"] = normalize_hex_color(ally, self.colors["ally_color"])
        if enemy:
            self.colors["enemy_color"] = normalize_hex_color(enemy, self.colors["enemy_color"])
        return dict(self.colors)


@pytest.fixture
def color_server(monkeypatch):
    import test_data_layer_http_security as http_tests

    monkeypatch.setattr(http_tests, "_Service", _ColorService)
    with http_tests._running_server() as (port, service):
        yield port, service


def test_http_get_faction_colors_is_read_only(color_server):
    port, service = color_server
    status, _headers, body = _request(port, "/api/faction_colors")
    assert status == 200
    assert body["ally_color"] == "#174DFF"
    assert service.set_calls == []


def test_http_set_faction_colors_requires_action_header(color_server):
    port, service = color_server
    query = "/api/faction_colors?" + urllib.parse.urlencode({"ally": "#00C800"})
    denied, _headers, _body = _request(port, query)
    ok, _headers, body = _request(port, query, headers=_ACTION_HEADER)
    assert denied == 403
    assert ok == 200
    assert body["ally_color"] == "#00C800"
    assert service.set_calls == [("#00C800", None)]


def test_http_set_faction_colors_rejects_invalid_color(color_server):
    port, service = color_server
    query = "/api/faction_colors?" + urllib.parse.urlencode({"ally": "#00C800", "enemy": "bad"})
    status, _headers, body = _request(port, query, headers=_ACTION_HEADER)
    assert status == 400
    assert body["error"] == "invalid_color"
    assert service.set_calls == []


# ------------------------------------------------------------------ 插件配置
def test_plugin_toml_defaults_are_blue_and_red():
    raw = tomllib.loads((_ROOT / "plugin.toml").read_text(encoding="utf-8"))
    section = raw["neko_warthunder"]
    assert section["ally_color"] == DEFAULT_ALLY_COLOR
    assert section["enemy_color"] == DEFAULT_ENEMY_COLOR


def test_wt_config_defaults_and_normalizes_colors():
    assert WtConfig().ally_color == "#174DFF"
    assert WtConfig().enemy_color == "#FA0C00"
    cfg = WtConfig.from_mapping({"ally_color": "00c800", "enemy_color": "nope"})
    assert cfg.ally_color == "#00C800"
    assert cfg.enemy_color == DEFAULT_ENEMY_COLOR


# ------------------------------------------------------------------ 插件 → 数据层客户端
def test_build_faction_colors_url_encodes_hash():
    url = build_faction_colors_url("http://127.0.0.1:8112/", ally="#00C800", enemy="#FA0C00")
    assert url == "http://127.0.0.1:8112/api/faction_colors?ally=%2300C800&enemy=%23FA0C00"


def test_set_faction_colors_client_reports_failure():
    calls = []

    def ok_fetcher(url, timeout):
        calls.append((url, timeout))
        return {"ally_color": "#00C800", "enemy_color": "#FA0C00", "conflict": False}

    result = set_faction_colors("http://h", 1.5, ally="#00C800", enemy="#FA0C00", fetcher=ok_fetcher)
    assert result["ok"] is True
    assert calls[0][1] == 1.5
    assert set_faction_colors("http://h", 1.0, ally="#1", enemy="#2", fetcher=lambda *_: None)["ok"] is False
    assert set_faction_colors(
        "http://h", 1.0, ally="#1", enemy="#2", fetcher=lambda *_: {"error": "invalid_color"}
    )["ok"] is False


# ------------------------------------------------------------------ 插件动作
def _patch_request(monkeypatch, plugin, response):
    import sys

    module = sys.modules[type(plugin).__module__]
    sent = []

    def fake(base_url, timeout, *, ally, enemy):
        sent.append((ally, enemy))
        return response

    monkeypatch.setattr(module, "request_set_faction_colors", fake)
    return sent


def test_set_faction_colors_action_saves_and_forwards(monkeypatch, tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / "state.json"
    sent = _patch_request(monkeypatch, plugin, {"ok": True, "conflict": False})

    result = asyncio.run(plugin.set_faction_colors(ally_color="00c800", enemy_color="#a000c8"))

    assert sent == [("#00C800", "#A000C8")]
    assert result["faction_colors"] == {
        "ally_color": "#00C800",
        "enemy_color": "#A000C8",
        "conflict": False,
        "applied": True,
    }
    assert (plugin.cfg.ally_color, plugin.cfg.enemy_color) == ("#00C800", "#A000C8")
    saved = plugin._load_runtime_state()
    assert saved["ally_color"] == "#00C800"
    assert saved["enemy_color"] == "#A000C8"


def test_set_faction_colors_action_rejects_invalid_without_saving(monkeypatch, tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / "state.json"
    sent = _patch_request(monkeypatch, plugin, {"ok": True})

    result = asyncio.run(plugin.set_faction_colors(ally_color="green", enemy_color="#FA0C00"))

    assert isinstance(result, Exception)
    assert sent == []
    assert plugin.cfg.ally_color == DEFAULT_ALLY_COLOR
    assert "ally_color" not in plugin._load_runtime_state()


def test_set_faction_colors_reset_restores_defaults(monkeypatch, tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / "state.json"
    plugin.cfg.ally_color = "#00C800"
    sent = _patch_request(monkeypatch, plugin, {"ok": True})

    asyncio.run(plugin.set_faction_colors(ally_color="#123456", reset=True))

    assert sent == [(DEFAULT_ALLY_COLOR, DEFAULT_ENEMY_COLOR)]
    assert plugin.cfg.ally_color == DEFAULT_ALLY_COLOR


def test_set_faction_colors_saves_even_when_data_layer_is_down(monkeypatch, tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / "state.json"
    _patch_request(monkeypatch, plugin, {"ok": False, "error": "faction colors request failed"})

    result = asyncio.run(plugin.set_faction_colors(ally_color="#00C800", enemy_color="#FA0C00"))

    assert result["faction_colors"]["applied"] is False
    assert plugin._load_runtime_state()["ally_color"] == "#00C800"


def test_conflict_from_data_layer_is_surfaced(monkeypatch, tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / "state.json"
    _patch_request(monkeypatch, plugin, {"ok": True, "conflict": True})

    result = asyncio.run(plugin.set_faction_colors(ally_color="#FA0C00", enemy_color="#F00C00"))

    assert result["faction_colors"]["conflict"] is True


def test_saved_colors_override_config_on_reload(monkeypatch, tmp_path):
    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / "state.json"
    _patch_request(monkeypatch, plugin, {"ok": True})
    plugin.engine = plugin._build_engine()
    asyncio.run(plugin.set_faction_colors(ally_color="#00C800", enemy_color="#A000C8"))

    class Config:
        async def dump(self, timeout=5.0):
            return {"neko_warthunder": {"ally_color": "#174DFF", "enemy_color": "#FA0C00"}}

    plugin.config = Config()
    asyncio.run(plugin._reload_config())

    assert (plugin.cfg.ally_color, plugin.cfg.enemy_color) == ("#00C800", "#A000C8")


def test_restore_sends_current_colors_including_defaults(monkeypatch):
    plugin = _plugin_for_action_tests()
    sent = _patch_request(monkeypatch, plugin, {"ok": True, "conflict": False})

    assert plugin._restore_faction_colors_to_data_layer() == {"ok": True, "conflict": False}
    assert sent == [(DEFAULT_ALLY_COLOR, DEFAULT_ENEMY_COLOR)]


def test_config_change_applies_new_colors_without_restarting_connection(monkeypatch):
    plugin = _plugin_for_action_tests()
    plugin._startup_completed = True
    sent = _patch_request(monkeypatch, plugin, {"ok": True})

    async def reload_config():
        plugin._apply_config(WtConfig(ally_color="#00C800", enemy_color="#A000C8"))

    plugin._reload_config = reload_config

    asyncio.run(plugin.on_config_change())

    assert sent == [("#00C800", "#A000C8")]


def test_tick_restores_saved_colors_after_data_layer_reconnect(monkeypatch):
    from neko_warthunder.core.contracts import BattleState

    plugin = _plugin_for_action_tests()
    plugin.cfg.ally_color = "#00C800"
    sent = _patch_request(monkeypatch, plugin, {"ok": True})
    plugin.client = types.SimpleNamespace(poll=lambda: BattleState(connected=True, conn_state="not_in_battle"))
    plugin._sync_game_context = lambda *_: None
    plugin._evaluate = lambda *_: None
    plugin._report = lambda: None

    plugin._tick()
    plugin._tick()

    assert sent == [("#00C800", DEFAULT_ENEMY_COLOR)]


def test_failed_color_apply_retries_after_backoff_without_repeating_each_tick(monkeypatch, tmp_path):
    from neko_warthunder.core.contracts import BattleState

    plugin = _plugin_for_action_tests()
    plugin._runtime_state_path = tmp_path / "state.json"
    module = sys.modules[type(plugin).__module__]
    moment = [100.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: moment[0])
    sent = _patch_request(monkeypatch, plugin, {"ok": False})
    plugin.state = BattleState(connected=True)
    plugin.client = types.SimpleNamespace(poll=lambda: BattleState(connected=True))
    plugin._sync_game_context = lambda *_: None
    plugin._evaluate = lambda *_: None
    plugin._report = lambda: None
    asyncio.run(plugin.set_faction_colors(ally_color="#00C800"))
    assert len(sent) == 1
    plugin._tick()
    assert len(sent) == 1
    moment[0] = 105.0
    retried = _patch_request(monkeypatch, plugin, {"ok": True})
    plugin._tick()
    assert plugin._faction_colors_sync_pending is False
    assert retried == [("#00C800", DEFAULT_ENEMY_COLOR)]
    plugin._tick()
    assert len(retried) == 1


def test_dashboard_exposes_faction_colors_and_panel_wires_action():
    panel = (_ROOT / "ui" / "panel.tsx").read_text(encoding="utf-8")
    assert '"set_faction_colors"' in panel
    assert 'type="color"' in panel
    source = (_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert '"faction_colors": {' in source
