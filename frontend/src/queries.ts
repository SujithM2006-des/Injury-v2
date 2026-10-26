import { useQuery } from '@tanstack/react-query'
import { getAlertReads, getAssessments, getDetectorProgress, getEvents, getInjuryHistory, getMatches, getPlayers, getTeams } from './api/services'
import { devMode, tokenStore } from './api/client'
import type { InjuryEvent } from './types'

// Nothing is fetched without a login (logged out, or the developer preview).
const on = () => !devMode.get() && !!tokenStore.get()

/** Match name without the date the backend adds ("fall_test - 19 Oct 2026 17:30" -> "fall_test"). */
const baseMatch = (m: string | null) => (m ?? '').replace(/\s+-\s+\d{1,2}\s+\w{3}\s+\d{4}.*$/, '').trim().toLowerCase()

/** True when two events are the same fall from the same match video analysed again:
 *  same video, same moment (within 2 s), same body area and type, and not two different players. */
const sameFall = (a: InjuryEvent, b: InjuryEvent) =>
  a.videoTimeSec !== null && b.videoTimeSec !== null
  && Math.abs(a.videoTimeSec - b.videoTimeSec) <= 2
  && baseMatch(a.matchName) === baseMatch(b.matchName)
  && (a.region ?? '') === (b.region ?? '')
  && a.eventType === b.eventType
  && !(a.player.playerId !== null && b.player.playerId !== null && a.player.playerId !== b.player.playerId)

/** Every clip once: when a fall was saved again (re-run of the same video, maybe with a
 *  different risk), only the newest copy is kept. Nothing is deleted in the database. */
export function uniqueEvents(list: InjuryEvent[]): InjuryEvent[] {
  const newest = [...list].sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp))
  const kept: InjuryEvent[] = []
  for (const e of newest) if (!kept.some((k) => sameFall(k, e))) kept.push(e)
  const keep = new Set(kept.map((e) => e.id))
  return list.filter((e) => keep.has(e.id)) // original order
}

// Live data: events refresh every 3 s (same as the old dashboard), teams every 5 s, matches every 10 s.
// Every page gets the events from here, so repeated clips are removed for every user.
export const useEvents = (matchId?: number | null) =>
  useQuery({ queryKey: ['events', matchId ?? 'all'], queryFn: () => getEvents(matchId), select: uniqueEvents, refetchInterval: 3000, enabled: on() })

export const useTeams = () => useQuery({ queryKey: ['teams'], queryFn: getTeams, refetchInterval: 5000, enabled: on() })

export const useMatches = () => useQuery({ queryKey: ['matches'], queryFn: getMatches, refetchInterval: 10000, enabled: on() })

/** Both teams, every role (needed to identify an Unidentified fall). Loaded once. */
export const usePlayers = () => useQuery({ queryKey: ['players'], queryFn: getPlayers, staleTime: Infinity, enabled: on() })

/* ---------- medical staff and coach features ---------- */

/** Saved medical assessments (coaches get the outcome only). */
export const useAssessments = (enabled = true) =>
  useQuery({ queryKey: ['assessments'], queryFn: getAssessments, refetchInterval: 10000, enabled: on() && enabled })

/** Alerts this user has already read. */
export const useAlertReads = (enabled = true) =>
  useQuery({ queryKey: ['alertReads'], queryFn: getAlertReads, refetchInterval: 15000, enabled: on() && enabled })

/** Live detector progress for match pages (every 5 s). */
export const useDetector = (enabled = true) =>
  useQuery({ queryKey: ['detector'], queryFn: getDetectorProgress, refetchInterval: 5000, enabled: on() && enabled })

/** Previous injury history (medical/admin: every player, coach: own team). */
export const useInjuryHistory = (enabled = true) =>
  useQuery({ queryKey: ['injuryHistory'], queryFn: getInjuryHistory, refetchInterval: 15000, enabled: on() && enabled })