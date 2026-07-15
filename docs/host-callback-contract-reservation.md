# Host Callback Contract Reservation

This plugin does not require a War-Thunder-specific host core patch.

For future host support, real battle outputs reserve a generic delivery contract
inside `push_message(..., metadata=...)`. Dialogue shaping stays plugin-owned.

```json
{
  "host_callback_contract_version": "neko.callback.v1",
  "host_callback_contract": {
    "version": "neko.callback.v1",
    "kind": "realtime_cue",
    "delivery": {
      "coalesce_key": "neko_warthunder:battle_event",
      "replace_pending": true,
      "interrupt_pending": true,
      "priority": 9,
      "expires_at": 105.0,
      "max_age_seconds": 8.0
    },
    "freshness": {
      "event_ts": 97.0,
      "event_age_seconds": 3.0,
      "event_max_age_seconds": 8.0,
      "event_expires_at": 105.0
    },
    "target": {
      "lanlan": "Lanlan"
    }
  }
}
```

The host-facing semantics are generic delivery only:

- `delivery.coalesce_key`: host may replace older pending callbacks with the same key.
- `delivery.replace_pending`: host may drop stale pending callbacks before enqueueing this one.
- `delivery.interrupt_pending`: host may let this cue preempt an older pending cue.
- `delivery.expires_at`: host should drop the cue if it is already stale.

Legacy flat metadata is still emitted for current tooling:

- `coalesce_key`
- `replace_pending`
- `interrupt_battle_event`
- `interrupt_pending`
- `battle_reply_contract`
- `live_reply_contract`
- `reply_contract`
- `max_reply_chars`
- `reply_max_chars`
- `reply_style_contract`
- `dialogue_policy_owner=plugin`
- `plugin_dialogue_policy`
- `plugin_quiet_window_policy`
- `plugin_recommended_reply`
- `plugin_owned_output`

Current plugin-owned dialogue behavior:

- `plugin_reply_hint_enabled=true` by default: the plugin adds a deterministic short recommended line to the prompt and metadata so the LLM has a concrete one-line target.
- `plugin_owned_battle_output_enabled=false` by default: non-urgent battle cues use bounded `respond` with `plugin_recommended_reply`, giving the host LLM room for short, domain-aware polish while keeping War Thunder facts and safety constraints plugin-owned.
- `plugin_owned_urgent_output_enabled=false` by default: urgent safety cues use `ai_behavior="respond"` so the catgirl response reaches TTS. Plugin-owned direct chat output remains an explicit opt-in for deployments that prefer lower latency over speech.
- `plugin_owned_blind_output_enabled=false` by default: this remains the explicit force-all direct-output switch, while normal release behavior is split between bounded `respond` for non-urgent cues and plugin-owned direct output for urgent cues.
- If `plugin_owned_battle_output_enabled=true`, deterministic non-urgent battle cues can also use the plugin-owned direct-output path for deliberate experiments or stricter no-polish deployments.

`tools/output_freshness_gate.py` verifies the plugin-owned dialogue policy and
the generic delivery-only `host_callback_contract` block. Host core must not
special-case `neko_warthunder`, and must not own War Thunder reply shaping.
