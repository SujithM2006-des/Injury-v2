// Raw shapes returned by the backend (backend/main.py).

export interface LoginDto {
  access_token: string
  role: string // "admin" | "medical" | "coach" | "player"
  team_id: number | null
  username: string
  player_id?: number | null
}

export interface EventDto {
  id: number
  player_id: number | null
  player_name: string
  jersey_number: number | null
  team_name: string | null
  identified: boolean
  identified_at: string | null
  identified_by: string | null
  id_detail: string | null
  id_confidence: number | null
  track_id: number | null
  video_time_sec: number | null
  gemini_verdict: string | null
  gemini_confidence: number | null
  gemini_reason: string | null
  gemini_description: string | null
  gemini_jersey: number | null
  gemini_team: string | null
  gemini_jersey_confidence: number | null
  ai_injury?: AiInjuryDto | null
  match_session_id: number | null
  match_name: string | null
  event_type: string
  region: string | null
  risk: string | null
  movement: number | null
  note: string | null
  injury_note: string | null
  clip_url: string | null
  source: string
  resolved: boolean
  timestamp: string
}

/** Gemini injury check (src/gemini_injury.py): possible injuries from the injury catalog with rest time */
export interface AiInjuryItemDto {
  injury: string
  body_area: string
  risk: string | null
  safety_measure: string | null
  rest: string | null
  likelihood: number | null
}

export interface AiInjuryDto {
  injury_event: boolean
  confidence: number | null
  action: string | null
  description: string | null
  side: string | null
  injuries: AiInjuryItemDto[]
  rest: string | null
  risk: string | null
  model: string | null
  checked_at: string | null
}

export interface PlayerDto {
  id: number
  name: string
  jersey_number: number
  team_id: number
  team_name?: string | null
}

export interface TeamDto {
  id: number
  name: string
  coaches: string[]
  player_count: number
  injury_events: number
  high_risk_events: number
  players: { id: number; name: string; jersey_number: number; injury_events: number; high_risk_events: number }[]
}

export interface MatchDto {
  id: number
  name: string
  video_source: string | null
  date: string | null
}

export interface UserDto {
  id: number
  username: string
  role: string // "admin" | "medical" | "coach" | "player"
  team_id: number | null
  team_name: string | null
  player_id?: number | null      // player logins: the roster player
  player_name?: string | null
  jersey_number?: number | null
  coaches?: string[]
}

/** GET /admin/system — live checks plus the detector's last report. */
export interface DetectorInfoDto {
  match_id?: number | null
  match_name?: string | null
  source_mode?: string | null
  video_source?: string | null
  device?: string | null
  gpu_name?: string | null
  pose_model?: string | null
  model_task?: string | null
  model_file_mb?: number | null
  imgsz?: number | null
  fps?: number | null
  total_frames?: number | null
  ultralytics_version?: string | null
  torch_version?: string | null
  cuda_version?: string | null
  opencv_version?: string | null
  identification?: boolean
  face_enabled?: boolean
  face_ready?: boolean
  ocr_engines?: string[]
  face_engines?: string[]
  gemini_enabled?: boolean
  gemini_available?: boolean
  collision_alerts?: boolean
  tracker_file?: string | null
  tracker_type?: string | null
  tracker_reid?: boolean | null
}

export interface SystemDto {
  checked_at: string
  backend: { ok: boolean; python: string; heartbeat_timeout_seconds: number }
  database: { ok: boolean; engine?: string; users?: number; teams?: number; players?: number; matches?: number; events?: number; detail?: string }
  detector: {
    state: 'never' | 'starting' | 'running' | 'finished' | 'stopped'
    info: DetectorInfoDto
    progress: { frame?: number; events?: number; falls?: number; falls_identified?: number; pending_identification?: number; tracks_identified?: number }
    started_at?: string
    finished_at?: string
    last_seen?: string
    seconds_since_last_signal?: number | null
  }
  identity: { events?: number; identified?: number; unidentified?: number; by_method?: Record<string, number>; gemini_checked?: number; detail?: string }
  medical_knowledge_base: { ok: boolean; risk_levels?: string[]; injury_notes?: number; safety_measure_sets?: number; safety_measure_steps?: number; has_collision_rules?: boolean; detail?: string }
  last_job: { id: number; name: string; video_source: string | null; date: string | null; events: number; identified: number } | null
}
/** GET /events/{id}/assessment, GET /assessments. Coaches only get event_id, status, saved_at, saved_by. */
export interface AssessmentDto {
  event_id: number
  status: string
  saved_at: string
  saved_by: string
  pain?: string
  swelling?: string
  tenderness?: string
  rom?: string
  weight?: string
  neuro?: string
  notes?: string
  imaging?: string
  impression?: string
  created_at?: string
  revision?: number
}

/** GET /detector/status — the detector's live progress for match pages (every role). */
export interface DetectorProgressDto {
  state: 'never' | 'starting' | 'running' | 'finished' | 'stopped'
  match_id?: number | null
  match_name?: string | null
  frame?: number | null
  total_frames?: number | null
  events?: number | null
  started_at?: string | null
  finished_at?: string | null
  seconds_since_last_signal?: number | null
}

/** GET /players/{id}/photos — reference photos in the known_players folder. */
export interface PlayerPhotosDto {
  player_id: number
  folder: string
  photos: { name: string; size: number; uploaded_at: string }[]
  auto_learned: number
}

/** GET /injury-history — previous injuries typed in by a coach (own team) or admin. */
export interface InjuryHistoryDto {
  id: number
  player_id: number
  player_name: string | null
  jersey_number: number | null
  team_id: number | null
  team_name: string | null
  injury: string
  body_area: string
  injury_date: string
  severity: string
  status: string
  days_out: number | null
  notes: string
  added_by: string
  added_at: string
  updated_by?: string
  updated_at?: string
  can_edit: boolean
}