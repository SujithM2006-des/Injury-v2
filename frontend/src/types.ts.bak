export type Role = 'ADMIN' | 'MEDICAL' | 'COACH' | 'PLAYER'
export type IdentityStatus = 'CONFIRMED' | 'UNCERTAIN' | 'UNKNOWN'
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH'

/** A player as shown on an event card. */
export interface PlayerRef {
  trackId: number | null
  playerId: number | null
  name: string | null
  jersey: number | null
  team: string | null
  identityStatus: IdentityStatus
  identityConfidence: number | null
}

export interface GeminiInfo {
  verdict: string | null
  confidence: number | null
  reason: string | null
  description: string | null
  jersey: number | null
  team: string | null
  jerseyConfidence: number | null
}

/** One possible injury picked by Gemini from the injury catalog (risk, first step and rest come from the catalog). */
export interface PossibleInjury {
  injury: string
  bodyArea: string
  risk: string | null
  safetyMeasure: string | null
  rest: string | null
  likelihood: number | null
}

/** Gemini's review of the clip: what happened, possible injuries and the expected rest. */
export interface AiInjury {
  description: string | null
  action: string | null
  side: string | null
  rest: string | null
  risk: string | null
  injuries: PossibleInjury[]
  checkedAt: string | null
}

/** One injury event (AI-detected fall or staff-logged event). */
export interface InjuryEvent {
  id: number
  player: PlayerRef
  identified: boolean
  identifiedBy: string | null
  idDetail: string | null
  identifiedAt: string | null
  matchId: number | null
  matchName: string | null
  eventType: string
  region: string | null
  risk: RiskLevel | null
  movement: number | null
  injuryNote: string | null
  note: string | null
  clipUrl: string | null
  source: string
  resolved: boolean
  timestamp: string
  videoTimeSec: number | null
  gemini: GeminiInfo
  aiInjury: AiInjury | null
}

export interface Player {
  id: number
  name: string
  jersey: number
  teamId: number
  teamName: string | null
}

export interface TeamPlayerRow {
  id: number
  name: string
  jersey: number
  injuryEvents: number
  highRiskEvents: number
}

export interface Team {
  id: number
  name: string
  coaches: string[]
  playerCount: number
  injuryEvents: number
  highRiskEvents: number
  players: TeamPlayerRow[]
}

export interface Match {
  id: number
  name: string
  videoSource: string | null
  date: string | null
}