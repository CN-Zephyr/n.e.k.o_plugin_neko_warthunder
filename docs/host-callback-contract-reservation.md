# Host Callback Contract Reservation

This plugin does not require a War-Thunder-specific host core patch.

For future host support, real battle outputs reserve a generic callback contract
inside `push_message(..., metadata=...)`:

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
    "reply": {
      "mode": "short_tts_line",
      "style": "short_line",
      "max_chars": 28,
      "single_turn": true,
      "drop_followup_chunks": true,
      "style_hint": "Style: one short Chinese line; urgent command; no filler."
    },
    "quiet_window": {
      "policy": "suppress_non_urgent_during_user_input",
      "bypass": true
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

The host-facing semantics are generic:

- `delivery.coalesce_key`: host may replace older pending callbacks with the same key.
- `delivery.replace_pending`: host may drop stale pending callbacks before enqueueing this one.
- `delivery.interrupt_pending`: host may let this cue preempt an older pending cue.
- `delivery.expires_at`: host should drop the cue if it is already stale.
- `reply.mode=short_tts_line`: host should produce one short spoken line.
- `reply.max_chars`: host should cap final reply text.
- `reply.single_turn`: host should avoid multi-chunk continuation.
- `quiet_window.policy`: host may suppress ordinary cues during recent user input.
- `quiet_window.bypass`: host may allow urgent cues through that quiet window.

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
- `quiet_window_policy`

`tools/output_freshness_gate.py` verifies both the legacy fields and the generic
`host_callback_contract` block. Host core changes should consume the generic
contract only; they should not special-case `neko_warthunder`.
