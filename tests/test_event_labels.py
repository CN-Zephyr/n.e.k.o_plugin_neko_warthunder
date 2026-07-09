"""Safe display labels for reports and UI summaries."""

from __future__ import annotations


def test_event_display_label_maps_internal_ids_to_plugin_language():
    from neko_warthunder.adapters.event_labels import display_event_id, display_event_key

    assert display_event_id("you_killed") == "击杀确认"
    assert display_event_id("you_died") == "被击毁"
    assert display_event_id("low_alt_danger") == "低空危险"
    assert display_event_id("ground_target_nearby") == "任务目标接近"
    assert display_event_id("ground_gunner_disabled") == "炮手失能"
    assert display_event_id("ground_driver_disabled") == "驾驶员失能"
    assert display_event_id("enemy_on_six") == "后方威胁"
    assert display_event_id("tailing_risk") == "持续尾随风险"
    assert display_event_key("overspeed/critical") == "超速风险 / critical"
    assert display_event_key("air_threat_nearby/warning") == "空中威胁接近 / warning"


def test_event_display_label_keeps_unknown_ids_debuggable():
    from neko_warthunder.adapters.event_labels import display_event_id, display_event_key

    assert display_event_id("future_event") == "future_event"
    assert display_event_key("future_event/warning") == "future_event / warning"
