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

## Reply length is the character's business, not the delivery layer's

`short_tts_line` / `max_reply_chars = 28` are **not** waiting on host enforcement, and no host
change should be proposed to make the core truncate replies. Reply length and wording belong to
the character the plugin targets: the plugin resolves `target_lanlan`, the host routes the cue to
that character (`proactive_bridge` carries it through as `lanlan_name`), and that character's
persona is what produces a short spoken line. The plugin's job is to put the constraint in the
prompt, which it already does.

The identically-named metadata keys exist only as observability markers for live debugging — so a
`live_monitor` report can show what the plugin asked for. A host that never reads them is not
missing a feature.

Two identities are involved and must not be confused:

- `player_name` — the operator's **War Thunder in-game nickname**, entered by hand in the panel and
  forwarded to the data layer so it can resolve `is_my_kill` / `is_my_death`. It never reaches the
  dispatcher and never appears in prompts.
- `target_lanlan` — **which character replies**. Resolved automatically by falling back through the
  event payload, `ctx.lanlan_name`, plugin config, `ctx._current_lanlan`, environment overrides and
  finally the host's `get_character_data()`. It follows the active character; the plugin does not
  pin a default.

## Host interop status

The canonical passive behavior is `ai_behavior="read"`: the cue becomes background context for a
natural user turn and must not create a proactive response or hot swap. When a confirmed kill lands
inside the text-chat quiet window, the plugin therefore sends `read` plus
`delivery_intent="passive_context"`. It does **not** use the retired `deferred_candidate` path and
does not promise that the next response will mention the kill.

The plugin also emits generic `delivery_ttl_seconds` and `interrupt_policy="drop"` hints. Hosts
that support them may preserve expiry across their internal queues; older hosts must safely ignore
them. `push_message` acceptance is not evidence of generation or playback completion.

The one delivery semantic with no host implementation on either checkout is
`quiet_window.bypass` — letting a critical cue cut through the user-is-typing quiet window. That is
a timing concern, so a character cannot solve it. Whether it actually needs host work should be
decided from live evidence about whether critical cues arrive late enough to matter, not
pre-emptively.

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
