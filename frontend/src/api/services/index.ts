import { api } from '../client'
import { EP } from '../endpoints'
import type { AssessmentDto, DetectorProgressDto, EventDto, InjuryHistoryDto, LoginDto, MatchDto, PlayerDto, PlayerPhotosDto, SystemDto, TeamDto, UserDto } from '../dto'
import { toEvent, toMatch, toPlayer, toTeam, toUser, type AppUser } from '../mappers'
import type { InjuryEvent, Match, Player, RiskLevel, Role, Team } from '../../types'

export async function login(username: string, password: string): Promise<LoginDto> {
  return (await api.post<LoginDto>(EP.login, { username, password })).data
}

/** Medical/admin get every event; coaches get their team's events plus Unidentified ones. */
export async function getEvents(matchId?: number | null): Promise<InjuryEvent[]> {
  const r = await api.get<EventDto[]>(EP.events, { params: matchId ? { match_id: matchId } : {} })
  return r.data.map(toEvent)
}

export async function getPlayers(): Promise<Player[]> {
  return (await api.get<PlayerDto[]>(EP.players)).data.map(toPlayer)
}

/** Admin/medical: both teams. Coach: own team only. */
export async function getTeams(): Promise<Team[]> {
  return (await api.get<TeamDto[]>(EP.teams)).data.map(toTeam)
}

export async function getMatches(): Promise<Match[]> {
  return (await api.get<MatchDto[]>(EP.matches)).data.map(toMatch)
}

/** Any role for an Unidentified event; only medical/admin can change an identified one. */
export async function assignPlayer(eventId: number, playerId: number): Promise<InjuryEvent | null> {
  const r = await api.patch<{ event?: EventDto }>(EP.assign(eventId), { player_id: playerId })
  return r.data.event ? toEvent(r.data.event) : null
}

/** Medical only. */
export async function logManualEvent(v: { playerId: number; eventType: string; note: string; risk: RiskLevel; matchId: number | null }) {
  await api.post(EP.manualEvent, { player_id: v.playerId, event_type: v.eventType, note: v.note, risk: v.risk, match_session_id: v.matchId })
}

/** Admin only: one event (e.g. a test or wrong detection), with its clip, AI results and assessment. */
export async function deleteEvent(eventId: number): Promise<void> {
  await api.delete(EP.event(eventId))
}

/** Admin only. Players and teams are kept. */
export async function clearAllEvents(): Promise<number> {
  return (await api.delete<{ deleted_events: number }>(EP.clearEvents)).data.deleted_events
}

/** Admin: every login account. Team owner: own team's logins + medical staff. */
export async function getUsers(): Promise<AppUser[]> {
  return (await api.get<UserDto[]>(EP.users)).data.map(toUser)
}

/** Admin, or a team owner for their own team (coach / player only). A coach or owner needs a team, a player login needs its roster player. */
export async function createUser(v: { username: string; password: string; role: Role; teamId: number | null; playerId?: number | null }): Promise<AppUser> {
  const r = await api.post<{ user: UserDto }>(EP.users, { username: v.username, password: v.password, role: v.role.toLowerCase(), team_id: v.role === 'COACH' || v.role === 'OWNER' ? v.teamId : null, player_id: v.role === 'PLAYER' ? v.playerId ?? null : null })
  return toUser(r.data.user)
}

/** Admin; a team owner only coach / player logins of their own team. You cannot delete yourself or the last admin. */
export async function deleteUser(id: number): Promise<void> {
  await api.delete(EP.user(id))
}

/** Admin only: backend, database, detector, identification and medical knowledge base status. */
export async function getSystemStatus(): Promise<SystemDto> {
  return (await api.get<SystemDto>(EP.system)).data
}

/* ---------- medical staff and coach features ---------- */

/** The logged-in account (team name for coaches). */
export async function getMe(): Promise<AppUser> {
  return toUser((await api.get<UserDto>(EP.me)).data)
}

/** Any role: change your own password. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await api.post(EP.changePassword, { current_password: currentPassword, new_password: newPassword })
}

/** Medical/admin: full assessments. Coach: outcome only (status, date, who). */
export async function getAssessments(): Promise<AssessmentDto[]> {
  return (await api.get<AssessmentDto[]>(EP.assessments)).data
}

export async function getAssessment(eventId: number): Promise<AssessmentDto | null> {
  return (await api.get<{ assessment: AssessmentDto | null }>(EP.assessment(eventId))).data.assessment
}

export type AssessmentInput = Pick<Required<AssessmentDto>, 'pain' | 'swelling' | 'tenderness' | 'rom' | 'weight' | 'neuro' | 'notes' | 'imaging' | 'impression' | 'status'>

/** Medical only. Saving marks the event reviewed, except "Under observation". */
export async function saveAssessment(eventId: number, v: AssessmentInput): Promise<{ assessment: AssessmentDto; resolved: boolean }> {
  return (await api.put<{ assessment: AssessmentDto; resolved: boolean }>(EP.assessment(eventId), v)).data
}

export async function resolveEvent(eventId: number): Promise<void> {
  await api.patch(EP.resolve(eventId))
}

/** Medical only: put a reviewed event back in the review queue. */
export async function reopenEvent(eventId: number): Promise<void> {
  await api.patch(EP.reopen(eventId))
}

/** Alerts this user has read. */
export async function getAlertReads(): Promise<number[]> {
  return (await api.get<{ event_ids: number[] }>(EP.alertReads)).data.event_ids
}

export async function markAlertsRead(ids: number[]): Promise<number[]> {
  return (await api.post<{ event_ids: number[] }>(EP.alertReads, { event_ids: ids })).data.event_ids
}

/** The detector's live progress (every role). */
export async function getDetectorProgress(): Promise<DetectorProgressDto> {
  return (await api.get<DetectorProgressDto>(EP.detector)).data
}

export async function getPlayerPhotos(playerId: number): Promise<PlayerPhotosDto> {
  return (await api.get<PlayerPhotosDto>(EP.photos(playerId))).data
}

/** Photos need the login token, so they are loaded as a blob and shown with an object URL. */
export async function getPlayerPhotoBlob(playerId: number, name: string): Promise<Blob> {
  return (await api.get<Blob>(EP.photo(playerId, name), { responseType: 'blob' })).data
}

export async function uploadPlayerPhoto(playerId: number, file: File): Promise<void> {
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result))
    r.onerror = () => reject(new Error(`Could not read ${file.name}`))
    r.readAsDataURL(file)
  })
  await api.post(EP.photos(playerId), { filename: file.name, data_base64: dataUrl }, { timeout: 60000 })
}

export async function deletePlayerPhoto(playerId: number, name: string): Promise<void> {
  await api.delete(EP.photo(playerId, name))
}

/* ---------- previous injury history ---------- */

export type InjuryHistoryInput = { injury: string; body_area: string; injury_date: string; severity: string; status: string; days_out: number | null; notes: string }

/** Medical/admin: every player. Coach: own team. */
export async function getInjuryHistory(): Promise<InjuryHistoryDto[]> {
  return (await api.get<InjuryHistoryDto[]>(EP.injuryHistory)).data
}

/** Coach (own team) or admin. */
export async function addInjuryHistory(playerId: number, v: InjuryHistoryInput): Promise<InjuryHistoryDto> {
  return (await api.post<{ record: InjuryHistoryDto }>(EP.playerInjuryHistory(playerId), v)).data.record
}

export async function updateInjuryHistory(id: number, v: InjuryHistoryInput): Promise<InjuryHistoryDto> {
  return (await api.put<{ record: InjuryHistoryDto }>(EP.injuryRecord(id), v)).data.record
}

export async function deleteInjuryHistory(id: number): Promise<void> {
  await api.delete(EP.injuryRecord(id))
}