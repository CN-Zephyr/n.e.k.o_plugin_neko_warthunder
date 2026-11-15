import type { NavalStatusState, NavalDetectionState, NavalInstrumentFields, NavalStaticReference } from "./naval-cards"
import type { PanelTone } from "./panel-format"

export type SafetyState = {
  status?: string
  manual_paused?: boolean
  auto_paused?: boolean
  failures?: number
}

export type IdentityState = {
  player_name?: string | null
  saved_player_name?: string | null
  self?: {
    name?: string | null
    source?: string | null
    confidence?: number | null
  } | null
}

export type DataLayerState = {
  mode?: string
  url?: string
  pid?: number | null
  started_by_plugin?: boolean
  health?: boolean
  last_error?: string | null
}

export type TelemetryState = {
  age_seconds?: number | null
  ias_kmh?: number | null
  mach?: number | null
  altitude_m?: number | null
  radio_altitude_m?: number | null
  climb_ms?: number | null
  fuel_fraction?: number | null
  flags?: Record<string, boolean>
}

export type FlightDiagnosticsState = {
  oil: { status: string; max_c: number | null; observed_channels: number; unavailable_channels: number }
  fuel_estimate: { status: string; burn_kgs: number | null; remaining_sec: number | null;
    age_sec: number | null; max_age_sec: number | null }
}

export type TrustedFactsState = {
  version: number
  readonly: boolean
  domain: string
  status: string
  sources: { id: string; status: string; age_seconds: number | null; life_binding: string }[]
  facts: { id: string; source: string; status: string; value: number | boolean | null; total?: number | null }[]
  capabilities: string[]
  limits: string[]
  output: { mode: string; ground_status_enabled: boolean; v2_enabled: boolean }
}

export type OnDemandState = {
  enabled?: boolean
  status?: string
  role?: string | null
  supported?: boolean
  cleanup_pending?: boolean
}

export type GroundStatusState = {
  status?: string
  sample_age_seconds?: number | null
  sample_timestamp?: number | null
  crew_current?: number | null
  crew_total?: number | null
  ammo_first_stage?: number | null
  gun_stabilizer?: boolean | null
  gear_position?: number | null
  speed_kmh?: number | null
  engine_rpm?: number | null
  gunner_state?: number | null
  driver_state?: number | null
  laser_warning_state?: number | null
  track_broken?: boolean | null
  h_drive_dead?: boolean | null
  breach_dead?: boolean | null
  barrel_dead?: boolean | null
}

export type HelicopterStatusState = {
  status?: string
  sample_age_seconds?: number | null
  rotor_rpm?: number | null
  radio_altitude_m?: number | null
  vario_ms?: number | null
}

export type TakeoffProtectionState = {
  active?: boolean
  radio_altitude_m?: number | null
  radio_altitude_available?: boolean
  enter_m?: number | null
  exit_m?: number | null
  low_alt_grace_seconds?: number | null
  suppresses?: string[]
}

export type ObserveRecord = {
  seq?: number | null
  ts?: number | string | null
  trace_id?: string | null
  event_id?: string | null
  stage?: string | null
  outcome?: string | null
  reason?: string | null
  scenario?: string | null
  safety_status?: string | null
  dry_run?: boolean | null
  pushed?: boolean | null
}

export type ObserveState = {
  last_event?: ObserveRecord | null
  last_decision?: ObserveRecord | null
  last_output_status?: ObserveRecord | null
  recent_activity?: ObserveRecord[]
  recent_timeline?: ObserveRecord[]
  observability_enabled?: boolean
}

export type AwarenessState = {
  proximity_event_count?: number
  latest_proximity?: {
    kind?: string | null
    target_type?: string | null
    category?: string | null
    is_air?: boolean | null
    distance_m?: number | null
    compass?: string | null
    clock?: number | null
  } | null
  situation?: {
    enemy_count?: number | null
    ally_count?: number | null
    air_threat_count?: number | null
    ground_target_count?: number | null
  }
  nearest_ground_target?: {
    kind?: string | null
    grid?: string | null
    distance_m?: number | null
    bearing_deg?: number | null
    relative_deg?: number | null
  } | null
}

export type OutputPolicyState = {
  ground_status_real_output_enabled?: boolean
  dialogue_intrusion_mode?: string | null
  user_chat_quiet_window_seconds?: number | null
  battle_output_quiet_window_seconds?: number | null
  critical_bypass_quiet_window?: boolean | null
  broadcast_frequency?: string | null
  broadcast_categories?: Record<string, boolean>
  critical_safety_always_enabled?: boolean
}

export type OnboardingState = {
  completed?: boolean
  required?: boolean
  trigger?: string
}

export type FactionColorsState = {
  ally_color?: string
  enemy_color?: string
  default_ally_color?: string
  default_enemy_color?: string
}

export type DashboardState = {
  remember_broadcast_choice?: boolean
  enabled?: boolean
  dry_run?: boolean
  connected?: boolean
  conn_state?: string
  in_battle?: boolean
  game_context_active?: boolean
  dead?: boolean
  domain?: string
  domain_label?: string | null
  domain_source?: string
  vehicle_type?: string | null
  profile_matched?: boolean | null
  profile_source?: string | null
  profile_family?: string | null
  scenario?: string
  level?: string
  onboarding?: OnboardingState
  identity?: IdentityState
  faction_colors?: FactionColorsState
  data_layer?: DataLayerState
  telemetry?: TelemetryState
  flight_diagnostics?: FlightDiagnosticsState | null
  trusted_facts?: TrustedFactsState
  on_demand?: OnDemandState
  ground_status?: GroundStatusState | null
  ground_ammo_explanation?: { status: string } | null
  helicopter_status?: HelicopterStatusState | null
  naval_status?: NavalStatusState | null
  map_status?: NavalStatusState | null
  naval_detection?: NavalDetectionState | null
  naval_instrument_fields?: NavalInstrumentFields | null
  naval_static_reference?: NavalStaticReference | null
  takeoff_protection?: TakeoffProtectionState
  output_policy?: OutputPolicyState
  awareness?: AwarenessState
  safety?: SafetyState
  observe?: ObserveState
}

export type PanelSummary = {
  kind: "error" | "safety" | "paused" | "waiting" | "detect" | "identity" | "live"
  tone: PanelTone
  title: string
  detail: string
  modeLabel: string
}

export type ActivityItem = {
  key: string
  time: string
  title: string
  detail: string
  status: string
  tone: PanelTone
  kind: ActivityKind
}

export type ActivityKind = "delivered" | "recorded" | "suppressed" | "failed"
