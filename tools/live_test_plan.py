"""Render a human-oriented live test plan from safe sample readiness data."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import types
from typing import Any

_BASE = pathlib.Path(__file__).resolve().parent.parent
if "neko_warthunder" not in sys.modules:
    _pkg = types.ModuleType("neko_warthunder")
    _pkg.__path__ = [str(_BASE)]  # type: ignore[attr-defined]
    sys.modules["neko_warthunder"] = _pkg

from neko_warthunder.tools.sample_replay import replay_sample_root  # noqa: E402


_ACTION_DETAILS: dict[str, dict[str, str]] = {
    "capture_replay_true_sample": {
        "operation": "进入回放或录像播放，保持插件在线但不要关闭 dry_run。",
        "monitor": "/api/telemetry.replay、observe.last_decision、dry_run / push 日志。",
        "pass": "replay=true 时 Detector 静默，observe.last_decision=detector_suppressed/replay，且没有 BattleEvent 输出。",
        "fail": "replay=true 时仍出现 BattleEvent、dry_run 输出或真实 push。",
        "data_gap": "如果整轮没有 replay=true，只记录为缺真实 replay 样本。",
    },
    "run_free_text_dry_run_safety_check": {
        "operation": "只在 dry_run=true 下触发 combat.feed / hud_notices / awards，不测试真实播报。",
        "monitor": "dry_run 输出、Dispatcher prompt、push_message.parts[].text、T-Safety 记录。",
        "pass": "输出只包含 safe / generic 摘要，不包含玩家名、HUD 原文、combat.feed 原文或 awards 原文。",
        "fail": "prompt 或输出中出现未净化自由文本，先停用该类播报并修 T-Safety。",
        "data_gap": "如果没有出现对应 DTO，只保留为待补样本。",
    },
    "capture_awards_or_free_text_sample": {
        "operation": "制造或等待 awards、HUD notice、combat feed 等自由文本来源出现。",
        "monitor": "coverage.awards_items、hud_notice_codes、combat_feed_items、T-Safety dry_run 输出。",
        "pass": "样本包含自由文本来源，且 dry_run 合同不泄漏原文。",
        "fail": "自由文本绕过 sanitizer 或无法进入 dry_run 决策链。",
        "data_gap": "如果没有 awards / hud_notices / combat.feed，继续向数据层要样本。",
    },
    "use_v16_combat_feed_ownership_fields": {
        "operation": "手动设置 identity 后打出 owned kill/death，优先空战和陆战各一次。",
        "monitor": "combat.feed[].is_my_kill / is_my_death / involves_me、combat.self.source、you_killed / you_died。",
        "pass": "ownership 字段为 true 时插件生成 you_killed / you_died，并经 Arbiter / Dispatcher 输出。",
        "fail": "字段为 true 但插件不出事件，按插件 DTO 接缝 bug 处理。",
        "data_gap": "如果 combat.feed 没有 ownership 字段，归为数据层 v1.6 样本缺口。",
    },
    "set_manual_identity_before_capture": {
        "operation": "开局前在面板输入玩家名并确认 /api/identity 返回 manual。",
        "monitor": "/api/identity、combat.self.source、combat.player_name、ownership 字段。",
        "pass": "combat.self.source=manual，后续 kill/death ownership 围绕该名字生效。",
        "fail": "identity 设置成功但 combat.self 没有切到 manual。",
        "data_gap": "如果数据层没有暴露 combat.self/source，保留为数据层接缝缺口。",
    },
    "capture_owned_kill_or_death": {
        "operation": "触发一次我方击杀或死亡，记录新 combat.feed 项。",
        "monitor": "combat.feed id 单调性、is_my_kill、is_my_death、you_killed、you_died。",
        "pass": "新 feed id 只触发一次对应事件，重复帧不重复播。",
        "fail": "同一 feed id 重复触发，或 true 字段未转成事件。",
        "data_gap": "字段存在但没有 true 命中时，继续补 owned 样本。",
    },
    "trigger_overspeed_critical": {
        "operation": "空战中拉到超速 critical，保持 dry_run=true。",
        "monitor": "processed.flags.overspeed_critical、overspeed/critical、observe.last_decision。",
        "pass": "Detector 产生 overspeed/critical，Arbiter 决策可解释 allow/drop/cooldown。",
        "fail": "flag 出现但 Detector 没有候选事件。",
        "data_gap": "只有 overspeed_warn 没有 critical 时，继续补高速样本。",
    },
    "capture_oil_overheat_notice": {
        "operation": "制造油温过热或等待数据层数据库补齐后复测。",
        "monitor": "hud_notices.feed[].code=oil_overheat、overheat 事件、T-Safety 输出。",
        "pass": "oil_overheat code-only 映射到 overheat，且不带 HUD 原文。",
        "fail": "oil_overheat 出现但插件未映射，或 raw HUD 文本进入输出。",
        "data_gap": "如果数据层仍没有 oil_overheat code，等待 profile/database 补齐。",
    },
    "wait_for_powertrain_profile_or_sample": {
        "operation": "等待动力故障 profile/database 或真实 powertrain_failure 样本，保持 dry_run 优先观察。",
        "monitor": "hud_notices.feed[].code=powertrain_failure、observe.last_decision.reason=deferred_hud_notice、live_monitor Decision detail。",
        "pass": "powertrain_failure 只记录 detector_suppressed/deferred_hud_notice，不直接播报，不带 raw HUD 文本。",
        "fail": "powertrain_failure 被硬造为真实播报事件，或 raw HUD 文本进入 prompt / push。",
        "data_gap": "没有 powertrain_failure 样本或数据库时，继续保持 TODO；有样本后再决定是否新增或映射故障事件。",
    },
    "verify_hud_notice_severity_mapping": {
        "operation": "采集 warning / critical notice 档位样本。",
        "monitor": "hud_notice_severities、事件 level、observe.last_decision。",
        "pass": "severity 能稳定映射 warning / critical。",
        "fail": "severity 不稳定时继续使用保守默认档位。",
        "data_gap": "只有 unknown severity 时，继续补数据层映射。",
    },
    "capture_rear_threat_or_six_oclock_sample": {
        "operation": "空战中让敌机或空中目标进入后方 5/6/7 点钟区域，保持 dry_run=true，尽量保留一段接近到脱离的样本。",
        "monitor": "proximity.events[].clock / relative_deg、observe.last_event、observe.last_decision、enemy_on_six / tailing_risk dry_run 输出。",
        "pass": "后方 proximity 新 id 触发 enemy_on_six，短窗连续近距离后方事件升级为 tailing_risk，prompt 只包含后方威胁 / 钟点 / 距离等安全摘要，critical 安全事件仍优先。",
        "fail": "后方 proximity 出现但插件无事件，或 raw proximity 文本 / 玩家名进入 prompt，或 critical 被后方威胁抢占。",
        "data_gap": "如果没有后方 / 六点钟 proximity，只记录为缺 rear-threat 样本；已有普通空中 proximity 不等于完成 enemy_on_six / tailing_risk 验证。",
    },
    "capture_sustained_close_rear_sample": {
        "operation": "空战中让后方威胁在短时间内连续保持近距离，优先让 proximity distance_m 多次低于 900m。",
        "monitor": "proximity.events[].clock / relative_deg / distance_m、tailing_risk、observe.last_decision。",
        "pass": "连续近距离后方样本保守升级为 tailing_risk，且不会抢占 critical 安全事件。",
        "fail": "后方近距样本已连续出现但没有 tailing_risk，或 tailing_risk 输出泄漏 raw proximity 文本。",
        "data_gap": "如果只有一次后方接近或距离太远，只记录为缺持续尾随样本。",
    },
    "capture_ground_target_sample": {
        "operation": "空战或对地任务中靠近轰炸点/任务目标点，保持 dry_run=true，记录一段 situation.ground_targets 样本。",
        "monitor": "situation.ground_targets[].grid / distance_m、ground_target_nearby、observe.last_decision、dry_run 输出。",
        "pass": "近距离 ground target 触发 ground_target_nearby，prompt 只包含任务目标点 / 网格 / 距离等安全摘要，COMBAT_STRESS 下低优先级目标提示可被压住。",
        "fail": "ground_targets 存在但插件无事件，或目标 label/raw 文本进入 prompt，或目标点提示抢占 critical 安全事件。",
        "data_gap": "如果没有 ground_targets，只记录为缺对地任务目标样本；普通 proximity 不等于完成目标点验证。",
    },
    "fly_closer_to_ground_target_sample": {
        "operation": "空战或对地任务中继续靠近轰炸点/任务目标点，尽量进入 3000m 内并保持 dry_run=true。",
        "monitor": "situation.ground_targets[].distance_m、ground_target_nearby、observe.last_decision、dry_run 输出。",
        "pass": "distance_m 进入 3000m 内后触发 ground_target_nearby；prompt 只包含任务目标点 / 网格 / 距离等安全摘要。",
        "fail": "已经出现 3000m 内目标候选但插件无 ground_target_nearby，或目标 label/raw 文本进入 prompt。",
        "data_gap": "如果 ground_targets 一直存在但距离均大于 3000m，只记录为缺近目标点候选，不算插件触发失败。",
    },
    "verify_output_backpressure": {
        "operation": "dry_run=false 时连续触发同优先级或更低优先级事件，观察是否被输出背压压住。",
        "monitor": "tools/live_monitor.py Summary、observe.last_output_status、output_backpressure、event_expired、push_message 时延。",
        "pass": "Summary 显示 output=dispatcher_suppressed/dropped(output_backpressure)、output=dispatcher_suppressed/dropped(event_expired) 或 repeated_event_collapsed；旧事件不再排队晚回，击杀、death、critical 安全事件仍能通过。",
        "fail": "连续事件仍造成晚回、刷屏，或更高优先级事件被误压。",
        "data_gap": "不依赖新 DTO；若现场事件不足，可用 test_say / generic kill-death smoke 补充。",
    },
    "verify_kill_coalescing": {
        "operation": "dry_run=false 或 dry_run=true 下打出短窗多杀，优先用 owned combat.feed 或已验证的杀敌场景。",
        "monitor": "tools/live_monitor.py Summary、observe.last_decision、kill_coalesced、kill_count、push_message 轮数。",
        "pass": "Summary / Observe 保留 decision=arbiter_allowed/allowed/kill_coalesced，多杀合成单条 generic 输出，kill_count 可解释。",
        "fail": "多杀连续刷屏、kill_count 丢失，或 you_died / critical 不能抢占。",
        "data_gap": "如果现场没有 owned kill 样本，先保留下一轮真机用例。",
    },
    "verify_user_chat_interference_quiet_window": {
        "operation": "真实开口或样本回放期间，等普通战雷 cue 进入队列后手动给猫发一句日常消息，例如“喵”或“你先等一下”。",
        "monitor": "聊天窗口、用户输入后约 10 秒内的战雷 callback、neko_warthunder:battle_event metadata、death/critical 插队情况。",
        "pass": "普通战雷 cue 不混入这轮日常回复；warning 低空/超速不因 priority 高而插队；you_died 和 level=critical 危险仍可插队。",
        "fail": "猫把旧的普通战雷 cue 混进日常回复，或 death/critical 被静默窗误压。",
        "data_gap": "不依赖新 DTO；若现场没有普通 cue，可用 replay_8112_server 回放含低空/敌机/过热的样本补测。",
    },
}


def build_compact_plan(root: str | pathlib.Path, *, player_name: str = "tl0sr2") -> dict[str, Any]:
    report = replay_sample_root(root, player_name=player_name)
    summary = report.get("session_summary") or {}
    steps = [build_step_from_item(item) for item in summary.get("live_test_plan") or [] if isinstance(item, dict)]
    quick_checklist = build_quick_checklist(steps)
    return {
        "root": report.get("root"),
        "files": report.get("files"),
        "frames": report.get("frames"),
        "status": summary.get("status") or "unknown",
        "steps": steps,
        "quick_checklist": quick_checklist,
        "next_steps": list(summary.get("next_steps") or []),
        "coverage_gaps": list(report.get("coverage_gaps") or []),
    }


def build_markdown_plan(root: str | pathlib.Path, *, player_name: str = "tl0sr2") -> str:
    payload = build_compact_plan(root, player_name=player_name)
    lines = [
        "# neko_warthunder live test plan",
        "",
        f"- sample root: `{payload.get('root')}`",
        f"- frames: `{payload.get('frames')}`",
        f"- status: `{payload.get('status')}`",
        "",
    ]
    steps = payload.get("steps") or []
    quick_checklist = payload.get("quick_checklist") or []
    if quick_checklist:
        lines.extend(
            [
                "## Operator quick checklist",
                "",
                "| 顺序 | 用户操作 | 我方监控重点 | 通过标准 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in quick_checklist:
            lines.append(f"| {item['order']} | {item['user_action']} | {item['monitor']} | {item['pass']} |")
        lines.append("")
    if not steps:
        lines.extend(["## No live-test gaps", "", "- 当前样本没有生成额外真机待测项。"])
    for step in steps:
        lines.extend(
            [
                f"## {step['priority']} {step['label']}",
                "",
                f"- 操作：{step['operation']}",
                f"- 监控：{step['monitor']}",
                f"- 通过：{step['pass']}",
                f"- 失败：{step['fail']}",
                f"- 数据层缺口：{step['data_gap']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Safety boundary",
            "",
            "- 全程不记录玩家名、HUD 原文、combat.feed 原文或 awards 原文。",
            "- 自由文本路径只做 dry_run 安全验证，通过前不做真实播报。",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def build_step_from_item(item: dict[str, Any]) -> dict[str, Any]:
    action = str(item.get("action") or "")
    detail = _ACTION_DETAILS.get(action, _fallback_detail(action))
    return {
        "priority": item.get("priority") or "P?",
        "area": item.get("area") or "unknown",
        "label": item.get("label") or item.get("area") or "unknown",
        "status": item.get("status") or "unknown",
        "action": action,
        "operation": detail["operation"],
        "monitor": detail["monitor"],
        "pass": detail["pass"],
        "fail": detail["fail"],
        "data_gap": detail["data_gap"],
    }


def build_quick_checklist(steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions = {str(step.get("action") or "") for step in steps}
    checklist = [
        {
            "order": "0",
            "user_action": "先跑离线门禁，或确认当天代码未变。",
            "monitor": "tests/run_logic_tests.py、pytest、host boundary gate、plugin check、sample/live plan。",
            "pass": "离线基线通过，操作清单包含 P1/P2 待测项。",
        },
        {
            "order": "1",
            "user_action": "启动宿主、Hosted UI、数据层，打开面板。",
            "monitor": "48911/health、48916/health、8112/health、Hosted UI context/actions。",
            "pass": "三项 health 正常，context 非空，actions 可调用。",
        },
        {
            "order": "2",
            "user_action": "进战局前设置玩家名。",
            "monitor": "/api/identity、combat.self.source、combat.player_name。",
            "pass": "combat.self.source=manual，后续 ownership 围绕该昵称生效。",
        },
        {
            "order": "3",
            "user_action": "保持 `dry_run=true`，打一轮常规空战或陆战。",
            "monitor": "observe.last_event、observe.last_decision、observe.last_output_status、processed.flags。",
            "pass": "事件能解释为 allowed / preempt / cooldown / scenario_gated / dry_run 输出之一。",
        },
    ]
    if "use_v16_combat_feed_ownership_fields" in actions or "capture_owned_kill_or_death" in actions:
        checklist.append(
            {
                "order": "4",
                "user_action": "触发或等待 owned kill / death。",
                "monitor": "combat.feed[].is_my_kill / is_my_death、you_killed / you_died。",
                "pass": "生成 generic kill/death，不含 raw 玩家名；death / critical 仍可抢占。",
            }
        )
    if "run_free_text_dry_run_safety_check" in actions or "capture_awards_or_free_text_sample" in actions:
        checklist.append(
            {
                "order": "5",
                "user_action": "观察 awards / hud_notices / combat.feed 自由文本源。",
                "monitor": "free_text_safety.status、source_details、prompt / dry_run 输出。",
                "pass": "free_text=dry_run_only，raw HUD / combat.feed / awards 原文不进入 prompt。",
            }
        )
    if "capture_replay_true_sample" in actions:
        checklist.append(
            {
                "order": "6",
                "user_action": "若出现 replay，继续观察不要手动触发输出。",
                "monitor": "replay=true、detector_suppressed/replay、output_blocked。",
                "pass": "replay 帧静默，live_monitor 显示 replay suppressed，不真实开口。",
            }
        )
    if "capture_ground_target_sample" in actions or "fly_closer_to_ground_target_sample" in actions:
        checklist.append(
            {
                "order": "6b",
                "user_action": "空战/对地任务中靠近任务目标点，尽量进入 3000m 内。",
                "monitor": "situation.ground_targets、ground_target_nearby、observe.last_decision。",
                "pass": "只输出任务目标点的网格/距离安全摘要，不读取 label/raw 文本。",
            }
        )
    if "verify_output_backpressure" in actions or "verify_kill_coalescing" in actions:
        checklist.append(
            {
                "order": "7",
                "user_action": "条件允许时关闭 `dry_run`，复测数值安全或 generic kill/death。",
                "monitor": "push_message、last_output_status、output_backpressure、event_expired、repeated_event_collapsed、kill_coalesced。",
                "pass": "真实开口不刷屏，旧回复晚到减少，过期旧事件不真实 push，更高优先级事件仍可插队。",
            }
        )
    if "verify_user_chat_interference_quiet_window" in actions:
        checklist.append(
            {
                "order": "7a",
                "user_action": "真实开口或样本回放期间手动给猫发日常消息。",
                "monitor": "聊天窗口、用户输入后约 10 秒内的战雷 callback、battle_event metadata。",
                "pass": "普通战雷 cue 不混入这轮日常回复；warning 低空/超速不因 priority 高而插队；death / critical 仍可插队。",
            }
        )
    if "wait_for_powertrain_profile_or_sample" in actions:
        checklist.append(
            {
                "order": "8",
                "user_action": "若出现动力故障 HUD 技术通知，不急着判断成播报事件。",
                "monitor": "powertrain_failure、deferred_hud_notice、detector_suppressed、raw HUD 是否被阻断。",
                "pass": "只显示 deferred 可观测记录，不真实开口，不泄漏 raw HUD 文本。",
            }
        )
    return checklist


def _fallback_detail(action: str) -> dict[str, str]:
    return {
        "operation": f"按 `{action or 'unknown'}` 补充样本或真机验证。",
        "monitor": "observe.last_decision、observe.last_output_status、dry_run 输出。",
        "pass": "链路可解释且不泄漏自由文本原文。",
        "fail": "出现不可解释输出、真实 push 异常或安全合同破坏。",
        "data_gap": "缺少对应 DTO 时记录为数据层样本缺口。",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the next neko_warthunder live-test operation plan.")
    parser.add_argument("root", nargs="?", default=str(_BASE / "local_samples" / "data_process_20260620"))
    parser.add_argument("player_name", nargs="?", default="tl0sr2")
    parser.add_argument("--output", help="Write Markdown plan to this path instead of stdout.")
    parser.add_argument("--json", action="store_true", help="Print a compact safe JSON plan.")
    args = parser.parse_args(argv)

    if args.json:
        print(json.dumps(build_compact_plan(args.root, player_name=args.player_name), ensure_ascii=False, sort_keys=True))
        return 0

    markdown = build_markdown_plan(args.root, player_name=args.player_name)
    if args.output:
        out = pathlib.Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
