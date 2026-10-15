import type { IdentityStatus, InjuryEvent, Match, Player, PlayerRef, RiskLevel, Role, Team } from '../../types'
import type { EventDto, MatchDto, PlayerDto, TeamDto, UserDto } from '../dto'
import { API_BASE } from '../client'

/** A null player_id always maps to UNKNOWN; identity is never guessed. */
export const unknownPlayer: PlayerRef = { trackId: null, playerId: null, name: null, jersey: null, team: null, identityStatus: 'UNKNOWN', identityConfidence: null }

export const toRole = (r: string): Role => {
  const v = r.toUpperCase()
  return v === 'ADMIN' ? 'ADMIN' : v === 'MEDICAL' ? 'MEDICAL' : v === 'PLAYER' ? 'PLAYER' : 'COACH'
}

const toRisk = (r: string | null): RiskLevel | null => {
  const v = (r || '').toUpperCase()
  return v === 'LOW' || v === 'MEDIUM' || v === 'HIGH' ? v : null
}

/** Staff picks and confident AI reads are "Confirmed"; weaker AI reads are "Uncertain". */
const toIdentity = (e: EventDto): IdentityStatus => {
  if (!e.identified) return 'UNKNOWN'
  if (e.identified_by === 'manual') return 'CONFIRMED'
  return e.id_confidence === null || e.id_confidence >= 0.85 ? 'CONFIRMED' : 'UNCERTAIN'
}

export function toEvent(e: EventDto): InjuryEvent {
  return {
    id: e.id,
    player: {
      trackId: e.track_id,
      playerId: e.player_id,
      name: e.identified ? e.player_name : null,
      jersey: e.jersey_number,
      team: e.team_name,
      identityStatus: toIdentity(e),
      identityConfidence: e.id_confidence,
    },
    identified: e.identified,
    identifiedBy: e.identified_by,
    idDetail: e.id_detail,
    identifiedAt: e.identified_at,
    matchId: e.match_session_id,
    matchName: e.match_name,
    eventType: e.event_type,
    region: e.region,
    risk: toRisk(e.risk),
    movement: e.movement,
    injuryNote: e.injury_note,
    note: e.note,
    clipUrl: e.clip_url ? API_BASE + e.clip_url : null,
    source: e.source,
    resolved: !!e.resolved,
    timestamp: e.timestamp,
    videoTimeSec: e.video_time_sec,
    gemini: {
      verdict: e.gemini_verdict,
      confidence: e.gemini_confidence,
      reason: e.gemini_reason,
      description: e.gemini_description,
      jersey: e.gemini_jersey,
      team: e.gemini_team,
      jerseyConfidence: e.gemini_jersey_confidence,
    },
    aiInjury: e.ai_injury && e.ai_injury.injuries?.length ? {
      description: e.ai_injury.description ?? null,
      action: e.ai_injury.action ?? null,
      side: e.ai_injury.side ?? null,
      rest: e.ai_injury.rest ?? e.ai_injury.injuries[0].rest ?? null,
      risk: e.ai_injury.risk ?? null,
      injuries: e.ai_injury.injuries.map((i) => ({ injury: i.injury, bodyArea: i.body_area, risk: i.risk ?? null, safetyMeasure: i.safety_measure ?? null, rest: i.rest ?? null, likelihood: i.likelihood ?? null })),
      checkedAt: e.ai_injury.checked_at ?? null,
    } : null,
  }
}

export const toPlayer = (p: PlayerDto): Player => ({ id: p.id, name: p.name, jersey: p.jersey_number, teamId: p.team_id, teamName: p.team_name ?? null })

export const toTeam = (t: TeamDto): Team => ({
  id: t.id,
  name: t.name,
  coaches: t.coaches,
  playerCount: t.player_count,
  injuryEvents: t.injury_events,
  highRiskEvents: t.high_risk_events,
  players: t.players.map((p) => ({ id: p.id, name: p.name, jersey: p.jersey_number, injuryEvents: p.injury_events, highRiskEvents: p.high_risk_events })),
})

export const toMatch = (m: MatchDto): Match => ({ id: m.id, name: m.name, videoSource: m.video_source, date: m.date })

/** A login account (Users page). */
export interface AppUser {
  id: number
  username: string
  role: Role
  teamId: number | null
  teamName: string | null
  /** Player logins: the roster player this account belongs to */
  playerId: number | null
  playerName: string | null
  jersey: number | null
  coaches: string[]
}

export const toUser = (u: UserDto): AppUser => ({ id: u.id, username: u.username, role: toRole(u.role), teamId: u.team_id, teamName: u.team_name, playerId: u.player_id ?? null, playerName: u.player_name ?? null, jersey: u.jersey_number ?? null, coaches: u.coaches ?? [] })