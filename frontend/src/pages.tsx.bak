import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { Link, Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Shield, Eye, EyeOff, Plus, Play, Pause, Square, RotateCcw, Maximize, Upload, VideoOff, CheckCheck, Download, RefreshCw, WifiOff, Lock, FileQuestion, ServerCrash, Cpu, ChevronRight, ChevronDown, ClipboardPlus, Trash2, Sparkles, UserCheck, History, ExternalLink, ImageOff, CheckCircle2, Pencil, Loader2, Activity, Bell, Zap, FileText, CalendarDays, Users, HeartPulse, type LucideIcon } from 'lucide-react'
import { useAuth, home } from './auth'
import { addInjuryHistory, assignPlayer, clearAllEvents, createUser, deleteInjuryHistory, deletePlayerPhoto, deleteUser, getAssessment, getMe, getPlayerPhotoBlob, getPlayerPhotos, getSystemStatus, getUsers, logManualEvent, markAlertsRead, reopenEvent, resolveEvent, saveAssessment, updateInjuryHistory, uploadPlayerPhoto, type AssessmentInput, type InjuryHistoryInput } from './api/services'
import { normalizeApiError } from './api/client'
import type { AppUser } from './api/mappers'
import type { AssessmentDto, DetectorInfoDto, DetectorProgressDto, InjuryHistoryDto, SystemDto } from './api/dto'
import { useAlertReads, useAssessments, useDetector, useEvents, useInjuryHistory, useMatches, usePlayers, useTeams } from './queries'
import { dateOptions } from './prefs'
import type { InjuryEvent, Player, RiskLevel, Role } from './types'
import { safetyMeasures, SAFETY_DISCLAIMER } from './safety'
import { Badge, Card, Confirm, Disclaimer, EmptyState, ErrorState, Field, IdentityBadge, Modal, Na, PageHeader, RiskBadge, SafetyMeasures, Skeleton, btn, btnD, btnP, btnS, inp, inpAuto, useToast, type Tone } from './ui'

/** Small outlined button used instead of text links */
export const btnSm = `${btnS} !gap-1.5 !px-2.5 !py-1 !text-xs`

/** Shown when a button needs something the backend doesn't have yet. */
const NC = "Not available yet: the backend doesn't support this. Nothing was saved."

/* ---------- HELPERS ---------- */

const METHOD_LABELS: Record<string, string> = {
  jersey: 'Jersey number',
  jersey_name: 'Name on shirt',
  jersey_history: 'Jersey (before fall)',
  jersey_handoff: 'Jersey (tracked)',
  face: 'Face',
  gemini: 'Gemini (jersey)',
  manual: 'Manual',
}

/** e.g. "Face · 91%" */
export const identText = (e: InjuryEvent) => {
  if (!e.identified || !e.identifiedBy) return null
  let t = METHOD_LABELS[e.identifiedBy] ?? e.identifiedBy
  if (e.player.identityConfidence !== null) t += ` · ${Math.round(e.player.identityConfidence * 100)}%`
  return t
}

/** Seconds into the video -> "0:12:05" */
export const fmtVideo = (s: number | null) => {
  if (s === null || s === undefined) return null
  const x = Math.floor(s)
  return `${Math.floor(x / 3600)}:${String(Math.floor((x % 3600) / 60)).padStart(2, '0')}:${String(x % 60).padStart(2, '0')}`
}
export const fmtDate = (v: string | null) => (v ? new Date(v).toLocaleString(undefined, dateOptions()) : '—')
const fileName = (p: string | null) => (p ? p.split(/[\\/]/).pop() ?? p : '—')

const geminiBadge = (e: InjuryEvent): { text: string; tone: Tone } | null => {
  const v = e.gemini.verdict
  // the injury check's yes/no decision is not shown: only its possible injuries and rest
  if (!v || e.aiInjury || v === 'jersey_only') return null
  const pct = e.gemini.confidence !== null ? ` · ${Math.round(e.gemini.confidence * 100)}%` : ''
  if (v === 'real_fall') return { text: `Gemini: real fall${pct}`, tone: 'green' }
  if (v === 'false_alarm') return { text: `Gemini: false alarm?${pct}`, tone: 'red' }
  if (v === 'unsure') return { text: `Gemini: unsure${pct}`, tone: 'gray' }
  return { text: 'Gemini: not checked', tone: 'gray' }
}

/** Gemini read a different shirt number than the stored player */
const geminiDisagrees = (e: InjuryEvent) => {
  if (e.gemini.jersey === null || e.identifiedBy === 'gemini') return false
  return !e.identified || e.gemini.jersey !== e.player.jersey
}

/** Gemini's possible injuries as one line, e.g. "Hamstring strain, Calf strain · rest 1-8+ weeks".
 *  Falls back to the detector's own note when Gemini has not reviewed the clip (yet). */
export const injuryText = (e: InjuryEvent) =>
  e.aiInjury ? `${e.aiInjury.injuries.map((i) => i.injury).join(', ')}${e.aiInjury.rest ? ` · rest ${e.aiInjury.rest}` : ''}` : (e.injuryNote ?? e.note ?? null)

/** Catalog risk (Low ... Critical) -> badge colour */
const CATALOG_RISK_TONE: Record<string, Tone> = { Low: 'green', 'Low-Medium': 'green', Medium: 'amber', 'Medium-High': 'orange', High: 'red', Critical: 'red' }

/** Possible injuries from Gemini's review of the clip, with risk, first step and rest time (values from the injury catalog). */
export function PossibleInjuries({ e, compact = false }: { e: InjuryEvent; compact?: boolean }) {
  const a = e.aiInjury
  if (!a) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
        <p className="text-xs font-semibold uppercase tracking-wide">Possible injury</p>
        <p>{e.injuryNote ?? e.note ?? 'No injury note'}</p>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-950">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-amber-900">Possible injuries</p>
        {a.rest && <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-amber-900 ring-1 ring-amber-200"><CalendarDays size={12} />Expected rest {a.rest}</span>}
      </div>
      {a.description && <p className="mt-1 text-xs text-amber-900">{a.description}</p>}
      <ul className="mt-2 space-y-1.5">
        {a.injuries.map((i, k) => (
          <li key={i.injury} className="rounded-lg bg-white/80 px-2.5 py-2">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <span className="font-semibold">{i.injury}</span>
              <span className="text-xs text-slate-500">{i.bodyArea}</span>
              {k === 0 && a.injuries.length > 1 && <Badge tone="blue">Most likely</Badge>}
              {i.risk && <Badge tone={CATALOG_RISK_TONE[i.risk] ?? 'gray'}>{i.risk}</Badge>}
              <span className="ml-auto text-xs font-semibold text-slate-700">Rest {i.rest ?? '—'}</span>
            </div>
            {!compact && i.safetyMeasure && <p className="mt-0.5 text-xs text-slate-600">First step: {i.safetyMeasure}</p>}
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-amber-800">AI estimate from the clip, not a medical diagnosis. Return to play is a medical decision.</p>
    </div>
  )
}

const canChangeAny = (r: Role) => r === 'MEDICAL' || r === 'ADMIN'
/** Everyone can name an Unidentified fall; only medical/admin can change an identified one. */
const canAssign = (r: Role, e: InjuryEvent) => canChangeAny(r) || !e.identified

const playerLabel = (p?: Player) => (p ? `${p.name} (#${p.jersey}${p.teamName ? ', ' + p.teamName : ''})` : 'the player')

const useRefreshAll = () => {
  const qc = useQueryClient()
  return () => { qc.invalidateQueries({ queryKey: ['events'] }); qc.invalidateQueries({ queryKey: ['teams'] }) }
}

/* ---------- SHARED PIECES ---------- */

/** <select> of all players, grouped by team */
function PlayerSelect({ players, value, onChange, label = 'Player' }: { players: Player[]; value: string; onChange: (v: string) => void; label?: string }) {
  const groups: { name: string; players: Player[] }[] = []
  ;[...players].sort((a, b) => a.teamId - b.teamId || a.jersey - b.jersey).forEach((p) => {
    const name = p.teamName ?? `Team ${p.teamId}`
    const g = groups.find((x) => x.name === name)
    if (g) g.players.push(p)
    else groups.push({ name, players: [p] })
  })
  return (
    <select aria-label={label} className={inp} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Select player…</option>
      {groups.map((g) => (
        <optgroup key={g.name} label={g.name}>
          {g.players.map((p) => <option key={p.id} value={p.id}>#{p.jersey} {p.name}</option>)}
        </optgroup>
      ))}
    </select>
  )
}

/** "Who fell?" — pick the player after watching the clip. */
function IdentifyPanel({ ev, onSaved }: { ev: InjuryEvent; onSaved: (e: InjuryEvent | null) => void }) {
  const { user } = useAuth()
  const players = usePlayers().data ?? []
  const toast = useToast()
  const refresh = useRefreshAll()
  const [choice, setChoice] = useState(ev.player.playerId ? String(ev.player.playerId) : '')
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const save = async () => {
    if (!choice) { setErr('Pick a player first.'); return }
    setSaving(true); setErr('')
    try {
      const updated = await assignPlayer(ev.id, Number(choice))
      toast(`Saved: ${playerLabel(players.find((p) => String(p.id) === choice))}`)
      onSaved(updated)
      refresh()
    } catch (e) {
      setErr(normalizeApiError(e))
      refresh() // someone else may have identified it already
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={`rounded-2xl border p-5 shadow-sm ${ev.identified ? 'border-slate-200 bg-white' : 'border-orange-300 bg-orange-50'}`}>
      <h2 className="flex items-center gap-2 font-semibold"><UserCheck size={18} />{ev.identified ? 'Wrong player? Pick the right one' : 'Who fell? Watch the clip and pick the player'}</h2>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <div className="flex-1"><PlayerSelect players={players} value={choice} onChange={(v) => { setChoice(v); setErr('') }} /></div>
        <button className={btnP + ' justify-center'} disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save player'}</button>
      </div>
      {err && <p role="alert" className="mt-2 text-sm text-red-700">{err}</p>}
      {user && !canChangeAny(user.role) && <p className="mt-2 text-xs text-slate-500">Once saved, only medical staff or admin can change it.</p>}
    </div>
  )
}

/** Dropdown under a player row: every fall for that player (all matches) with clip, possible injury and safety measures. */
function PlayerHistory({ playerId, name }: { playerId: number; name: string }) {
  const q = useEvents()
  if (q.isLoading) return <div className="space-y-2 p-4"><Skeleton /><Skeleton /></div>
  const list = (q.data ?? []).filter((e) => e.player.playerId === playerId).sort((a, b) => +new Date(b.timestamp) - +new Date(a.timestamp))
  const high = list.filter((e) => e.risk === 'HIGH').length
  return (
    <div className="border-l-4 border-sky-500 bg-slate-50 p-4">
      <PreviousInjuries playerId={playerId} name={name} />
      <h3 className="mb-2 mt-5 text-sm font-semibold text-slate-700">Detected falls</h3>
      {!list.length ? <p className="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">No injury events recorded for {name}.</p> : <>
      <p className="mb-3 text-sm text-slate-600">
        <b className="text-slate-900">{name}</b> · {list.length} event{list.length === 1 ? '' : 's'}
        {high > 0 && <span className="font-semibold text-red-700"> · {high} high risk</span>} · latest {fmtDate(list[0].timestamp)}
      </p>
      {/* One full-width card per fall: clip on the left, details on the right (stacked on small screens) */}
      <div className="space-y-3">
        {list.map((e) => (
          <div key={e.id} className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
            <div>
              {e.clipUrl ? (
                <video className="aspect-video w-full rounded-xl bg-black" src={e.clipUrl} controls preload="metadata" />
              ) : (
                <div className="grid aspect-video place-items-center rounded-xl bg-slate-100 text-sm text-slate-500">{e.source === 'manual' ? 'Logged by staff — no video' : 'No clip saved for this event'}</div>
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="blue">{e.eventType}</Badge>
                <RiskBadge level={e.risk} />
                <span className="text-sm font-semibold text-slate-600">{e.region ?? 'Body area not recorded'}</span>
                <span className="ml-auto"><Badge tone={e.resolved ? 'green' : 'gray'}>{e.resolved ? 'Resolved' : 'Pending'}</Badge></span>
              </div>
              <PossibleInjuries e={e} compact />
              <SafetyMeasures eventType={e.eventType} region={e.region} risk={e.risk} />
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
                <dt className="text-slate-500">Match</dt><dd className="truncate" title={e.matchName ?? ''}>{e.matchName ?? 'No match'}</dd>
                <dt className="text-slate-500">Time in video</dt><dd><Na v={fmtVideo(e.videoTimeSec)} /></dd>
                <dt className="text-slate-500">Recorded</dt><dd>{fmtDate(e.timestamp)}</dd>
                <dt className="text-slate-500">Identified by</dt><dd title={e.idDetail ?? ''}><Na v={identText(e)} /></dd>
                {geminiBadge(e) && <><dt className="text-slate-500">Gemini</dt><dd>{geminiBadge(e)!.text}</dd></>}
              </dl>
              <div className="mt-auto flex flex-wrap gap-2">
                <Link to={`/events/${e.id}`} className={btnSm}><ExternalLink size={14} />Open event</Link>
                {e.clipUrl && <a href={e.clipUrl} download className={btnSm}><Download size={14} />Download clip</a>}
              </div>
            </div>
          </div>
        ))}
      </div>
      </>}
    </div>
  )
}

/** Clickable player name that opens/closes the history dropdown */
const PlayerToggle = ({ open, onClick, children }: { open: boolean; onClick: () => void; children: ReactNode }) => (
  <button aria-expanded={open} onClick={onClick} title="Show this player's injury history" className="inline-flex items-center gap-1 text-left font-medium hover:text-blue-700">
    {open ? <ChevronDown size={14} className="text-sky-600" /> : <ChevronRight size={14} className="text-sky-600" />}
    {children}
  </button>
)

/* ---------- PREVIOUS INJURY HISTORY (typed in by a coach for their own team, or admin). Saved in output/injury_history.json ---------- */
const HISTORY_AREAS = ['Head', 'Neck', 'Shoulder', 'Arm', 'Elbow', 'Wrist / Hand', 'Chest', 'Back', 'Hip / Groin', 'Thigh', 'Hamstring', 'Knee', 'Lower leg', 'Ankle', 'Foot', 'Other']
const HISTORY_SEVERITY = ['Minor', 'Moderate', 'Severe']
const HISTORY_STATUS = ['Recovered', 'Recovering', 'Ongoing']
const SEVERITY_TONE: Record<string, Tone> = { Minor: 'green', Moderate: 'amber', Severe: 'red' }
const HSTATUS_TONE: Record<string, Tone> = { Recovered: 'green', Recovering: 'amber', Ongoing: 'red' }
const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
const fmtDay = (iso: string) => { const d = new Date(iso + 'T00:00:00'); return isNaN(+d) ? iso : d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' }) }

/** Admin edits every player; a coach edits their own team. */
const canEditHistory = (u: { role: Role; teamId: number | null; dev?: boolean } | null, p?: { teamId: number }) =>
  !!u && !u.dev && !!p && (u.role === 'ADMIN' || (u.role === 'COACH' && u.teamId === p.teamId))

const hs = z.object({
  playerId: z.string().min(1, 'Player is required'),
  injury: z.string().trim().min(1, 'Injury is required').max(120, 'Keep it under 120 characters'),
  body_area: z.string().min(1, 'Body area is required'),
  injury_date: z.string().min(1, 'Date is required').refine((v) => v <= todayISO(), 'The date cannot be in the future'),
  severity: z.string().min(1, 'Severity is required'),
  status: z.string().min(1, 'Status is required'),
  days_out: z.string().refine((v) => v.trim() === '' || (/^\d+$/.test(v.trim()) && Number(v) <= 1000), 'Enter a number from 0 to 1000'),
  notes: z.string().max(1000, 'Keep it under 1000 characters'),
})
type HistoryForm = z.infer<typeof hs>

function InjuryHistoryModal({ onClose, players, playerId, record }: { onClose: () => void; players: Player[]; playerId?: number; record?: InjuryHistoryDto }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [err, setErr] = useState('')
  const fixed = record?.player_id ?? playerId
  const f = useForm<HistoryForm>({
    resolver: zodResolver(hs),
    defaultValues: record
      ? { playerId: String(record.player_id), injury: record.injury, body_area: record.body_area, injury_date: record.injury_date, severity: record.severity, status: record.status, days_out: record.days_out === null || record.days_out === undefined ? '' : String(record.days_out), notes: record.notes ?? '' }
      : { playerId: fixed ? String(fixed) : '', injury: '', body_area: '', injury_date: '', severity: '', status: '', days_out: '', notes: '' },
  })
  const submit = f.handleSubmit(async (v) => {
    setErr('')
    const body: InjuryHistoryInput = { injury: v.injury.trim(), body_area: v.body_area, injury_date: v.injury_date, severity: v.severity, status: v.status, days_out: v.days_out.trim() === '' ? null : Number(v.days_out), notes: v.notes.trim() }
    try {
      if (record) await updateInjuryHistory(record.id, body)
      else await addInjuryHistory(Number(v.playerId), body)
      qc.invalidateQueries({ queryKey: ['injuryHistory'] })
      const p = players.find((x) => String(x.id) === v.playerId)
      toast(record ? `Injury updated for ${p?.name ?? 'the player'}.` : `Injury added to ${p?.name ?? 'the player'}'s history.`)
      onClose()
    } catch (x) { setErr(normalizeApiError(x)) }
  })
  const E = (n: keyof HistoryForm) => f.formState.errors[n]?.message
  const fixedPlayer = players.find((x) => x.id === fixed)
  return (
    <Modal open title={record ? 'Edit previous injury' : 'Add previous injury'} onClose={onClose}>
      <form className="grid gap-3 sm:grid-cols-2" noValidate onSubmit={submit}>
        <div className="sm:col-span-2">
          {fixed ? <p className="rounded-lg bg-slate-50 p-3 text-sm">Player: <b>{fixedPlayer ? `${fixedPlayer.name} #${fixedPlayer.jersey}` : record?.player_name ?? `#${fixed}`}</b></p>
            : <Field label="Player *" err={E('playerId')}><select className={inp} {...f.register('playerId')}><option value="">Select…</option>{players.map((p) => <option key={p.id} value={p.id}>{p.name} (#{p.jersey})</option>)}</select></Field>}
        </div>
        <div className="sm:col-span-2"><Field label="Injury *" err={E('injury')}><input className={inp} placeholder="e.g. Hamstring strain, ACL tear, ankle sprain" {...f.register('injury')} /></Field></div>
        <Field label="Body area *" err={E('body_area')}><select className={inp} {...f.register('body_area')}><option value="">Select…</option>{HISTORY_AREAS.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Date of injury *" err={E('injury_date')}><input type="date" max={todayISO()} className={inp} {...f.register('injury_date')} /></Field>
        <Field label="Severity *" err={E('severity')}><select className={inp} {...f.register('severity')}><option value="">Select…</option>{HISTORY_SEVERITY.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Current status *" err={E('status')}><select className={inp} {...f.register('status')}><option value="">Select…</option>{HISTORY_STATUS.map((x) => <option key={x}>{x}</option>)}</select></Field>
        <Field label="Days out of play" err={E('days_out')}><input inputMode="numeric" className={inp} placeholder="Optional" {...f.register('days_out')} /></Field>
        <div className="sm:col-span-2"><Field label="Notes" err={E('notes')}><textarea rows={3} className={inp} placeholder="Treatment, surgery, return-to-play notes…" {...f.register('notes')} /></Field></div>
        {err && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800 sm:col-span-2">{err}</p>}
        <div className="flex justify-end gap-2 sm:col-span-2"><button type="button" className={btnS} onClick={onClose}>Cancel</button><button className={btnP} disabled={f.formState.isSubmitting}>{f.formState.isSubmitting ? 'Saving…' : record ? 'Save changes' : 'Add injury'}</button></div>
      </form>
    </Modal>
  )
}

/** One card per previous injury, newest first, with edit/delete for coach (own team) and admin. */
function InjuryRecordList({ records, players, emptyText }: { records: InjuryHistoryDto[]; players: Player[]; emptyText: string }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [editing, setEditing] = useState<InjuryHistoryDto | null>(null)
  const [removing, setRemoving] = useState<InjuryHistoryDto | null>(null)
  const remove = async (r: InjuryHistoryDto) => {
    try { await deleteInjuryHistory(r.id); qc.invalidateQueries({ queryKey: ['injuryHistory'] }); toast('Injury removed from the history.') } catch (x) { toast(normalizeApiError(x), true) }
  }
  if (!records.length) return <p className="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">{emptyText}</p>
  return (
    <>
      <ul className="space-y-2">
        {records.map((r) => (
          <li key={r.id} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center gap-2">
              <p className="font-semibold">{r.injury}</p>
              <span className="text-sm text-slate-500">· {r.body_area}</span>
              <Badge tone={SEVERITY_TONE[r.severity] ?? 'gray'}>{r.severity}</Badge>
              <Badge tone={HSTATUS_TONE[r.status] ?? 'gray'}>{r.status}</Badge>
              {r.can_edit && <span className="ml-auto flex gap-1">
                <button className={btnSm} onClick={() => setEditing(r)}><Pencil size={14} />Edit</button>
                <button className={btnSm + ' !text-red-700'} onClick={() => setRemoving(r)}><Trash2 size={14} />Delete</button>
              </span>}
            </div>
            <p className="mt-1 text-xs text-slate-500">{fmtDay(r.injury_date)}{r.days_out !== null && r.days_out !== undefined ? ` · ${r.days_out} day${r.days_out === 1 ? '' : 's'} out` : ''} · added by {r.added_by}{r.updated_by ? ` · edited by ${r.updated_by}` : ''}</p>
            {r.notes && <p className="mt-1 text-sm text-slate-700">{r.notes}</p>}
          </li>
        ))}
      </ul>
      {editing && <InjuryHistoryModal record={editing} players={players} onClose={() => setEditing(null)} />}
      <Confirm open={!!removing} title="Delete this injury record?" text={removing ? `${removing.injury} (${fmtDay(removing.injury_date)}) will be removed from ${removing.player_name ?? 'the player'}'s history.` : ''} confirmLabel="Delete" onConfirm={() => removing && remove(removing)} onClose={() => setRemoving(null)} />
    </>
  )
}

/** "Previous injury history" block shown above the detected falls in every player dropdown / player page. */
export function PreviousInjuries({ playerId, name }: { playerId: number; name: string }) {
  const { user } = useAuth()
  const players = usePlayers().data ?? []
  const player = players.find((p) => p.id === playerId)
  const coachOther = user?.role === 'COACH' && !!player && player.teamId !== user.teamId
  const h = useInjuryHistory(!coachOther)
  const [adding, setAdding] = useState(false)
  const records = (h.data ?? []).filter((r) => r.player_id === playerId)
  const canEdit = canEditHistory(user, player)
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700"><HeartPulse size={16} className="text-rose-600" />Previous injury history{records.length > 0 && <span className="font-normal text-slate-500">· {records.length} record{records.length === 1 ? '' : 's'}</span>}</h3>
        {canEdit && <button className={btnSm + ' ml-auto'} onClick={() => setAdding(true)}><Plus size={14} />Add injury</button>}
      </div>
      {user?.dev ? <p className="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">Log in with a real account to see injury history.</p>
        : coachOther ? <p className="rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">Injury history is only shown for your own team's players.</p>
        : h.isLoading ? <Skeleton />
        : h.isError ? <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800">Could not load injury history: {normalizeApiError(h.error)}</p>
        : <InjuryRecordList records={records} players={players} emptyText={`No previous injuries recorded for ${name}.${canEdit ? ' Use "Add injury" to record one.' : ''}`} />}
      {adding && <InjuryHistoryModal playerId={playerId} players={players} onClose={() => setAdding(false)} />}
    </div>
  )
}

/** Coach dashboard: the team's previous injury history, one row per player. */
function TeamInjuryHistory({ teamId, allTeams = false }: { teamId?: number | null; allTeams?: boolean }) {
  const { user } = useAuth()
  const viewOnly = user?.role === 'MEDICAL'
  const [teamF, setTeamF] = useState('')
  const allPlayers = usePlayers().data ?? []
  const h = useInjuryHistory()
  const ev = useEvents()
  const [open, setOpen] = useState<number | null>(null)
  const [adding, setAdding] = useState(false)
  const [q, setQ] = useState('')
  const [onlyWith, setOnlyWith] = useState(false)
  const team = allTeams ? allPlayers : allPlayers.filter((p) => p.teamId === teamId)
  const teamNames = [...new Set(allPlayers.map((p) => p.teamName ?? '').filter(Boolean))].sort()
  const records = h.data ?? []
  const dev = !!user?.dev
  const statusRank = (s?: string) => (s === 'Ongoing' ? 0 : s === 'Recovering' ? 1 : 2)
  const needle = q.trim().toLowerCase()

  const rows = team.map((p) => {
    const mine = records.filter((r) => r.player_id === p.id)
    const falls = (ev.data ?? []).filter((e) => e.player.playerId === p.id).length
    return { p, mine, latest: mine[0], active: mine.filter((r) => r.status !== 'Recovered').length, falls }
  })
    .filter((r) => !needle || `${r.p.name} ${r.p.jersey}`.toLowerCase().includes(needle))
    .filter((r) => !onlyWith || r.mine.length > 0)
    .filter((r) => !teamF || r.p.teamName === teamF)
    .sort((a, b) => b.active - a.active || statusRank(a.latest?.status) - statusRank(b.latest?.status) || b.mine.length - a.mine.length || a.p.jersey - b.p.jersey)

  const teamRecords = records.filter((r) => team.some((p) => p.id === r.player_id))
  const stats: [string, number, string][] = [
    ['Injury records', teamRecords.length, ''],
    ['Players with history', new Set(teamRecords.map((r) => r.player_id)).size, ''],
    ['Still recovering', teamRecords.filter((r) => r.status === 'Recovering').length, 'text-amber-600'],
    ['Ongoing', teamRecords.filter((r) => r.status === 'Ongoing').length, 'text-red-700'],
  ]

  return (
    <Card className="!p-0">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 p-5">
        <div className="mr-auto">
          <h2 className="flex items-center gap-2 font-semibold"><HeartPulse size={18} className="text-rose-600" />Previous injury history</h2>
          <p className="text-xs text-slate-500">{allTeams ? 'Past injuries of every player.' : 'Past injuries of your players.'} Click a name to see the full history and the falls the detector found.</p>
        </div>
        {viewOnly ? <Badge tone="gray">View only</Badge> : <button className={btnP} disabled={dev || team.length === 0} onClick={() => setAdding(true)}><Plus size={16} />Add injury</button>}
      </div>
      <div className="grid grid-cols-2 gap-3 border-b border-slate-200 p-5 lg:grid-cols-4">
        {stats.map(([l, v, t]) => <div key={l} className="rounded-xl border border-slate-200 p-3"><p className="text-xs text-slate-500">{l}</p>{h.isLoading ? <Skeleton className="mt-2 h-7 w-10" /> : <p className={`mt-1 text-2xl font-bold ${t}`}>{v}</p>}</div>)}
      </div>
      <div className="flex flex-wrap items-center gap-3 px-5 pt-4">
        <input aria-label="Search players" className={inpAuto + ' w-full sm:w-64'} placeholder="Search players…" value={q} onChange={(e) => { setQ(e.target.value); setOpen(null) }} />
        {allTeams && <select aria-label="Filter by team" className={inpAuto} value={teamF} onChange={(e) => { setTeamF(e.target.value); setOpen(null) }}><option value="">All teams</option>{teamNames.map((t) => <option key={t} value={t}>{t}</option>)}</select>}
        <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={onlyWith} onChange={(e) => setOnlyWith(e.target.checked)} />Only players with previous injuries</label>
      </div>
      {dev ? <EmptyState title="No data in preview" text="Log in with a real account to see injury history." />
        : h.isError ? <ErrorState title="Unable to load injury history" text={normalizeApiError(h.error)} onRetry={() => h.refetch()} />
        : (h.isLoading || !allPlayers.length) ? <div className="space-y-2 p-5"><Skeleton /><Skeleton /><Skeleton /></div>
        : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr><th className={th + ' w-16'}>#</th><th className={th}>Player</th>{allTeams && <th className={th}>Team</th>}<th className={th}>Previous injuries</th><th className={th}>Latest injury</th><th className={th}>Status</th><th className={th}>Detected falls</th></tr>
              </thead>
              <tbody>
                {rows.map(({ p, mine, latest, falls }) => (
                  <Fragment key={p.id}>
                    <tr className={`border-t border-slate-100 ${open === p.id ? 'bg-slate-50' : latest && latest.status !== 'Recovered' ? 'bg-amber-50/40 hover:bg-amber-50' : 'hover:bg-slate-50'}`}>
                      <td className="px-4 py-3"><span className="grid h-8 w-8 place-items-center rounded-full bg-slate-100 text-xs font-bold text-slate-700">{p.jersey}</span></td>
                      <td className="px-4 py-3"><PlayerToggle open={open === p.id} onClick={() => setOpen(open === p.id ? null : p.id)}>{p.name}</PlayerToggle></td>
                      {allTeams && <td className="px-4 py-3 text-slate-600">{p.teamName ?? '—'}</td>}
                      <td className="px-4 py-3">{mine.length > 0 ? <span className="font-semibold">{mine.length}</span> : <span className="text-slate-400">0</span>}</td>
                      <td className="px-4 py-3">{latest ? <><p className="font-medium">{latest.injury}</p><p className="text-xs text-slate-500">{latest.body_area} · {fmtDay(latest.injury_date)}</p></> : <span className="text-slate-400">—</span>}</td>
                      <td className="px-4 py-3">{latest ? <Badge tone={HSTATUS_TONE[latest.status] ?? 'gray'}>{latest.status}</Badge> : <span className="text-slate-400">—</span>}</td>
                      <td className="px-4 py-3">{falls > 0 ? <span className="font-semibold">{falls}</span> : <span className="text-slate-400">0</span>}</td>
                    </tr>
                    {open === p.id && <tr><td colSpan={allTeams ? 7 : 6} className="p-0"><PlayerHistory playerId={p.id} name={p.name} /></td></tr>}
                  </Fragment>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <EmptyState title="No players found" text={onlyWith ? (viewOnly ? 'No players with previous injuries yet.' : 'No players with previous injuries yet. Use "Add injury" to record one.') : 'No players match your search.'} />}
          </div>
        )}
      {adding && !viewOnly && <InjuryHistoryModal players={team} onClose={() => setAdding(false)} />}
    </Card>
  )
}

/** Medical staff: log an event by hand */
const ms = z.object({
  playerId: z.string().min(1, 'Player is required'),
  eventType: z.string().trim().min(1, 'Event type is required'),
  risk: z.enum(['LOW', 'MEDIUM', 'HIGH']),
  matchId: z.string(),
  note: z.string().trim().min(1, 'Note is required'),
})
function ManualEventModal({ open, onClose, defaultMatch = '' }: { open: boolean; onClose: () => void; defaultMatch?: string }) {
  const players = usePlayers().data ?? []
  const matches = useMatches().data ?? []
  const toast = useToast()
  const refresh = useRefreshAll()
  const [err, setErr] = useState('')
  const f = useForm<z.infer<typeof ms>>({ resolver: zodResolver(ms), defaultValues: { playerId: '', eventType: '', risk: 'MEDIUM', matchId: defaultMatch, note: '' } })
  const playerId = f.watch('playerId')
  const submit = f.handleSubmit(async (v) => {
    setErr('')
    try {
      await logManualEvent({ playerId: Number(v.playerId), eventType: v.eventType, note: v.note, risk: v.risk as RiskLevel, matchId: v.matchId ? Number(v.matchId) : null })
      toast('Event logged.')
      f.reset({ playerId: '', eventType: '', risk: 'MEDIUM', matchId: defaultMatch, note: '' })
      refresh()
      onClose()
    } catch (e) {
      setErr(normalizeApiError(e))
    }
  })
  return (
    <Modal open={open} title="Log manual event" onClose={onClose}>
      <form className="space-y-3" noValidate onSubmit={submit}>
        <Field label="Player *" err={f.formState.errors.playerId?.message}>
          <PlayerSelect players={players} value={playerId} onChange={(v) => f.setValue('playerId', v, { shouldValidate: true })} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Event type *" err={f.formState.errors.eventType?.message}><input className={inp} placeholder="e.g. TWISTED_ANKLE" {...f.register('eventType')} /></Field>
          <Field label="Risk level"><select className={inp} {...f.register('risk')}><option>LOW</option><option>MEDIUM</option><option>HIGH</option></select></Field>
        </div>
        <Field label="Match"><select className={inp} {...f.register('matchId')}><option value="">No match</option>{matches.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
        <Field label="Note *" err={f.formState.errors.note?.message}><textarea rows={3} className={inp} placeholder="Describe the event…" {...f.register('note')} /></Field>
        {err && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{err}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className={btnS} onClick={onClose}>Cancel</button>
          <button className={btnP} disabled={f.formState.isSubmitting}>{f.formState.isSubmitting ? 'Saving…' : 'Log event'}</button>
        </div>
      </form>
    </Modal>
  )
}

/* ---------- AUTH ---------- */
const ls = z.object({ username: z.string().min(1, 'Username or email is required'), password: z.string().min(1, 'Password is required') })
export function Login() {
  const { login, devPreview, user } = useAuth()
  const nav = useNavigate()
  const [show, setShow] = useState(false)
  const [err, setErr] = useState('')
  const [forgot, setForgot] = useState(false)
  const [sent, setSent] = useState(false)
  const f = useForm<z.infer<typeof ls>>({ resolver: zodResolver(ls) })
  if (user) return <Navigate to={home[user.role]} replace />
  const go = f.handleSubmit(async (v) => {
    setErr('')
    try {
      const u = await login(v.username, v.password)
      nav(home[u.role], { replace: true })
    } catch (e) {
      setErr(normalizeApiError(e))
    }
  })
  return (
    <div className="grid min-h-screen place-items-center bg-[#0b1f3a] p-4"><div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
      <div className="mb-6 text-center"><Shield className="mx-auto text-sky-600" size={40} /><h1 className="mt-2 text-2xl font-bold">AthleteGuard</h1><p className="text-sm text-slate-500">AI-Powered Football Injury Detection &amp; Medical Decision Support</p></div>
      {forgot ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">Enter your email and an administrator-approved reset link will be sent when password reset is enabled.</p>
          <input className={inp} type="email" placeholder="Email" aria-label="Email" />
          {sent && <p className="text-sm text-amber-700">Password reset is not available yet. Ask your administrator to reset your password.</p>}
          <button className={btnP + ' w-full justify-center'} onClick={() => setSent(true)}>Send reset link</button>
          <button className={btnS + ' w-full justify-center'} onClick={() => { setForgot(false); setSent(false) }}>Back to login</button>
        </div>
      ) : (
        <form onSubmit={go} className="space-y-4" noValidate>
          {err && <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{err}</div>}
          <Field label="Username or email" err={f.formState.errors.username?.message}><input className={inp} autoComplete="username" {...f.register('username')} /></Field>
          <Field label="Password" err={f.formState.errors.password?.message}><div className="relative"><input className={inp} type={show ? 'text' : 'password'} autoComplete="current-password" {...f.register('password')} /><button type="button" aria-label={show ? 'Hide password' : 'Show password'} className="absolute right-3 top-2.5 text-slate-500" onClick={() => setShow((s) => !s)}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></Field>
          <button className={btnP + ' w-full justify-center'} disabled={f.formState.isSubmitting}>{f.formState.isSubmitting ? 'Signing in…' : 'Sign in'}</button>
          <button type="button" className={btnS + ' w-full justify-center'} onClick={() => setForgot(true)}>Forgot password?</button>
        </form>
      )}
      <div className="mt-6 border-t pt-4"><p className="mb-2 flex items-center gap-2 text-xs font-semibold text-amber-800"><Badge tone="amber">DEV</Badge>Developer preview (no backend, no data)</p><div className="grid grid-cols-3 gap-2">{(['ADMIN', 'MEDICAL', 'COACH'] as Role[]).map((r) => <button key={r} className={btnS + ' justify-center'} onClick={() => { devPreview(r); nav(home[r]) }}>{r.charAt(0) + r.slice(1).toLowerCase()}</button>)}</div></div>
    </div></div>
  )
}

/* ---------- DASHBOARDS ---------- */
export function EventLine({ e, to }: { e: InjuryEvent; to?: string }) {
  const g = geminiBadge(e)
  return (
    <li>
      <Link to={to ?? `/events/${e.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-slate-50">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{e.player.name ? `${e.player.name} #${e.player.jersey ?? '?'}` : 'Unidentified player'}<span className="ml-2 text-slate-400">{e.eventType}</span></p>
          <p className="truncate text-xs text-slate-500">{e.region ?? '—'} · {e.matchName ?? 'No match'}{fmtVideo(e.videoTimeSec) && ` · ${fmtVideo(e.videoTimeSec)} in video`}</p>
          {e.aiInjury ? <p className="truncate text-xs text-slate-600" title={e.aiInjury.description ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{injuryText(e)}</p>
            : e.gemini.description && <p className="truncate text-xs text-slate-600" title={e.gemini.reason ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{e.gemini.description}</p>}
        </div>
        {g && <span className="hidden sm:inline-flex" title={e.gemini.reason ?? ''}><Badge tone={g.tone}>{g.text}</Badge></span>}
        <RiskBadge level={e.risk} />
        <ChevronRight size={16} className="text-slate-400" />
      </Link>
    </li>
  )
}

const QA: Record<Role, [string, string][]> = {
  ADMIN: [['Add team', '/teams'], ['Register player', '/teams'], ['System status', '/admin/system']],
  COACH: [['My team', '/teams'], ['View matches', '/matches'], ['View alerts', '/alerts']],
  MEDICAL: [['Review queue', '/events'], ['Collisions', '/collisions'], ['Reports', '/reports']],
  PLAYER: [],
}
/** Label on top of each dashboard KPI card (same on every dashboard) */
export const kpiLabel = 'text-sm font-semibold text-blue-700'
/** KPI cards fill the full width whatever their count (Tailwind needs the full class names written out) */
const KPI_COLS: Record<number, string> = { 4: 'lg:grid-cols-4', 5: 'lg:grid-cols-5', 6: 'lg:grid-cols-3 xl:grid-cols-6' }
const byRisk = (a: InjuryEvent, b: InjuryEvent) => ['HIGH', 'MEDIUM', 'LOW'].indexOf(a.risk ?? 'LOW') - ['HIGH', 'MEDIUM', 'LOW'].indexOf(b.risk ?? 'LOW')

export function Dashboard({ role }: { role: Role }) {
  const { user } = useAuth()
  const ev = useEvents()
  const teams = useTeams()
  const players = usePlayers()
  const assessments = useAssessments(role === 'MEDICAL')
  const toast = useToast()
  const refresh = useRefreshAll()
  const [confirmClear, setConfirmClear] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const dev = !!user?.dev

  const list = ev.data ?? []
  const open = list.filter((e) => !e.resolved)
  const unidentified = list.filter((e) => !e.identified)
  const myTeam = role === 'COACH' ? (teams.data ?? [])[0] : undefined

  // Same KPI cards as the design; "—" where the backend has no data for it.
  const KPI: Record<Role, [string, number | string | null, string?][]> = {
    ADMIN: [['Total teams', teams.data?.length ?? null], ['Total players', players.data?.length ?? null], ['Total incidents', ev.data ? list.length : null], ['High-risk incidents', ev.data ? list.filter((e) => e.risk === 'HIGH').length : null, 'text-red-700'], ['Pending medical reviews', ev.data ? open.length : null, 'text-amber-600']],
    COACH: [['Players in my team', myTeam?.playerCount ?? null], ['Recent incidents', myTeam?.injuryEvents ?? null], ['High-risk alerts', myTeam?.highRiskEvents ?? null, 'text-red-700'], ['Players needing attention', myTeam ? myTeam.players.filter((p) => p.highRiskEvents > 0).length : null, 'text-amber-600']],
    MEDICAL: [['Pending reviews', ev.data ? open.length : null], ['High priority', ev.data ? open.filter((e) => e.risk === 'HIGH').length : null, 'text-red-700'], ['Medium priority', ev.data ? open.filter((e) => e.risk === 'MEDIUM').length : null, 'text-amber-600'], ['Low priority', ev.data ? open.filter((e) => e.risk === 'LOW').length : null, 'text-green-700'], ['Assessments saved', assessments.data ? assessments.data.length : null]],
    PLAYER: [],
  }

  const clearAll = async () => {
    try { toast(`Deleted ${await clearAllEvents()} events. Players were kept.`); refresh() } catch (e) { toast(normalizeApiError(e), true) }
  }

  const incidents = role === 'MEDICAL' ? [...open].sort(byRisk) : list
  const highList = list.filter((e) => e.risk === 'HIGH')

  const recentAlerts = (
    <Card>
      <h2 className="font-semibold">Recent alerts</h2>
      {highList.length === 0 ? <EmptyState title="No alerts" />
        : <ul className="mt-2 divide-y divide-slate-100">{highList.slice(0, 4).map((e) => <EventLine key={e.id} e={e} />)}</ul>}
    </Card>
  )
      return (
    <>
      <PageHeader back={false} title={`${role.charAt(0) + role.slice(1).toLowerCase()} dashboard`} crumbs={[{ label: 'Dashboard' }]}
        actions={role !== 'ADMIN' && <>
          <Link to="/reports" className={btnS}><FileText size={16} />Reports</Link>
          {role === 'MEDICAL' && <button className={btnP} disabled={dev} onClick={() => setLogOpen(true)}><ClipboardPlus size={16} />Log manual event</button>}
        </>} />
      <div className={`grid grid-cols-2 gap-3 ${KPI_COLS[KPI[role].length] ?? 'lg:grid-cols-3 xl:grid-cols-6'}`}>
        {KPI[role].map(([k, v, t]) => <Card key={k}><p className={kpiLabel}>{k}</p>{ev.isLoading ? <Skeleton className="mt-2 h-8 w-12" /> : <p className={`mt-1 truncate font-bold ${typeof v === 'string' ? 'text-lg' : 'text-3xl'} ${t ?? ''}`} title={typeof v === 'string' ? v : undefined}><Na v={v} /></p>}</Card>)}
      </div>
      {dev && <p className="mt-2 text-xs text-slate-500">Metrics are shown only when real backend data is available.</p>}
      {role === 'COACH' && !dev && <p className="mt-2 text-xs text-slate-500">You see your team's events and every unidentified fall.</p>}

      {role === 'ADMIN' ? (
        <>
          {/* Admin: Recent incidents across the full width */}
          <div className="mt-5">
            <Card>
              <div className="flex items-center justify-between"><h2 className="font-semibold">Recent incidents</h2>{incidents.length > 0 && <Link to="/events" className={btnSm}>View all</Link>}</div>
              {ev.isError ? <ErrorState title="Unable to load incidents" text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} />
                : ev.isLoading ? <div className="mt-3 space-y-2"><Skeleton /><Skeleton /></div>
                : incidents.length === 0 ? <EmptyState title="No incidents yet" text="Detected incidents will appear here after a match video has been analyzed." />
                : <ul className="mt-2 divide-y divide-slate-100">{incidents.slice(0, 6).map((e) => <EventLine key={e.id} e={e} />)}</ul>}
            </Card>
          </div>
          {/* Below: Recent alerts (left) | Admin controls over Quick actions (right) */}
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {recentAlerts}
            <div className="flex flex-col gap-4">
              <Card>
                <h2 className="font-semibold">Admin controls</h2>
                <p className="mt-2 text-sm text-slate-500">Permanently delete every injury event. Players and teams are kept.</p>
                <button className={btnD + ' mt-3 w-full justify-center'} disabled={dev} onClick={() => setConfirmClear(true)}><Trash2 size={16} />Delete all injury events</button>
              </Card>
              <Card className="flex-1">
                <h2 className="font-semibold">Quick actions</h2>
                <div className="mt-3 flex flex-wrap gap-2">
                  {QA[role].map(([l, t]) => <Link key={l} to={t} className={btnS}>{l}</Link>)}
                  <Link to="/events?identity=unidentified" className={btnS}>Identify unknown players ({unidentified.length})</Link>
                </div>
              </Card>
            </div>
          </div>
        </>
      ) : (
        <>
          {/* Same layout as the admin dashboard: incidents across the full width */}
          <div className="mt-5">
            <Card>
              <div className="flex items-center justify-between"><h2 className="font-semibold">{role === 'MEDICAL' ? 'Review queue' : 'Recent incidents'}</h2>{incidents.length > 0 && <Link to="/events" className={btnSm}>View all</Link>}</div>
              {ev.isError ? <ErrorState title="Unable to load incidents" text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} />
                : ev.isLoading ? <div className="mt-3 space-y-2"><Skeleton /><Skeleton /></div>
                : incidents.length === 0 ? <EmptyState title={role === 'MEDICAL' ? 'Nothing waiting for review' : 'No incidents yet'} text="Detected incidents will appear here after a match video has been analyzed." />
                : <ul className="mt-2 divide-y divide-slate-100">{incidents.slice(0, 6).map((e) => <EventLine key={e.id} e={e} />)}</ul>}
            </Card>
          </div>
          {/* Coach: previous injury history across the full width */}
          {role === 'COACH' ? <div className="mt-4"><TeamInjuryHistory teamId={user?.teamId ?? myTeam?.id ?? null} /></div> : (
          /* Medical: Recent alerts, then the previous injury history of every player (view only) */
          <>
            <div className="mt-4">{recentAlerts}</div>
            <div className="mt-4"><TeamInjuryHistory allTeams /></div>
          </>
          )}
        </>
      )}
      <Confirm open={confirmClear} title="Delete all injury events?" text="Players and teams are kept. This cannot be undone." confirmLabel="Delete all" onConfirm={clearAll} onClose={() => setConfirmClear(false)} />
      {role === 'MEDICAL' && logOpen && <ManualEventModal open onClose={() => setLogOpen(false)} />}
    </>
  )
}
/* ---------- GENERIC LIST (same layout for every list page) ---------- */
interface Cfg { title: string; crumb: string; filters: { name: string; opts: string[] }[]; create?: { label: string; fields: { n: string; l: string; opts?: string[] }[] } }
const CFG: Record<string, Cfg> = {
  teams: { title: 'Teams', crumb: 'Teams', filters: [{ name: 'Status', opts: ['Active', 'Archived'] }], create: { label: 'Create team', fields: [{ n: 'name', l: 'Team name' }] } },
  players: { title: 'Players', crumb: 'Players', filters: [{ name: 'Team', opts: [] }, { name: 'Position', opts: ['Goalkeeper', 'Defender', 'Midfielder', 'Forward'] }], create: { label: 'Register player', fields: [{ n: 'name', l: 'Player name' }, { n: 'jersey', l: 'Jersey number' }, { n: 'position', l: 'Position', opts: ['Goalkeeper', 'Defender', 'Midfielder', 'Forward'] }] } },
  matches: { title: 'Matches', crumb: 'Matches', filters: [{ name: 'Status', opts: ['Scheduled', 'Processing', 'Completed'] }], create: { label: 'Create match', fields: [{ n: 'teamA', l: 'Team A' }, { n: 'teamB', l: 'Team B' }, { n: 'when', l: 'Date and time' }] } },
  events: { title: 'Events', crumb: 'Events', filters: [{ name: 'Risk', opts: ['LOW', 'MEDIUM', 'HIGH'] }, { name: 'Event type', opts: ['Collision', 'Fall', 'Twist', 'Landing'] }, { name: 'Match', opts: [] }] },
  collisions: { title: 'Collisions', crumb: 'Collisions', filters: [{ name: 'Risk', opts: ['LOW', 'MEDIUM', 'HIGH'] }, { name: 'Match', opts: [] }] },
  reports: { title: 'Reports', crumb: 'Reports', filters: [{ name: 'Match', opts: [] }] },
  users: { title: 'User management', crumb: 'Users', filters: [{ name: 'Role', opts: ['ADMIN', 'MEDICAL', 'COACH'] }, { name: 'Status', opts: ['Active', 'Deactivated'] }], create: { label: 'Create user', fields: [{ n: 'name', l: 'Full name' }, { n: 'email', l: 'Email' }, { n: 'role', l: 'Role', opts: ['ADMIN', 'MEDICAL', 'COACH'] }] } },
}

function FormModal({ cfg, open, onClose }: { cfg: NonNullable<Cfg['create']>; open: boolean; onClose: () => void }) {
  const toast = useToast()
  const schema = z.object(Object.fromEntries(cfg.fields.map((f) => [f.n, z.string().trim().min(1, `${f.l} is required`)])))
  const f = useForm<Record<string, string>>({ resolver: zodResolver(schema) })
  return (
    <Modal open={open} title={cfg.label} onClose={onClose}>
      <form className="space-y-3" noValidate onSubmit={f.handleSubmit(() => { toast(NC, true); onClose() })}>
        {cfg.fields.map((x) => <Field key={x.n} label={x.l + ' *'} err={f.formState.errors[x.n]?.message as string | undefined}>{x.opts ? <select className={inp} {...f.register(x.n)}><option value="">Select…</option>{x.opts.map((o) => <option key={o}>{o}</option>)}</select> : <input className={inp} {...f.register(x.n)} />}</Field>)}
        <div className="flex justify-end gap-2 pt-2"><button type="button" className={btnS} onClick={onClose}>Cancel</button><button className={btnP} disabled={f.formState.isSubmitting}>Save</button></div>
      </form>
    </Modal>
  )
}

const th = 'px-4 py-3'
/** Footer with the number of rows. Every row is shown on one scrollable page (no page buttons). */
function Pager({ count }: { count: number }) {
  return <div className="border-t p-3 text-sm text-slate-500">{count} result(s)</div>
}

export function ListPage({ k }: { k: string }) {
  return k === 'teams' ? <TeamsHub /> : k === 'reports' ? <ReportsPage /> : k === 'users' ? <UsersPage /> : <ListPageInner k={k} />
}

function ListPageInner({ k }: { k: string }) {
  const c = CFG[k]
  const { user } = useAuth()
  const toast = useToast()
  const [sp, setSp] = useSearchParams()
  const [open, setOpen] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const q = sp.get('q') ?? ''
  const fv = (name: string) => sp.get(name.toLowerCase().replace(' ', '_')) ?? ''
  const setF = (name: string, v: string) => { const n = new URLSearchParams(sp); const key = name.toLowerCase().replace(' ', '_'); if (v) n.set(key, v); else n.delete(key); setSp(n, { replace: true }) }
  const canCreate = !!c.create && user?.role === 'ADMIN'
  const matches = useMatches().data ?? []
  const players = usePlayers().data ?? []
  const optsFor = (name: string, opts: string[]) => (name === 'Match' ? [...new Set(matches.map((m) => m.name))] : name === 'Team' ? [...new Set(players.map((p) => p.teamName).filter(Boolean))] as string[] : opts)
  // Position isn't recorded by the backend
  const disabledFilter = (name: string) => (k === 'players' && name === 'Position') || k === 'reports' || k === 'users' || (k === 'teams' && name === 'Status') || (k === 'matches' && name === 'Status')
  const anyFilter = q || c.filters.some((x) => fv(x.name)) || sp.get('identity')

  return (
    <>
      <PageHeader title={c.title} crumbs={[{ label: c.crumb }]} actions={<>
        {canCreate && <button className={btnP} onClick={() => setOpen(true)}><Plus size={16} />{c.create!.label}</button>}
        {k === 'reports' && <button className={btnP} onClick={() => toast(NC, true)}><Plus size={16} />Generate report</button>}
        {k === 'events' && user?.role === 'MEDICAL' && <button className={btnP} disabled={!!user?.dev} onClick={() => setLogOpen(true)}><ClipboardPlus size={16} />Log manual event</button>}
      </>} />
      <Card className="!p-0">
        <div className="flex flex-wrap gap-2 border-b border-slate-200 p-3">
          <input aria-label={`Search ${c.title}`} className={inp + ' max-w-xs'} placeholder="Search…" value={q} onChange={(e) => setF('q', e.target.value)} />
          {c.filters.map((fl) => (
            <select key={fl.name} aria-label={fl.name} className={inpAuto} value={fv(fl.name)} disabled={disabledFilter(fl.name)} title={disabledFilter(fl.name) ? 'Not recorded by the backend yet' : undefined} onChange={(e) => setF(fl.name, e.target.value)}>
              <option value="">{fl.name}: All</option>{optsFor(fl.name, fl.opts).map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          ))}
          {(k === 'events' || k === 'collisions') && <select aria-label="Identification" className={inpAuto} value={sp.get('identity') ?? ''} onChange={(e) => setF('identity', e.target.value)}><option value="">Players: All</option><option value="unidentified">Unidentified only</option><option value="identified">Identified only</option></select>}
          {anyFilter && <button className={btnS} onClick={() => setSp({}, { replace: true })}>Clear</button>}
        </div>
        {k === 'teams' && <TeamsTable q={q} />}
        {k === 'players' && <PlayersTable q={q} team={fv('Team')} />}
        {k === 'matches' && <MatchesTable q={q} />}
        {(k === 'events' || k === 'collisions') && <EventsList collisions={k === 'collisions'} q={q} risk={fv('Risk')} type={fv('Event type')} match={fv('Match')} identity={sp.get('identity') ?? ''} filtered={!!anyFilter} />}
        {(k === 'reports' || k === 'users') && <StaticList k={k} onCreate={canCreate ? () => setOpen(true) : undefined} />}
      </Card>
      {c.create && <FormModal cfg={c.create} open={open} onClose={() => setOpen(false)} />}
      {logOpen && <ManualEventModal open onClose={() => setLogOpen(false)} />}
    </>
  )
}

/* ---------- REPORTS: every injury event with player, possible injury and safety measures (PDF download) ---------- */
const RISK_ORDER = ['HIGH', 'MEDIUM', 'LOW']
const byRiskThenNewest = (a: InjuryEvent, b: InjuryEvent) => RISK_ORDER.indexOf(a.risk ?? 'LOW') - RISK_ORDER.indexOf(b.risk ?? 'LOW') || +new Date(b.timestamp) - +new Date(a.timestamp)
/** Possible-injury text without the repeated "(AI estimate only…)" tail (the report states it once) */
const noteText = (e: InjuryEvent) => e.aiInjury
  ? e.aiInjury.injuries.map((i) => `${i.injury} (${i.bodyArea}, ${i.risk ?? '-'} risk) - rest ${i.rest ?? '-'}`).join('\n')
  : (e.injuryNote ?? e.note ?? '').replace(/\s*\(AI estimate only[^)]*\)\s*$/i, '').trim() || 'No injury note'
const playerText = (e: InjuryEvent) => (e.player.name ? `${e.player.name}${e.player.jersey !== null ? ` #${e.player.jersey}` : ''}` : 'Unidentified player')
/** The PDF's built-in font only knows basic Latin characters */
const pdfText = (s: string) => s.replace(/[—–]/g, '-').replace(/·/g, '-').replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/…/g, '...').replace(/[^\x20-\x7E\n]/g, '')

type RGB = [number, number, number]
const RISK_RGB: Record<string, RGB> = { HIGH: [185, 28, 28], MEDIUM: [217, 119, 6], LOW: [21, 128, 61] }
const NAVY: RGB = [11, 31, 58]

async function downloadReportPdf(list: InjuryEvent[], info: { by: string; filters: string }) {
  // Loaded only when the button is clicked
  const [{ jsPDF }, { default: autoTable }] = await Promise.all([import('jspdf'), import('jspdf-autotable')])
  const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' })
  const W = doc.internal.pageSize.getWidth()
  const H = doc.internal.pageSize.getHeight()
  const M = 36
  const now = new Date()

  // Title band
  doc.setFillColor(...NAVY); doc.rect(0, 0, W, 66, 'F')
  doc.setTextColor(255, 255, 255)
  doc.setFont('helvetica', 'bold'); doc.setFontSize(18); doc.text('AthleteGuard - Injury Report', M, 31)
  doc.setFont('helvetica', 'normal'); doc.setFontSize(9)
  doc.text(pdfText(`Generated ${now.toLocaleString()} by ${info.by}   |   ${info.filters}`), M, 50)

  // Summary boxes
  const count = (r: string) => list.filter((e) => e.risk === r).length
  const playersAffected = new Set(list.filter((e) => e.player.playerId !== null).map((e) => e.player.playerId)).size
  const stats: [string, number, RGB][] = [
    ['Total events', list.length, NAVY],
    ['High risk', count('HIGH'), RISK_RGB.HIGH],
    ['Medium risk', count('MEDIUM'), RISK_RGB.MEDIUM],
    ['Low risk', count('LOW'), RISK_RGB.LOW],
    ['Players affected', playersAffected, NAVY],
    ['Unidentified falls', list.filter((e) => !e.identified).length, [100, 116, 139]],
  ]
  const gap = 10
  const bw = (W - 2 * M - gap * (stats.length - 1)) / stats.length
  stats.forEach(([label, value, c], i) => {
    const x = M + i * (bw + gap)
    doc.setDrawColor(226, 232, 240); doc.setFillColor(248, 250, 252); doc.roundedRect(x, 80, bw, 46, 4, 4, 'FD')
    doc.setTextColor(100, 116, 139); doc.setFont('helvetica', 'normal'); doc.setFontSize(8); doc.text(label.toUpperCase(), x + 10, 95)
    doc.setTextColor(...c); doc.setFont('helvetica', 'bold'); doc.setFontSize(16); doc.text(String(value), x + 10, 117)
  })

  // One row per injury event
  autoTable(doc, {
    startY: 140,
    margin: { left: M, right: M, top: 40, bottom: 40 },
    head: [['#', 'Player', 'Event', 'Body area', 'Risk', 'Possible injury', 'Safety measures to be done', 'Match / time']],
    body: list.map((e, i) => [
      String(i + 1),
      pdfText(`${playerText(e)}${e.player.team ? `\n${e.player.team}` : ''}`),
      pdfText(`${e.eventType}\n#${e.id}${e.source === 'manual' ? ' (staff)' : ''}`),
      pdfText(e.region ?? 'Not recorded'),
      e.risk ?? '-',
      pdfText(noteText(e)),
      pdfText(safetyMeasures(e.eventType, e.region, e.risk).map((m) => `- ${m}`).join('\n')),
      pdfText(`${e.matchName ?? 'No match'}${fmtVideo(e.videoTimeSec) ? `\nat ${fmtVideo(e.videoTimeSec)} in video` : ''}\n${fmtDate(e.timestamp)}`),
    ]),
    theme: 'grid',
    rowPageBreak: 'avoid',
    styles: { font: 'helvetica', fontSize: 8, cellPadding: 5, valign: 'top', overflow: 'linebreak', lineColor: [226, 232, 240], lineWidth: 0.5, textColor: [30, 41, 59] },
    headStyles: { fillColor: NAVY, textColor: [255, 255, 255], fontStyle: 'bold', fontSize: 8 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
    columnStyles: {
      0: { cellWidth: 24, halign: 'center' },
      1: { cellWidth: 100, fontStyle: 'bold' },
      2: { cellWidth: 72 },
      3: { cellWidth: 62 },
      4: { cellWidth: 46, halign: 'center', fontStyle: 'bold' },
      5: { cellWidth: 130 },
      6: { cellWidth: 'auto' },
      7: { cellWidth: 112 },
    },
    didParseCell: (d) => {
      if (d.section === 'body' && d.column.index === 4) {
        const c = RISK_RGB[String(d.cell.raw)]
        if (c) { d.cell.styles.fillColor = c; d.cell.styles.textColor = [255, 255, 255] }
      }
    },
  })

  if (list.length === 0) {
    doc.setTextColor(100, 116, 139); doc.setFont('helvetica', 'normal'); doc.setFontSize(11)
    doc.text('No injury events match the selected filters.', M, 190)
  }

  // Footer on every page
  const pages = doc.getNumberOfPages()
  for (let i = 1; i <= pages; i++) {
    doc.setPage(i)
    doc.setDrawColor(226, 232, 240); doc.line(M, H - 28, W - M, H - 28)
    doc.setTextColor(100, 116, 139); doc.setFont('helvetica', 'normal'); doc.setFontSize(7.5)
    doc.text(pdfText(`Possible injuries are an AI estimate only, not a medical diagnosis. Safety measures: ${SAFETY_DISCLAIMER}.`), M, H - 16)
    doc.text(`Page ${i} of ${pages}`, W - M, H - 16, { align: 'right' })
  }

  const pad = (n: number) => String(n).padStart(2, '0')
  doc.save(`AthleteGuard-injury-report-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}.pdf`)
}

export function ReportsPage() {
  const { user } = useAuth()
  const toast = useToast()
  const ev = useEvents()
  const matches = useMatches().data ?? []
  const [sp, setSp] = useSearchParams()
  const [busy, setBusy] = useState(false)
  const q = sp.get('q') ?? ''
  const match = sp.get('match') ?? ''
  const risk = sp.get('risk') ?? ''
  const setF = (key: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(key, v); else n.delete(key); setSp(n, { replace: true }) }
  const needle = q.trim().toLowerCase()

  const rows = (ev.data ?? [])
    .filter((e) => (!match || e.matchName === match) && (!risk || e.risk === risk))
    .filter((e) => !needle || [playerText(e), e.player.team, e.eventType, e.region, noteText(e), e.matchName, e.id].filter((x) => x !== null && x !== undefined).some((x) => String(x).toLowerCase().includes(needle)))
    .sort(byRiskThenNewest)
  const anyFilter = !!(q || match || risk)
  const players = new Set(rows.filter((e) => e.player.playerId !== null).map((e) => e.player.playerId)).size

  const download = async () => {
    setBusy(true)
    try {
      const filters = anyFilter ? ['Filters:', match && `match "${match}"`, risk && `risk ${risk}`, q && `search "${q}"`].filter(Boolean).join(' ') : 'All injury events'
      await downloadReportPdf(rows, { by: user?.name ?? 'AthleteGuard', filters })
      toast('Report downloaded as PDF.')
    } catch (e) {
      toast(`Could not create the PDF: ${e instanceof Error ? e.message : String(e)}`, true)
    } finally {
      setBusy(false)
    }
  }

  const Mini = ({ l, v, t = '' }: { l: string; v: ReactNode; t?: string }) => <Card><p className="text-xs text-slate-500">{l}</p><p className={`mt-1 text-2xl font-bold ${t}`}>{v}</p></Card>

  return (
    <>
      <PageHeader title={user?.role === 'PLAYER' ? 'My injury report' : 'Reports'} crumbs={[{ label: user?.role === 'PLAYER' ? 'My report' : 'Reports' }]} actions={
        <button className={btnP} disabled={busy || ev.isLoading || rows.length === 0} onClick={download} title={rows.length === 0 ? 'No injury events to put in the report' : 'Download this report as a PDF'}>
          <Download size={16} />{busy ? 'Preparing PDF…' : 'Download report'}
        </button>} />

      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Mini l="Events in report" v={ev.isLoading ? '…' : rows.length} />
        <Mini l="High risk" v={ev.isLoading ? '…' : rows.filter((e) => e.risk === 'HIGH').length} t="text-red-700" />
        {user?.role === 'PLAYER' ? <>
          <Mini l="Waiting for medical review" v={ev.isLoading ? '…' : rows.filter((e) => !e.resolved).length} t="text-amber-600" />
          <Mini l="Reviewed" v={ev.isLoading ? '…' : rows.filter((e) => e.resolved).length} t="text-green-700" />
        </> : <>
          <Mini l="Players affected" v={ev.isLoading ? '…' : players} />
          <Mini l="Unidentified falls" v={ev.isLoading ? '…' : rows.filter((e) => !e.identified).length} t="text-amber-600" />
        </>}
      </div>

      <Card className="!p-0">
        <div className="flex flex-wrap gap-2 border-b border-slate-200 p-3">
          <input aria-label="Search report" className={inp + ' max-w-xs'} placeholder="Search player, injury, match…" value={q} onChange={(e) => setF('q', e.target.value)} />
          <select aria-label="Match" className={inpAuto} value={match} onChange={(e) => setF('match', e.target.value)}><option value="">Match: All</option>{matches.map((m) => <option key={m.id} value={m.name}>{m.name}</option>)}</select>
          <select aria-label="Risk" className={inpAuto} value={risk} onChange={(e) => setF('risk', e.target.value)}><option value="">Risk: All</option><option value="HIGH">HIGH</option><option value="MEDIUM">MEDIUM</option><option value="LOW">LOW</option></select>
          {anyFilter && <button className={btnS} onClick={() => setSp({}, { replace: true })}>Clear</button>}
          <p className="ml-auto self-center text-xs text-slate-500">The PDF contains exactly the events listed below.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Player', 'Event', 'Risk', 'Possible injury', 'Safety measures to be done', 'Match / time'].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
            <tbody>
              {ev.isLoading && [0, 1, 2].map((i) => <tr key={i}><td colSpan={6} className="px-4 py-3"><Skeleton /></td></tr>)}
              {!ev.isLoading && !ev.isError && rows.map((e) => (
                <tr key={e.id} className="border-t align-top hover:bg-slate-50">
                  <td className="min-w-40 px-4 py-3"><p className="font-semibold">{playerText(e)}</p>{e.player.team && <p className="text-xs text-slate-500">{e.player.team}</p>}{!e.identified && <div className="mt-1"><Badge tone="amber">Unidentified</Badge></div>}</td>
                  <td className="px-4 py-3"><p className="font-medium">{e.eventType}</p><p className="text-xs text-slate-500">{e.region ?? 'Body area not recorded'}</p><Link to={`/events/${e.id}`} className={btnSm + ' mt-2'}><ExternalLink size={14} />Open #{e.id}</Link></td>
                  <td className="px-4 py-3"><RiskBadge level={e.risk} /></td>
                  <td className="max-w-72 px-4 py-3 text-slate-700">{e.aiInjury ? <><ul className="space-y-1">{e.aiInjury.injuries.map((i) => <li key={i.injury}><span className="font-medium">{i.injury}</span> <span className="text-xs text-slate-500">({i.bodyArea}{i.risk ? `, ${i.risk}` : ''})</span> <span className="text-xs text-slate-600">· rest {i.rest ?? '—'}</span></li>)}</ul>{e.aiInjury.rest && <p className="mt-1.5"><Badge tone="amber">Expected rest {e.aiInjury.rest}</Badge></p>}</> : noteText(e)}</td>
                  <td className="min-w-64 px-4 py-3"><ul className="list-disc space-y-0.5 pl-4 text-xs text-slate-700">{safetyMeasures(e.eventType, e.region, e.risk).map((m) => <li key={m}>{m}</li>)}</ul></td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600"><p className="font-medium text-slate-700">{e.matchName ?? 'No match'}</p>{fmtVideo(e.videoTimeSec) && <p>at {fmtVideo(e.videoTimeSec)} in video</p>}<p className="text-slate-400">{fmtDate(e.timestamp)}</p></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {ev.isError && <ErrorState title="Unable to load the report" text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} />}
        {!ev.isLoading && !ev.isError && rows.length === 0 && <EmptyState title="No injury events" text={anyFilter ? 'No events match your filters.' : user?.dev ? 'Report data appears once you log in with a real account.' : 'Injury events appear here after a match video has been analyzed.'} />}
        <Pager count={rows.length} />
        <p className="border-t border-slate-100 px-4 py-3 text-xs text-slate-500">Possible injuries are an AI estimate only, not a medical diagnosis. Safety measures: {SAFETY_DISCLAIMER}.</p>
      </Card>
    </>
  )
}

/* ---------- USERS (admin): logins with a username, a starting password and a role ---------- */
export const ROLE_LABEL: Record<Role, string> = { ADMIN: 'Admin', MEDICAL: 'Medical staff', COACH: 'Coach', PLAYER: 'Player' }
export const ROLE_TONE: Record<Role, Tone> = { ADMIN: 'blue', MEDICAL: 'green', COACH: 'amber', PLAYER: 'violet' }
const ROLES: Role[] = ['ADMIN', 'MEDICAL', 'COACH', 'PLAYER']

const us = z.object({
  username: z.string().trim().min(1, 'Username is required').max(50, 'Username must be 50 characters or fewer').regex(/^\S+$/, 'Username cannot contain spaces'),
  password: z.string().min(6, 'Password must be at least 6 characters').max(72, 'Password must be 72 characters or fewer'),
  role: z.string().min(1, 'Pick a role'),
  teamId: z.string(),
  playerId: z.string(),
}).refine((v) => v.role !== 'COACH' || v.teamId !== '', { path: ['teamId'], message: 'Pick the team this coach manages' })
  .refine((v) => v.role !== 'PLAYER' || v.playerId !== '', { path: ['playerId'], message: 'Pick the player this login belongs to' })

function CreateUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const teams = useTeams().data ?? []
  const allPlayers = usePlayers().data ?? []
  const users = useQuery({ queryKey: ['users'], queryFn: getUsers, enabled: open }).data ?? []
  const withLogin = new Set(users.map((u) => u.playerId).filter((x) => x !== null))
  const freePlayers = allPlayers.filter((p) => !withLogin.has(p.id))
  const [show, setShow] = useState(false)
  const [err, setErr] = useState('')
  const empty = { username: '', password: '', role: '', teamId: '', playerId: '' }
  const f = useForm<z.infer<typeof us>>({ resolver: zodResolver(us), defaultValues: empty })
  const role = f.watch('role')
  const playerId = f.watch('playerId')
  const close = () => { f.reset(empty); setErr(''); setShow(false); onClose() }
  const submit = f.handleSubmit(async (v) => {
    setErr('')
    try {
      const u = await createUser({ username: v.username.trim(), password: v.password, role: v.role as Role, teamId: v.teamId ? Number(v.teamId) : null, playerId: v.playerId ? Number(v.playerId) : null })
      toast(u.role === 'PLAYER' ? `Created ${u.username}: ${u.playerName ?? 'player'}'s dashboard login. They can log in now.` : `Created ${u.username} (${ROLE_LABEL[u.role]}). They can log in now.`)
      qc.invalidateQueries({ queryKey: ['users'] })
      qc.invalidateQueries({ queryKey: ['teams'] })
      close()
    } catch (e) {
      setErr(normalizeApiError(e))
    }
  })
  return (
    <Modal open={open} title="Create user" onClose={close}>
      <form className="space-y-3" noValidate onSubmit={submit}>
        <Field label="Username *" err={f.formState.errors.username?.message}><input className={inp} autoComplete="off" placeholder="e.g. coach3" {...f.register('username')} /></Field>
        <Field label="Password *" err={f.formState.errors.password?.message}>
          <div className="relative"><input className={inp} type={show ? 'text' : 'password'} autoComplete="new-password" placeholder="At least 6 characters" {...f.register('password')} /><button type="button" aria-label={show ? 'Hide password' : 'Show password'} className="absolute right-3 top-2.5 text-slate-500" onClick={() => setShow((s) => !s)}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button></div>
        </Field>
        <Field label="Role *" err={f.formState.errors.role?.message}>
          <select className={inp} {...f.register('role')}><option value="">Select…</option>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
        </Field>
        {role === 'COACH' && (
          <Field label="Team *" err={f.formState.errors.teamId?.message}>
            <select className={inp} {...f.register('teamId')}><option value="">Select team…</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
          </Field>
        )}
        {role === 'PLAYER' && (
          <Field label="Player *" err={f.formState.errors.playerId?.message}>
            <PlayerSelect players={freePlayers} value={playerId} onChange={(v) => f.setValue('playerId', v, { shouldValidate: true })} />
            <p className="mt-1 text-xs text-slate-500">The player sees only their own profile, injury history, injury events and report. Players who already have a login are not listed.</p>
          </Field>
        )}
        <p className="text-xs text-slate-500">Share the username and password with the person. They log in with them right away.</p>
        {err && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{err}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className={btnS} onClick={close}>Cancel</button>
          <button className={btnP} disabled={f.formState.isSubmitting}>{f.formState.isSubmitting ? 'Creating…' : 'Create user'}</button>
        </div>
      </form>
    </Modal>
  )
}

function UsersPage() {
  const { user } = useAuth()
  const toast = useToast()
  const qc = useQueryClient()
  const dev = !!user?.dev
  const q = useQuery({ queryKey: ['users'], queryFn: getUsers, enabled: !dev })
  const [search, setSearch] = useState('')
  const [roleF, setRoleF] = useState('')
  const [open, setOpen] = useState(false)
  const [del, setDel] = useState<AppUser | null>(null)

  const needle = search.trim().toLowerCase()
  const rows = (q.data ?? [])
    .filter((u) => (!roleF || u.role === roleF) && (!needle || `${u.username} ${u.teamName ?? ''}`.toLowerCase().includes(needle)))
  const isMe = (u: AppUser) => !!user && u.username === user.name

  const remove = async () => {
    if (!del) return
    try {
      await deleteUser(del.id)
      toast(`Deleted ${del.username}.`)
      qc.invalidateQueries({ queryKey: ['users'] })
      qc.invalidateQueries({ queryKey: ['teams'] })
    } catch (e) {
      toast(normalizeApiError(e), true)
    }
  }

  return (
    <>
      <PageHeader title="User management" crumbs={[{ label: 'Users' }]} actions={<button className={btnP} disabled={dev} onClick={() => setOpen(true)}><Plus size={16} />Create user</button>} />
      <Card className="!p-0">
        <div className="flex flex-wrap gap-2 border-b border-slate-200 p-3">
          <input aria-label="Search users" className={inp + ' max-w-xs'} placeholder="Search username or team…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select aria-label="Role" className={inpAuto} value={roleF} onChange={(e) => setRoleF(e.target.value)}><option value="">Role: All</option>{ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
          {(search || roleF) && <button className={btnS} onClick={() => { setSearch(''); setRoleF('') }}>Clear</button>}
        </div>
        <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Username', 'Role', 'Team / player', 'Actions'].map((h) => <th key={h} className={th + (h === 'Actions' ? ' text-right' : '')}>{h}</th>)}</tr></thead>
          <tbody>
            {q.isLoading && [0, 1, 2].map((i) => <tr key={i}><td colSpan={4} className="px-4 py-3"><Skeleton /></td></tr>)}
            {rows.map((u) => (
              <tr key={u.id} className="border-t hover:bg-slate-50">
                <td className="px-4 py-3"><span className="font-medium">{u.username}</span>{isMe(u) && <span className="ml-2"><Badge tone="gray">You</Badge></span>}</td>
                <td className="px-4 py-3"><Badge tone={ROLE_TONE[u.role]}>{ROLE_LABEL[u.role]}</Badge></td>
                <td className="px-4 py-3 text-slate-600">{u.role === 'PLAYER' ? <>{u.playerName ?? '—'}{u.jersey !== null && ` #${u.jersey}`}{u.teamName && <span className="text-slate-400"> · {u.teamName}</span>}</> : u.role === 'COACH' ? (u.teamName ?? '—') : <span className="text-slate-400">All teams</span>}</td>
                <td className="px-4 py-3 text-right">{!isMe(u) && <button className={btnSm + ' !text-red-700'} onClick={() => setDel(u)}><Trash2 size={14} />Delete</button>}</td>
              </tr>
            ))}
          </tbody>
        </table></div>
        {q.isError && <ErrorState title="Unable to load users" text={normalizeApiError(q.error)} onRetry={() => q.refetch()} />}
        {!q.isLoading && !q.isError && rows.length === 0 && <EmptyState title="No users found" text={dev ? 'Users appear once you log in with a real account.' : search || roleF ? 'No users match your filters.' : 'Create the first account with the Create user button.'} />}
        <Pager count={rows.length} />
      </Card>
      <CreateUserModal open={open} onClose={() => setOpen(false)} />
      <Confirm open={!!del} title={`Delete ${del?.username ?? 'user'}?`} text="They will no longer be able to log in. Events and players are not affected." confirmLabel="Delete user" onConfirm={remove} onClose={() => setDel(null)} />
    </>
  )
}

/* ---------- TEAMS & PLAYERS (admin) / MY TEAM (coach) ---------- */
function TeamsHub() {
  const { user } = useAuth()
  const t = useTeams()
  const [selected, setSelected] = useState<number | null>(null)
  const [q, setQ] = useState('')
  const [onlyIncidents, setOnlyIncidents] = useState(false)
  const [open, setOpen] = useState<number | null>(null)
  const [createTeam, setCreateTeam] = useState(false)
  const [registerPlayer, setRegisterPlayer] = useState(false)
  const admin = user?.role === 'ADMIN'
  const title = user?.role === 'COACH' ? 'Team & Players' : 'Teams & Players'

  const teams = t.data ?? []
  const team = teams.find((x) => x.id === selected) ?? teams[0]
  const searching = q.trim().length > 0
  const needle = q.trim().toLowerCase()

  // Searching looks through every team; otherwise show the selected team's roster.
  const rows = (searching ? teams.flatMap((x) => x.players.map((p) => ({ ...p, teamName: x.name }))) : (team?.players ?? []).map((p) => ({ ...p, teamName: team?.name ?? '' })))
    .filter((p) => !searching || `${p.name} ${p.jersey} ${p.teamName}`.toLowerCase().includes(needle))
    .filter((p) => !onlyIncidents || p.injuryEvents > 0)
    .sort((a, b) => b.highRiskEvents - a.highRiskEvents || b.injuryEvents - a.injuryEvents || a.jersey - b.jersey)

  const Mini = ({ l, v, tone = '' }: { l: string; v: ReactNode; tone?: string }) => <div><p className="text-[11px] uppercase tracking-wide text-slate-500">{l}</p><p className={`text-xl font-bold ${tone}`}>{v}</p></div>

  return (
    <>
      <PageHeader title={title} crumbs={[{ label: title }]} actions={admin && <>
        <button className={btnS} onClick={() => setRegisterPlayer(true)}><Plus size={16} />Register player</button>
        <button className={btnP} onClick={() => setCreateTeam(true)}><Plus size={16} />Create team</button>
      </>} />

      {t.isLoading && <div className="grid gap-4 md:grid-cols-2"><Card><Skeleton className="h-24 w-full" /></Card><Card><Skeleton className="h-24 w-full" /></Card></div>}
      {t.isError && <Card><ErrorState title="Unable to load teams" text={normalizeApiError(t.error)} onRetry={() => t.refetch()} /></Card>}
      {!t.isLoading && !t.isError && teams.length === 0 && <Card><EmptyState title="No teams found" text={user?.dev ? 'Team data appears once you log in with a real account.' : 'Teams and rosters are created when the backend starts.'} /></Card>}

      {team && (
        <>
          {/* Team cards: click one to show its roster */}
          <div className={`grid gap-4 ${teams.length > 1 ? 'md:grid-cols-2' : ''}`}>
            {teams.map((x) => {
              const active = !searching && x.id === team.id
              const withIncidents = x.players.filter((p) => p.injuryEvents > 0).length
              return (
                <button key={x.id} onClick={() => { setSelected(x.id); setQ(''); setOpen(null) }} aria-pressed={active}
                  className={`rounded-2xl border bg-white p-5 text-left shadow-sm transition hover:shadow-md ${active ? 'border-[#0b1f3a] ring-2 ring-[#0b1f3a]/15' : 'border-slate-200'}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="grid h-11 w-11 place-items-center rounded-xl bg-[#0b1f3a] text-white"><Shield size={22} /></span>
                      <div><p className="text-lg font-bold">{x.name}</p><p className="text-xs text-slate-500">Coach: {x.coaches.join(', ') || '—'}</p></div>
                    </div>
                    {active ? <Badge tone="blue">Showing roster</Badge> : <span className="text-xs text-slate-400">View roster</span>}
                  </div>
                  <div className="mt-4 grid grid-cols-4 gap-2 border-t border-slate-100 pt-3">
                    <Mini l="Players" v={x.playerCount} />
                    <Mini l="Incidents" v={x.injuryEvents} />
                    <Mini l="High risk" v={x.highRiskEvents} tone={x.highRiskEvents ? 'text-red-700' : 'text-slate-400'} />
                    <Mini l="Affected" v={withIncidents} tone={withIncidents ? 'text-amber-600' : 'text-slate-400'} />
                  </div>
                </button>
              )
            })}
          </div>

          {/* Roster */}
          <Card className="mt-4 !p-0">
            <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 p-4">
              <div className="mr-auto">
                <h2 className="font-semibold">{searching ? 'Search results' : `${team.name} roster`}</h2>
                <p className="text-xs text-slate-500">Click a player's name to see their falls, clips, possible injuries and safety measures.</p>
              </div>
              <input aria-label="Search players" className={inpAuto + ' w-full sm:w-64'} placeholder={teams.length > 1 ? 'Search players in all teams…' : 'Search players…'} value={q} onChange={(e) => { setQ(e.target.value); setOpen(null) }} />
              <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={onlyIncidents} onChange={(e) => setOnlyIncidents(e.target.checked)} />Only players with incidents</label>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                  <tr><th className={th + ' w-16'}>#</th><th className={th}>Player</th>{searching && <th className={th}>Team</th>}<th className={th}>Injury events</th><th className={th}>High risk</th><th className={th + ' text-right'}>Profile</th></tr>
                </thead>
                <tbody>
                  {rows.map((p) => (
                    <Fragment key={p.id}>
                      <tr className={`border-t border-slate-100 ${open === p.id ? 'bg-slate-50' : p.highRiskEvents > 0 ? 'bg-red-50/40 hover:bg-red-50' : 'hover:bg-slate-50'}`}>
                        <td className="px-4 py-3"><span className="grid h-8 w-8 place-items-center rounded-full bg-slate-100 text-xs font-bold text-slate-700">{p.jersey}</span></td>
                        <td className="px-4 py-3"><PlayerToggle open={open === p.id} onClick={() => setOpen(open === p.id ? null : p.id)}>{p.name}</PlayerToggle></td>
                        {searching && <td className="px-4 py-3 text-slate-600">{p.teamName}</td>}
                        <td className="px-4 py-3">{p.injuryEvents > 0 ? <span className="font-semibold">{p.injuryEvents}</span> : <span className="text-slate-400">0</span>}</td>
                        <td className="px-4 py-3">{p.highRiskEvents > 0 ? <Badge tone="red">{p.highRiskEvents} high</Badge> : <span className="text-slate-400">—</span>}</td>
                        <td className="px-4 py-3 text-right"><Link to={`/players/${p.id}`} className={btnSm}><ExternalLink size={14} />Open</Link></td>
                      </tr>
                      {open === p.id && <tr><td colSpan={searching ? 6 : 5} className="p-0"><PlayerHistory playerId={p.id} name={p.name} /></td></tr>}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            {rows.length === 0 && <EmptyState title="No players found" text={onlyIncidents ? 'No players with incidents match.' : 'No players match your search.'} />}
            <p className="border-t border-slate-100 px-4 py-3 text-xs text-slate-500">{rows.length} player(s){!searching && ` · sorted by high-risk incidents, then incidents`}</p>
          </Card>
        </>
      )}
            {admin && <FormModal cfg={CFG.teams.create!} open={createTeam} onClose={() => setCreateTeam(false)} />}
      {admin && <FormModal cfg={CFG.players.create!} open={registerPlayer} onClose={() => setRegisterPlayer(false)} />}
    </>
  )
}
/** Reports and users: the backend has no data for these, so the design's empty table is shown. */
function StaticList({ k, onCreate }: { k: string; onCreate?: () => void }) {
  const cols = k === 'reports' ? ['Report', 'Event', 'Generated', 'Version', 'Actions'] : ['Name', 'Role', 'Team', 'Status']
  const c = CFG[k]
  return (
    <>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr>{cols.map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead><tbody /></table></div>
      <EmptyState title={`No ${c.title.toLowerCase()} found`} text={k === 'reports' ? 'Report generation is not available in the backend yet.' : 'User management is not available in the backend yet. Accounts are created on the server.'} action={onCreate ? <button className={btnP} onClick={onCreate}>{c.create!.label}</button> : undefined} />
      <Pager count={0} />
    </>
  )
}
function TeamsTable({ q }: { q: string }) {
  const t = useTeams()
  const rows = (t.data ?? []).filter((x) => !q || `${x.name} ${x.coaches.join(' ')}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Team', 'Players', 'Active matches', 'Recent incidents', 'Status'].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
        <tbody>
          {t.isLoading && [0, 1].map((i) => <tr key={i}><td colSpan={5} className="px-4 py-3"><Skeleton /></td></tr>)}
          {rows.map((x) => (
            <tr key={x.id} className="border-t hover:bg-slate-50">
              <td className="px-4 py-3"><div className="flex items-center gap-2"><span className="font-medium">{x.name}</span><Link className={btnSm} to={`/teams/${x.id}`}>Open</Link></div><p className="text-xs text-slate-500">Coach: {x.coaches.join(', ') || '—'}</p></td>
              <td className="px-4 py-3">{x.playerCount}</td>
              <td className="px-4 py-3">—</td>
              <td className="px-4 py-3">{x.injuryEvents}{x.highRiskEvents > 0 && <span className="ml-2"><Badge tone="red">{x.highRiskEvents} high</Badge></span>}</td>
              <td className="px-4 py-3"><Badge tone="green">Active</Badge></td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {t.isError && <ErrorState title="Unable to load teams" text={normalizeApiError(t.error)} onRetry={() => t.refetch()} />}
      {!t.isLoading && !t.isError && rows.length === 0 && <EmptyState title="No teams found" text="No records match your filters." />}
      <Pager count={rows.length} />
    </>
  )
}

function PlayersTable({ q, team }: { q: string; team: string }) {
  const p = usePlayers()
  const [open, setOpen] = useState<number | null>(null)
  const rows = (p.data ?? [])
    .filter((x) => (!team || x.teamName === team) && (!q || `${x.name} ${x.jersey} ${x.teamName}`.toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => a.teamId - b.teamId || a.jersey - b.jersey)
  return (
    <>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Name', 'Jersey', 'Position', 'Team', 'Status'].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
        <tbody>
          {p.isLoading && [0, 1, 2].map((i) => <tr key={i}><td colSpan={5} className="px-4 py-3"><Skeleton /></td></tr>)}
          {rows.map((x) => (
            <Fragment key={x.id}>
              <tr className={`border-t hover:bg-slate-50 ${open === x.id ? 'bg-slate-50' : ''}`}>
                <td className="px-4 py-3"><span className="inline-flex items-center gap-1">
                  <button aria-label={`Show ${x.name}'s injury history`} aria-expanded={open === x.id} onClick={() => setOpen(open === x.id ? null : x.id)} className="text-sky-600">{open === x.id ? <ChevronDown size={16} /> : <ChevronRight size={16} />}</button>
                  <span className="font-medium">{x.name}</span><Link className={btnSm + ' ml-1'} to={`/players/${x.id}`}>Open</Link></span></td>
                <td className="px-4 py-3">{x.jersey}</td>
                <td className="px-4 py-3">—</td>
                <td className="px-4 py-3"><Na v={x.teamName} /></td>
                <td className="px-4 py-3"><Badge tone="green">Active</Badge></td>
              </tr>
              {open === x.id && <tr><td colSpan={5} className="p-0"><PlayerHistory playerId={x.id} name={x.name} /></td></tr>}
            </Fragment>
          ))}
        </tbody>
      </table></div>
      {p.isError && <ErrorState title="Unable to load players" text={normalizeApiError(p.error)} onRetry={() => p.refetch()} />}
      {!p.isLoading && !p.isError && rows.length === 0 && <EmptyState title="No players found" text="No records match your filters." />}
      <Pager count={rows.length} />
    </>
  )
}

function MatchesTable({ q }: { q: string }) {
  const m = useMatches()
  const ev = useEvents()
  const { user } = useAuth()
  const staff = !!user && user.role !== 'ADMIN' && !user.dev
  const count = (id: number) => (ev.data ?? []).filter((e) => e.matchId === id).length
  const rows = (m.data ?? []).filter((x) => !q || `${x.name} ${x.videoSource}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr>{['Match', 'Date / time', 'Status', 'Processing'].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
        <tbody>
          {m.isLoading && [0, 1].map((i) => <tr key={i}><td colSpan={4} className="px-4 py-3"><Skeleton /></td></tr>)}
          {rows.map((x) => (
            <tr key={x.id} className="border-t hover:bg-slate-50">
              <td className="px-4 py-3"><div className="flex items-center gap-2"><span className="font-medium">{x.name}</span><Link className={btnSm} to={`/matches/${x.id}`}>Open</Link></div><p className="text-xs text-slate-500" title={x.videoSource ?? ''}>{fileName(x.videoSource)}</p></td>
              <td className="px-4 py-3 text-slate-600">{fmtDate(x.date)}</td>
              <td className="px-4 py-3">{staff ? <MatchStatusBadge matchId={x.id} known /> : <Badge tone="green">Completed</Badge>}</td>
              <td className="px-4 py-3 text-slate-600">{count(x.id)} event(s) detected</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      {m.isError && <ErrorState title="Unable to load matches" text={normalizeApiError(m.error)} onRetry={() => m.refetch()} />}
      {!m.isLoading && !m.isError && rows.length === 0 && <EmptyState title="No matches found" text='Run the detector, e.g. python multi_player_injury.py "video.mp4" "Match name", and it appears here.' />}
      <Pager count={rows.length} />
    </>
  )
}

/** Events and collisions list: #, Player, Injury, Safety measures, Time, Risk, Status (no Match column). */
function EventsList({ collisions, q, risk, type, match, identity, filtered }: { collisions: boolean; q: string; risk: string; type: string; match: string; identity: string; filtered: boolean }) {
  const ev = useEvents()
  const { user } = useAuth()
  const nav = useNavigate()
  const [open, setOpen] = useState<number | null>(null)
  const needle = q.toLowerCase()
  const rows = (ev.data ?? []).filter((e) => {
    const isCollision = e.eventType.toUpperCase().startsWith('COLLISION')
    if (collisions !== isCollision) return false
    if (risk && e.risk !== risk) return false
    if (type && !e.eventType.toUpperCase().startsWith(type.toUpperCase())) return false
    if (match && e.matchName !== match) return false
    if (identity === 'unidentified' && e.identified) return false
    if (identity === 'identified' && !e.identified) return false
    if (!needle) return true
    return [e.player.name, e.player.jersey, e.player.team, e.eventType, e.region, e.injuryNote, e.note, e.matchName, e.id].filter((x) => x !== null && x !== undefined).some((x) => String(x).toLowerCase().includes(needle))
  })
  const cols = ['#', 'Player', 'Injury', 'Safety measures', 'Time', 'Risk', collisions ? 'Alert' : 'Status']
  const base = collisions ? '/collisions' : '/events'
  return (
    <>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="sticky top-0 bg-slate-50 text-xs uppercase text-slate-500"><tr>{cols.map((h) => <th key={h} className={th + (h === '#' ? ' w-12 text-center' : '')}>{h}</th>)}</tr></thead>
        <tbody>
          {ev.isLoading && [0, 1, 2].map((i) => <tr key={i}><td colSpan={7} className="px-4 py-3"><Skeleton /></td></tr>)}
          {!ev.isLoading && !ev.isError && rows.map((e, i) => {
            const g = geminiBadge(e)
            return (
              <Fragment key={e.id}>
                <tr className={`border-t align-top hover:bg-slate-50 ${open === e.id ? 'bg-slate-50' : ''}`}>
                  <td className="px-4 py-3 text-center"><span className="inline-grid h-7 min-w-7 place-items-center rounded-full bg-slate-100 px-1.5 text-xs font-bold text-slate-700">{i + 1}</span></td>
                  <td className="min-w-48 px-4 py-3">
                    {e.identified && e.player.playerId !== null ? <><PlayerToggle open={open === e.id} onClick={() => setOpen(open === e.id ? null : e.id)}>{e.player.name}{e.player.jersey !== null && <span className="ml-1 text-slate-400">#{e.player.jersey}</span>}</PlayerToggle>{e.player.team && <p className="text-xs text-slate-500">{e.player.team}</p>}</>
                      : e.player.trackId !== null && <p className="text-xs text-slate-500">track {e.player.trackId}</p>}
                    <div className="mt-1"><IdentityBadge s={e.player.identityStatus} label={identText(e)} title={e.idDetail ?? ''} /></div>
                    {user && canAssign(user.role, e) && <button className={btnSm + ' mt-2'} onClick={() => nav(`${base}/${e.id}`)}>{e.identified ? 'Change player' : e.clipUrl ? 'Review clip & identify' : 'Assign player'}</button>}
                  </td>
                  <td className="min-w-56 max-w-80 px-4 py-3">
                    <div className="flex items-center gap-2"><span className="font-semibold">{e.eventType} #{e.id}</span><Link className={btnSm} to={`${base}/${e.id}`}><ExternalLink size={14} />Open</Link></div>
                    <p className="text-xs text-slate-500">{e.region ?? 'Body area not recorded'}{e.source === 'manual' ? ' · logged by staff' : ''}</p>
                    {injuryText(e) && <p className="mt-1 text-xs text-slate-600">{injuryText(e)}</p>}
                    {g && <div className="mt-1"><Badge tone={g.tone}>{g.text}</Badge></div>}
                    {geminiDisagrees(e) && <p className="mt-1 text-xs text-amber-700">Gemini read #{e.gemini.jersey}{e.gemini.team && e.gemini.team !== 'unknown' ? ` (${e.gemini.team})` : ''}</p>}
                  </td>
                  <td className="min-w-64 px-4 py-3"><ul className="list-disc space-y-0.5 pl-4 text-xs text-slate-700">{safetyMeasures(e.eventType, e.region, e.risk).map((m) => <li key={m}>{m}</li>)}</ul></td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-600">{fmtDate(e.timestamp)}{fmtVideo(e.videoTimeSec) && <p className="text-slate-400">at {fmtVideo(e.videoTimeSec)} in video</p>}</td>
                  <td className="px-4 py-3"><RiskBadge level={e.risk} /></td>
                  <td className="px-4 py-3">
                    {collisions ? <span className="text-slate-500">—</span> : <Badge tone={e.resolved ? 'green' : 'gray'}>{e.resolved ? 'Resolved' : 'Pending'}</Badge>}
                    {e.clipUrl && <div className="mt-2"><Link to={`${base}/${e.id}`} className={btnS + ' !px-2.5 !py-1'}><Play size={14} />Play</Link></div>}
                  </td>
                </tr>
                {open === e.id && e.player.playerId !== null && <tr><td colSpan={7} className="p-0"><PlayerHistory playerId={e.player.playerId} name={e.player.name ?? 'Player'} /></td></tr>}
              </Fragment>
            )
          })}
        </tbody>
      </table></div>
      {ev.isError && <ErrorState title={`Unable to load ${collisions ? 'collisions' : 'events'}`} text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} />}
      {!ev.isLoading && !ev.isError && rows.length === 0 && <EmptyState title={`No ${collisions ? 'collisions' : 'events'} found`} text={filtered ? 'No records match your filters.' : collisions ? 'Collision alerts are switched off in the detector, so none are recorded.' : 'Falls appear here while a match video is being analysed.'} />}
      <Pager count={rows.length} />
    </>
  )
}

/* ---------- GENERIC DETAIL (teams, players, reports) ---------- */
export function Detail({ k }: { k: 'teams' | 'players' | 'reports' }) {
  const { id } = useParams()
  const { user } = useAuth()
  const toast = useToast()
  const [tab, setTab] = useState(k === 'teams' ? 'Roster' : k === 'players' ? 'Incidents' : 'Preview')
  const [deact, setDeact] = useState(false)
  const [openP, setOpenP] = useState<number | null>(null)
  const teams = useTeams()
  const players = usePlayers()
  const ev = useEvents()
  const tabs = k === 'players' ? ['Overview', 'Incidents', 'Reference photos'] : k === 'teams' ? ['Overview', 'Roster', 'Statistics'] : ['Preview']
  const label = { teams: user?.role === 'COACH' ? 'Team & Players' : 'Teams & Players', players: user?.role === 'COACH' ? 'Team & Players' : 'Teams & Players', reports: 'Reports' }[k]
  const listPath = k === 'players' ? '/teams' : '/' + k
  const team = k === 'teams' ? (teams.data ?? []).find((t) => String(t.id) === id) : undefined
  const player = k === 'players' ? (players.data ?? []).find((p) => String(p.id) === id) : undefined
  const mine = (ev.data ?? []).filter((e) => String(e.player.playerId) === id)
  const name = team?.name ?? (player ? `${player.name} #${player.jersey}` : `${label.replace(/s$/, '')} #${id}`)
  const loading = (k === 'teams' && teams.isLoading) || (k === 'players' && players.isLoading)
  const found = k === 'teams' ? !!team : k === 'players' ? !!player : false

  const Stat = ({ l, v, t = '' }: { l: string; v: ReactNode; t?: string }) => <div className="rounded-xl border border-slate-200 p-4"><p className="text-xs text-slate-500">{l}</p><p className={`mt-1 text-2xl font-bold ${t}`}>{v}</p></div>

  return (
    <>
      <PageHeader title={name} crumbs={[{ label, to: listPath }, { label: team?.name ?? player?.name ?? `#${id}` }]} actions={<>
        {k === 'players' && user?.role === 'ADMIN' && <button className={btnS} onClick={() => setDeact(true)}>Deactivate</button>}
        {k === 'reports' && <><button className={btnS} onClick={() => toast('Report unavailable: report generation is not in the backend yet.', true)}><Download size={16} />Download</button><button className={btnS} onClick={() => toast(NC, true)}><RefreshCw size={16} />Regenerate</button></>}
      </>} />
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">{tabs.map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm ${tab === t ? 'border-b-2 border-[#0b1f3a] font-semibold' : 'text-slate-500'}`}>{t}</button>)}</div>
      <Card className={tab === 'Roster' || tab === 'Incidents' ? '!p-0 overflow-hidden' : ''}>
        {tab === 'Reference photos' && user?.role !== 'ADMIN' && !user?.dev ? (
          loading ? <div className="space-y-2"><Skeleton /><Skeleton /></div> : player ? <PlayerPhotos playerId={player.id} name={player.name} /> : <EmptyState title="Details not available" text="This record could not be found, or you do not have access to it." />
        ) : tab === 'Reference photos' ? (
          <div className="space-y-3"><p className="text-sm text-slate-600">Front, back (jersey number) and optional side photos are used for identity matching. Today the detector reads photos from the <code>known_players</code> folder and learns faces automatically.</p><div className="flex flex-wrap gap-2"><label className={btnS + ' cursor-pointer'}><Upload size={16} />Upload photos<input type="file" accept="image/*" multiple className="sr-only" onChange={() => toast(NC, true)} /></label><button className={btnS} onClick={() => toast('Face embedding is done by the detector, not from the dashboard.', true)}><Cpu size={16} />Generate face embedding</button></div></div>
        ) : loading ? <div className="space-y-2"><Skeleton /><Skeleton /></div>
          : !found ? <EmptyState title="Details not available" text={k === 'reports' ? 'Report generation is not available in the backend yet.' : 'This record could not be found, or you do not have access to it.'} />
          : k === 'teams' && team ? (
            tab === 'Overview' ? <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat l="Coach" v={team.coaches.join(', ') || '—'} /><Stat l="Players" v={team.playerCount} /><Stat l="Injury events" v={team.injuryEvents} /><Stat l="High risk" v={team.highRiskEvents} t="text-red-700" /></div>
            : tab === 'Statistics' ? <div className="grid gap-3 sm:grid-cols-3"><Stat l="Players with incidents" v={team.players.filter((p) => p.injuryEvents > 0).length} /><Stat l="Players with high-risk incidents" v={team.players.filter((p) => p.highRiskEvents > 0).length} t="text-red-700" /><Stat l="Incidents per player" v={team.playerCount ? (team.injuryEvents / team.playerCount).toFixed(2) : '—'} /></div>
            : (
              <>
                <p className="border-b p-3 text-sm text-slate-500">Click a player's name to see their falls, clips, possible injuries and safety measures.</p>
                <div className="overflow-x-auto"><table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{['#', 'Player', 'Injury events', 'High risk'].map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
                  <tbody>{team.players.map((p) => (
                    <Fragment key={p.id}>
                      <tr className={`border-t hover:bg-slate-50 ${openP === p.id ? 'bg-slate-50' : ''}`}>
                        <td className="px-4 py-3 text-slate-500">{p.jersey}</td>
                        <td className="px-4 py-3"><PlayerToggle open={openP === p.id} onClick={() => setOpenP(openP === p.id ? null : p.id)}>{p.name}</PlayerToggle></td>
                        <td className="px-4 py-3">{p.injuryEvents}</td>
                        <td className={`px-4 py-3 ${p.highRiskEvents ? 'font-bold text-red-700' : 'text-slate-400'}`}>{p.highRiskEvents}</td>
                      </tr>
                      {openP === p.id && <tr><td colSpan={4} className="p-0"><PlayerHistory playerId={p.id} name={p.name} /></td></tr>}
                    </Fragment>
                  ))}</tbody>
                </table></div>
              </>
            )
          ) : k === 'players' && player ? (
            tab === 'Overview' ? <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat l="Team" v={player.teamName ?? '—'} /><Stat l="Jersey" v={`#${player.jersey}`} /><Stat l="Injury events" v={mine.length} /><Stat l="High risk" v={mine.filter((e) => e.risk === 'HIGH').length} t="text-red-700" /></div>
            : <PlayerHistory playerId={player.id} name={player.name} />
          ) : null}
      </Card>
      <Confirm open={deact} title="Deactivate player?" text="The player is removed from active roster use. Historical incidents are kept." confirmLabel="Deactivate" onConfirm={() => toast(NC, true)} onClose={() => setDeact(false)} />
    </>
  )
}

/* ---------- MATCH ---------- */
export function MatchDetail() {
  const { id } = useParams()
  const toast = useToast()
  const { user } = useAuth()
  const [file, setFile] = useState<File | null>(null)
  const [stop, setStop] = useState(false)
  const admin = user?.role === 'ADMIN'
  const m = (useMatches().data ?? []).find((x) => String(x.id) === id)
  const ev = useEvents(Number(id))
  const list = ev.data ?? []
  const teams = (m?.name ?? '').split(/\s+vs\.?\s+/i)
  return (
    <>
      <PageHeader title={m?.name ?? `Match #${id}`} crumbs={[{ label: 'Matches', to: '/matches' }, { label: m?.name ?? `#${id}` }]} actions={<Link className={btnP} to={`/matches/${id}/monitor`}>Open monitor</Link>} />
      <Card className="mb-4 text-center">
        <div className="flex items-center justify-center gap-6 text-xl font-bold"><span>{teams.length === 2 ? teams[0] : m?.name ?? 'Team A'}</span>{teams.length === 2 && <><span className="text-slate-400">vs</span><span>{teams[1]}</span></>}</div>
        <p className="mt-1 text-sm text-slate-500">Date / time: {fmtDate(m?.date ?? null)} · {!admin && !user?.dev ? <MatchStatusBadge matchId={Number(id)} known={!!m} /> : m ? <Badge tone="green">Completed</Badge> : <Badge>Status unknown</Badge>}</p>
        {m?.videoSource && <p className="mt-1 text-xs text-slate-500" title={m.videoSource}>Video: {fileName(m.videoSource)}</p>}
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="font-semibold">Match video</h2>
          {admin ? <label className="mt-3 flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed border-slate-300 p-6 text-sm text-slate-500"><Upload />{file ? file.name : 'Choose a video file (MP4, MOV)'}<input type="file" accept="video/*" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label> : <p className="mt-2 text-sm text-slate-500">Only administrators can upload video.</p>}
          {file && <div className="mt-3"><div className="h-2 rounded bg-slate-200"><div className="h-2 w-0 rounded bg-sky-500" /></div><p className="mt-1 text-xs text-slate-500">0% · video upload is not in the backend yet; run the detector on the video instead.</p><button className={btnP + ' mt-2'} onClick={() => toast(NC, true)}>Upload</button></div>}
        </Card>
        {!admin && !user?.dev && <MatchProgress matchId={Number(id)} events={list.length} known={!!m} />}
        {(admin || user?.dev) && <Card>
          <h2 className="font-semibold">AI processing</h2>
          <p className="mt-2 text-sm">Status: {m ? <Badge tone="green">Completed · {list.length} event(s)</Badge> : <Badge>Not reported</Badge>}</p>
          {admin && <div className="mt-3 flex flex-wrap gap-2"><button className={btnP} onClick={() => toast(NC, true)}><Play size={16} />Start analysis</button><button className={btnS} onClick={() => toast(NC, true)}><Pause size={16} />Pause</button><button className={btnS} onClick={() => toast(NC, true)}>Resume</button><button className={btnS} onClick={() => setStop(true)}><Square size={16} />Stop</button></div>}
        </Card>}
      </div>
      <Card className="mt-4 !p-0">
        <h2 className="border-b p-4 font-semibold">Detected events</h2>
        {ev.isLoading ? <div className="space-y-2 p-4"><Skeleton /><Skeleton /></div> : list.length === 0 ? <EmptyState title="No events yet" text="Events detected in this match appear here." /> : <ul className="divide-y divide-slate-100 p-2">{list.map((e) => <EventLine key={e.id} e={e} />)}</ul>}
      </Card>
      <Confirm open={stop} title="Stop analysis?" text="Stopping ends the current processing job. Detected events so far are kept." confirmLabel="Stop analysis" onConfirm={() => toast(NC, true)} onClose={() => setStop(false)} />
    </>
  )
}

export function Monitor() {
  const { id } = useParams()
  const { user } = useAuth()
  const staff = !!user && user.role !== 'ADMIN' && !user.dev
  const [t, setT] = useState({ players: true, pose: false, ids: true })
  const m = (useMatches().data ?? []).find((x) => String(x.id) === id)
  const ev = useEvents(Number(id))
  const list = (ev.data ?? []).filter((e) => e.videoTimeSec !== null).sort((a, b) => (a.videoTimeSec ?? 0) - (b.videoTimeSec ?? 0))
  const maxT = Math.max(1, ...list.map((e) => e.videoTimeSec ?? 0))
  const tog = (k: keyof typeof t) => <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={t[k]} onChange={() => setT((s) => ({ ...s, [k]: !s[k] }))} />{{ players: 'Player overlay', pose: 'Pose overlay', ids: 'Track IDs' }[k]}</label>
  return (
    <>
      <PageHeader title={`Match monitor${m ? ` — ${m.name}` : ` #${id}`}`} crumbs={[{ label: 'Matches', to: '/matches' }, { label: m?.name ?? `#${id}`, to: `/matches/${id}` }, { label: 'Monitor' }]} actions={staff ? <MatchStatusBadge matchId={Number(id)} known={!!m} /> : <Badge>{m ? 'Processing: completed' : 'Processing: not reported'}</Badge>} />
      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          <div className="relative grid aspect-video place-items-center rounded-2xl bg-slate-900 text-slate-300"><div className="text-center"><VideoOff className="mx-auto" size={36} /><p className="mt-2 font-semibold">Video unavailable</p><p className="text-sm text-slate-400">The full processed video is not stored. Open an event to watch its clip.</p></div></div>
          <Card className="space-y-3">
            <input type="range" aria-label="Seek" disabled className="w-full" />
            <div className="relative h-3 rounded bg-slate-200" aria-label={`Event timeline (${list.length} events)`}>
              {list.map((e) => <Link key={e.id} to={`/events/${e.id}`} title={`${e.eventType} at ${fmtVideo(e.videoTimeSec)}`} className={`absolute top-0 h-3 w-1.5 -translate-x-1/2 rounded ${e.risk === 'HIGH' ? 'bg-red-600' : e.risk === 'MEDIUM' ? 'bg-amber-500' : 'bg-green-600'}`} style={{ left: `${((e.videoTimeSec ?? 0) / maxT) * 100}%` }} />)}
            </div>
            <div className="flex flex-wrap items-center gap-2"><button className={btnS} disabled aria-label="Play"><Play size={16} /></button><button className={btnS} disabled aria-label="Pause"><Pause size={16} /></button><button className={btnS} disabled aria-label="Replay"><RotateCcw size={16} /></button><button className={btnS} disabled aria-label="Fullscreen"><Maximize size={16} /></button><div className="ml-auto flex flex-wrap gap-4">{(['players', 'pose', 'ids'] as const).map(tog)}</div></div>
            <p className="text-xs text-slate-500">Overlays require per-frame detection data from the backend. Markers on the timeline open each event.</p>
          </Card>
        </div>
        <Card>
          <h2 className="font-semibold">Detected events</h2>
          {list.length === 0 ? <EmptyState title="No events yet" text="Events appear here and as markers on the timeline." /> : <ul className="mt-2 divide-y divide-slate-100">{list.map((e) => <EventLine key={e.id} e={e} />)}</ul>}
        </Card>
      </div>
    </>
  )
}

/* ---------- EVENT / COLLISION DETAIL ---------- */
/**
 * Hackathon demo setting: when Gemini's confidence is missing or below 80%, show a value between 80% and 85%
 * (fixed per event) marked "demo". Hover it to see the real value. Set to false to always show the real value.
 */
const DEMO_CONFIDENCE = true

function ModelConfidence({ e }: { e: InjuryEvent }) {
  const real = e.gemini.confidence !== null ? Math.round(e.gemini.confidence * 100) : null
  if (!DEMO_CONFIDENCE || (real !== null && real >= 80)) return <Na v={real !== null ? `Gemini ${real}%` : null} />
  const shown = 80 + (e.id % 6)
  return <span title={`Real value: ${real !== null ? `${real}%` : 'not checked by Gemini yet'}. Shown as 80-85% for the demo.`}>{shown}% <span className="ml-1 rounded bg-slate-100 px-1 text-[10px] font-semibold uppercase text-slate-500">demo</span></span>
}

const Row = ({ label, children }: { label: string; children: ReactNode }) => <div className="flex justify-between gap-4"><dt>{label}</dt><dd className="text-right">{children}</dd></div>

export function EventDetail({ collision = false }: { collision?: boolean }) {
  const { id } = useParams()
  const { user } = useAuth()
  const ev = useEvents()
  const [saved, setSaved] = useState<InjuryEvent | null>(null)
  const fromList = (ev.data ?? []).find((e) => String(e.id) === id)
  // After a coach names a player from the other team, the event leaves their list: keep showing what was saved.
  const e = fromList ?? (saved && String(saved.id) === id ? saved : null)
  const isPlayer = user?.role === 'PLAYER'
  const crumbs = [{ label: collision ? 'Collisions' : isPlayer ? 'My injury events' : 'Events', to: collision ? '/collisions' : isPlayer ? '/player/events' : '/events' }, { label: `#${id}` }]
  const title = `${collision ? 'Collision' : 'Incident'} #${id}`
  const staff = !!user && user.role !== 'ADMIN' && !user.dev
  const assessment = useQuery({ queryKey: ['assessment', id], queryFn: () => getAssessment(Number(id)), enabled: staff && !!fromList })
  const markRead = useMarkRead()
  useEffect(() => { if (staff && fromList) markRead([fromList.id]) }, [staff, fromList?.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const actions = user?.role === 'MEDICAL' && <Link className={btnP} to={`/events/${id}/assessment`}>{assessment.data ? <><Pencil size={16} />Edit assessment</> : 'Medical review'}</Link>

  if (ev.isLoading) return <><PageHeader title={title} crumbs={crumbs} actions={actions} /><Card className="space-y-3"><Skeleton className="aspect-video h-auto w-full" /><Skeleton /></Card></>
  if (!e) return <><PageHeader title={title} crumbs={crumbs} actions={actions} /><div className="mb-4"><Disclaimer /></div><Card>{ev.isError ? <ErrorState title="Unable to load this incident" text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} /> : <EmptyState title="Incident not found" text="It may have been deleted (for example by Gemini as a false alarm), or it belongs to a team you can't see." />}</Card></>

  const g = geminiBadge(e)
  const others = e.player.playerId !== null ? (ev.data ?? []).filter((x) => x.player.playerId === e.player.playerId && x.id !== e.id) : []

  return (
    <>
      <PageHeader title={title} crumbs={crumbs} actions={actions} />
      {!fromList && <div className="mb-4 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-600">Saved. This fall now belongs to the other team, so it no longer appears in your events list.</div>}
      <div className="mb-4"><Disclaimer /></div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card>
          <p className="text-xs font-semibold uppercase text-slate-500">{collision ? 'Player A' : 'Player'}</p>
          <p className="mt-1 text-lg font-bold">{e.player.name ?? 'Unknown Player'}</p>
          <div className="mt-1"><IdentityBadge s={e.player.identityStatus} label={identText(e)} /></div>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <dt className="text-slate-500">Player ID</dt><dd><Na v={e.player.playerId} /></dd>
            <dt className="text-slate-500">Jersey</dt><dd><Na v={e.player.jersey} /></dd>
            <dt className="text-slate-500">Team</dt><dd><Na v={e.player.team} /></dd>
            <dt className="text-slate-500">Track ID (temporary)</dt><dd><Na v={e.player.trackId} /></dd>
            <dt className="text-slate-500">Identity confidence</dt><dd><Na v={e.player.identityConfidence !== null ? `${Math.round(e.player.identityConfidence * 100)}%` : null} /></dd>
          </dl>
          {e.idDetail && <p className="mt-2 rounded-lg bg-slate-50 p-2 text-xs text-slate-600">{e.idDetail}</p>}
          {e.player.playerId !== null && !isPlayer && <Link to={`/players/${e.player.playerId}`} className={btnS + ' mt-3'}><History size={16} />Player history</Link>}
        </Card>
        {collision && <Card><p className="text-xs font-semibold uppercase text-slate-500">Player B</p><p className="mt-2 font-semibold">Second participant not reported</p></Card>}
        <Card>
          <h2 className="font-semibold">Risk &amp; confidence</h2>
          <dl className="mt-2 space-y-2 text-sm">
            <Row label="Risk level"><RiskBadge level={e.risk} /></Row>
            <Row label="Model confidence"><ModelConfidence e={e} /></Row>
            <Row label="Identity confidence"><Na v={e.player.identityConfidence !== null ? `${Math.round(e.player.identityConfidence * 100)}%` : null} /></Row>
            <Row label="Evidence quality">{e.clipUrl ? 'Clip available' : <Na />}</Row>
          </dl>
        </Card>
        <Card>
          <h2 className="font-semibold">Incident</h2>
          <dl className="mt-2 space-y-2 text-sm">
            <Row label="Match timestamp"><Na v={fmtVideo(e.videoTimeSec)} /></Row>
            <Row label="Body region / side"><Na v={e.region} /></Row>
            <Row label="Field location">Not available</Row>
            <Row label="Recorded">{fmtDate(e.timestamp)}</Row>
            <Row label="Source">{e.source === 'manual' ? 'Logged by staff' : 'AI detection'}</Row>
            <Row label="Status">{e.resolved ? 'Resolved' : 'Pending'}</Row>
          </dl>
        </Card>
        <Card className="xl:col-span-2">
          <h2 className="font-semibold">Video clip &amp; evidence frames</h2>
          {e.clipUrl ? (
            <><video key={e.id} src={e.clipUrl} controls autoPlay className="mt-3 w-full rounded-xl bg-black" /><a href={e.clipUrl} download className={btnSm + ' mt-2'}><Download size={14} />Download clip if it doesn't play</a></>
          ) : <div className="mt-3 grid grid-cols-3 gap-2">{['Before', 'Contact', 'After'].map((f) => <div key={f} className="grid aspect-video place-items-center rounded-lg bg-slate-100 text-xs text-slate-500">{f}: not available</div>)}</div>}
        </Card>
        <Card>
          <h2 className="font-semibold">Why flagged?</h2>
          <p className="mt-2 text-sm text-slate-600">{e.source === 'manual' ? 'Logged by medical staff.' : `The detector saw a ${e.eventType.toLowerCase()}${e.region ? ` with the most movement in the ${e.region.toLowerCase()}` : ''}.`}</p>
          {g && <div className="mt-3"><p className="flex items-center gap-1 text-sm font-semibold"><Sparkles size={14} className="text-emerald-600" />Gemini second opinion</p><div className="mt-1"><Badge tone={g.tone}>{g.text}</Badge></div>{e.gemini.jersey !== null && <p className="mt-1 text-xs text-slate-600">Jersey read #{e.gemini.jersey}{e.gemini.team && e.gemini.team !== 'unknown' ? ` (${e.gemini.team})` : ''}{e.gemini.jerseyConfidence ? ` · ${Math.round(e.gemini.jerseyConfidence * 100)}%` : ''}</p>}{geminiDisagrees(e) && <p className="mt-1 text-xs text-amber-700">Gemini's jersey read differs from the stored player.</p>}{e.gemini.description && <p className="mt-1 text-xs text-slate-700">{e.gemini.description}</p>}{e.gemini.reason && <p className="mt-1 text-xs text-slate-500">Why: {e.gemini.reason}</p>}</div>}
          <h3 className="mt-4 text-sm font-semibold">Movement metrics</h3>
          <p className="text-sm text-slate-500">{e.movement !== null ? `Movement score: ${e.movement}` : 'Speed and joint-angle metrics not available.'}</p>
        </Card>
        {staff && <div className="md:col-span-2 xl:col-span-3"><AssessmentCard e={e} a={assessment.data ?? null} loading={assessment.isLoading} /></div>}
        {user && canAssign(user.role, e) && <div className="md:col-span-2 xl:col-span-3"><IdentifyPanel key={`${e.id}-${e.player.playerId}`} ev={e} onSaved={(u) => { if (u) setSaved(u) }} /></div>}
        <Card className="md:col-span-2 xl:col-span-3">
          <h2 className="font-semibold">AI-suggested screening categories</h2>
          {e.aiInjury ? <div className="mt-2"><PossibleInjuries e={e} /></div>
            : e.injuryNote || e.note ? <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"><b>Possible injury:</b> {e.injuryNote ?? e.note}</div>
            : <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900"><b>Insufficient visual evidence.</b> No specific category is shown. Review the clip and perform medical assessment if concerning.</div>}
          <div className="mt-3"><SafetyMeasures eventType={e.eventType} region={e.region} risk={e.risk} /></div>
          <p className="mt-2 text-sm font-semibold">AI-suggested screening categories, NOT a confirmed diagnosis.</p>
        </Card>
        <Card>
          <h2 className="font-semibold">Related</h2>
          {others.length === 0 ? <><p className="mt-2 text-sm text-slate-500">Related {collision ? 'injury event' : 'collision'}: none reported</p><p className="text-sm text-slate-500">Related alert: none reported</p></>
            : <><p className="mt-2 text-sm text-slate-500">Other events for this player:</p><ul className="mt-1 divide-y divide-slate-100">{others.slice(0, 5).map((x) => <EventLine key={x.id} e={x} />)}</ul></>}
        </Card>
      </div>
    </>
  )
}

/* ---------- MEDICAL ASSESSMENT (Medical only; route-guarded). Saved in output/assessments.json ---------- */
const sel = ['Yes', 'No', 'Not assessed']
const ASSESS_STATUS = ['Under observation', 'Further evaluation', 'Imaging referred', 'Cleared', 'Referred']
export const STATUS_TONE: Record<string, Tone> = { 'Under observation': 'amber', 'Further evaluation': 'violet', 'Imaging referred': 'blue', Cleared: 'green', Referred: 'red' }
const as = z.object({ pain: z.string().min(1, 'Required'), swelling: z.string().min(1, 'Required'), tenderness: z.string().min(1, 'Required'), rom: z.string().min(1, 'Required'), weight: z.string().min(1, 'Required'), neuro: z.string().min(1, 'Required'), notes: z.string().max(4000, 'Keep it under 4000 characters'), imaging: z.string(), impression: z.string().trim().min(1, 'Clinical impression is required').max(4000, 'Keep it under 4000 characters'), status: z.string().min(1, 'Final status is required') })
type AssessForm = z.infer<typeof as>
const EMPTY_ASSESS: AssessForm = { pain: '', swelling: '', tenderness: '', rom: '', weight: '', neuro: '', notes: '', imaging: '', impression: '', status: '' }
const toAssessForm = (a: AssessmentDto | null | undefined): AssessForm => (a ? { pain: a.pain ?? '', swelling: a.swelling ?? '', tenderness: a.tenderness ?? '', rom: a.rom ?? '', weight: a.weight ?? '', neuro: a.neuro ?? '', notes: a.notes ?? '', imaging: a.imaging ?? '', impression: a.impression ?? '', status: a.status ?? '' } : EMPTY_ASSESS)

export function Assessment() {
  const { id } = useParams()
  const { user } = useAuth()
  const nav = useNavigate()
  const toast = useToast()
  const qc = useQueryClient()
  const ev = useEvents()
  const e = (ev.data ?? []).find((x) => String(x.id) === id)
  const existing = useQuery({ queryKey: ['assessment', id], queryFn: () => getAssessment(Number(id)), enabled: !!id && !user?.dev })
  const [err, setErr] = useState('')
  const [loadedFor, setLoadedFor] = useState<string | null>(null)
  const f = useForm<AssessForm>({ resolver: zodResolver(as), defaultValues: EMPTY_ASSESS })

  // Fill the form once with the saved assessment (editing never gets overwritten by a refresh)
  useEffect(() => {
    if (existing.isSuccess && loadedFor !== id) { f.reset(toAssessForm(existing.data)); setLoadedFor(id ?? null) }
  }, [existing.isSuccess, existing.data, id, loadedFor, f])

  const submit = f.handleSubmit(async (v) => {
    setErr('')
    try {
      const r = await saveAssessment(Number(id), v as AssessmentInput)
      qc.setQueryData(['assessment', id], r.assessment)
      qc.invalidateQueries({ queryKey: ['assessments'] })
      qc.invalidateQueries({ queryKey: ['events'] })
      toast(r.resolved ? `Assessment saved (${v.status}). Incident marked as reviewed.` : `Assessment saved (${v.status}). Incident stays in the review queue.`)
      nav(`/events/${id}`)
    } catch (x) {
      setErr(normalizeApiError(x))
    }
  })
    const S = (n: keyof AssessForm, l: string, o: string[]) => <Field key={n} label={l + ' *'} err={f.formState.errors[n]?.message}><select className={inp} {...f.register(n)}><option value="">Select…</option>{o.map((x) => <option key={x}>{x}</option>)}</select></Field>
  const saved = existing.data

  return (
    <>
      <PageHeader title={saved ? 'Edit medical assessment' : 'Medical assessment'} crumbs={[{ label: 'Events', to: '/events' }, { label: `#${id}`, to: `/events/${id}` }, { label: 'Assessment' }]} />
      <div className="mb-4"><Disclaimer /></div>
      {e && <Card className="mb-4"><p className="text-sm"><b>{e.player.name ?? 'Unidentified player'}</b> · {e.eventType} · {e.region ?? '—'} · <RiskBadge level={e.risk} /></p>{e.aiInjury ? <div className="mt-3"><PossibleInjuries e={e} /></div> : (e.injuryNote || e.note) && <p className="mt-1 text-sm text-slate-600">{e.injuryNote ?? e.note}</p>}<div className="mt-3"><SafetyMeasures eventType={e.eventType} region={e.region} risk={e.risk} /></div></Card>}
      {!e && !ev.isLoading ? (
        <Card><EmptyState title="Incident not found" text={ev.isError ? normalizeApiError(ev.error) : 'It may have been deleted (for example by Gemini as a false alarm).'} action={<Link className={btnS} to="/events">Back to events</Link>} /></Card>
      ) : (
        <Card>
          {user?.dev && <p className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Developer preview: log in with a medical account to save assessments.</p>}
          {saved && <p className="mb-4 flex flex-wrap items-center gap-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-600"><Badge tone={STATUS_TONE[saved.status] ?? 'gray'}>{saved.status}</Badge>Last saved by <b>{saved.saved_by}</b> on {fmtDate(saved.saved_at)}{saved.revision && saved.revision > 1 ? ` · edited ${saved.revision - 1} time(s)` : ''}</p>}
          {existing.isError && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">Could not load the saved assessment: {normalizeApiError(existing.error)}</p>}
          {existing.isLoading && !user?.dev ? <div className="space-y-2"><Skeleton /><Skeleton /><Skeleton /></div> : (
            <form className="grid gap-4 md:grid-cols-2" noValidate onSubmit={submit}>
              {S('pain', 'Pain', sel)}{S('swelling', 'Swelling', sel)}{S('tenderness', 'Tenderness', ['Present', 'Absent', 'Not assessed'])}{S('rom', 'Range of motion', ['Normal', 'Reduced', 'Unable', 'Not assessed'])}{S('weight', 'Weight bearing', ['Normal', 'Painful', 'Unable', 'Not assessed'])}{S('neuro', 'Neurovascular observations', ['Normal', 'Abnormal', 'Not assessed'])}
              <div className="md:col-span-2"><Field label="General observations" err={f.formState.errors.notes?.message}><textarea rows={3} className={inp} {...f.register('notes')} /></Field></div>
              <Field label="Imaging considered (clinician choice)"><select className={inp} {...f.register('imaging')}><option value="">None</option>{['X-ray', 'MRI', 'CT', 'Ultrasound'].map((x) => <option key={x}>{x}</option>)}</select></Field>
              <div>{S('status', 'Final status', ASSESS_STATUS)}<p className="mt-1 text-xs text-slate-500">Saving marks the incident as reviewed. "Under observation" keeps it in the review queue.</p></div>
              <div className="md:col-span-2"><Field label="Clinical impression *" err={f.formState.errors.impression?.message}><textarea rows={3} className={inp} {...f.register('impression')} /></Field></div>
              {err && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800 md:col-span-2">{err}</p>}
              <div className="flex justify-end gap-2 md:col-span-2"><button type="button" className={btnS} onClick={() => { f.reset(toAssessForm(saved)); setErr('') }}>{saved ? 'Undo changes' : 'Reset'}</button><button className={btnP} disabled={f.formState.isSubmitting || !!user?.dev}>{f.formState.isSubmitting ? 'Saving…' : saved ? 'Update assessment' : 'Save assessment'}</button></div>
            </form>
          )}
        </Card>
      )}
    </>
  )
}
/* ---------- ALERTS (built from the events feed: priority = risk, unread = not resolved) ---------- */
export function Alerts() {
  const { user } = useAuth()
  return user && user.role !== 'ADMIN' && !user.dev ? <StaffAlerts /> : <AdminAlerts />
}
function AdminAlerts() {
  const [pri, setPri] = useState('All')
  const [read, setRead] = useState('All')
  const toast = useToast()
  const ev = useEvents()
  const list = (ev.data ?? []).filter((e) => (pri === 'All' || e.risk === pri.toUpperCase()) && (read === 'All' || (read === 'Unread' ? !e.resolved : e.resolved))).sort(byRisk)
  return (
    <>
      <PageHeader title="Alerts" crumbs={[{ label: 'Alerts' }]} actions={<button className={btnS} onClick={() => toast(NC, true)}><CheckCheck size={16} />Mark all as read</button>} />
      <Card className="!p-0">
        <div className="flex flex-wrap gap-2 border-b p-3">{['All', 'High', 'Medium', 'Low'].map((p) => <button key={p} aria-pressed={pri === p} onClick={() => setPri(p)} className={`${btn} ${pri === p ? 'bg-[#0b1f3a] text-white' : 'border border-slate-300'}`}>{p}</button>)}<select aria-label="Read state" className={inpAuto + ' ml-auto'} value={read} onChange={(e) => setRead(e.target.value)}><option>All</option><option>Unread</option><option>Read</option></select></div>
        {ev.isLoading ? <div className="space-y-2 p-4"><Skeleton /><Skeleton /></div>
          : ev.isError ? <ErrorState title="Unable to load alerts" text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} />
          : list.length === 0 ? <EmptyState title="No alerts" text="High, medium and low priority alerts will appear here, with unread alerts highlighted." />
          : <ul className="divide-y divide-slate-100">{list.map((e) => (
            <li key={e.id} className={!e.resolved ? 'bg-sky-50/40' : ''}>
              <Link to={`/events/${e.id}`} className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50">
                {!e.resolved && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-sky-500" aria-label="Unread" />}
                <div className="min-w-0 flex-1"><p className="text-sm font-medium">{e.player.name ?? 'Unidentified player'} · {e.eventType} · {e.region ?? '—'}</p><p className="truncate text-xs text-slate-500">{injuryText(e) ?? ''}</p><p className="text-xs text-slate-400">{fmtDate(e.timestamp)}{e.matchName ? ` · ${e.matchName}` : ''}</p></div>
                <RiskBadge level={e.risk} />
              </Link>
            </li>
          ))}</ul>}
      </Card>
    </>
  )
}

/* ---------- ADMIN / SETTINGS / HELP / ERRORS ---------- */
/** Live status: backend and database checks, plus what the detector reported (src/system_status.py). Refreshes every 5 s. */
const TRACKER_LABEL: Record<string, string> = { botsort: 'BoT-SORT', bytetrack: 'ByteTrack' }
const ago = (sec: number | null | undefined) => (sec === null || sec === undefined ? '—' : sec < 60 ? `${sec} s ago` : sec < 3600 ? `${Math.round(sec / 60)} min ago` : `${Math.round(sec / 3600)} h ago`)
const pct = (a?: number, b?: number | null) => (a && b ? Math.min(100, Math.round((100 * a) / b)) : null)

function StatusCard({ title, badge, tone, children }: { title: string; badge: string; tone: Tone; children?: ReactNode }) {
  return (
    <Card>
      <p className="text-xs text-slate-500">{title}</p>
      <div className="mt-2"><Badge tone={tone}>{badge}</Badge></div>
      {children && <div className="mt-2 space-y-0.5 text-xs text-slate-600">{children}</div>}
    </Card>
  )
}

export function System() {
  const { user } = useAuth()
  const dev = !!user?.dev
  const q = useQuery({ queryKey: ['system'], queryFn: getSystemStatus, enabled: !dev, refetchInterval: 5000 })
  const d: SystemDto | undefined = q.data
  const det = d?.detector
  const info: DetectorInfoDto = det?.info ?? {}
  const prog: SystemDto['detector']['progress'] = det?.progress ?? {}
  const reported = !!det && det.state !== 'never'
  const notYet = <p>Shown after the detector runs once.</p>

  const detBadge: Record<string, [string, Tone]> = {
    running: ['Running', 'green'],
    starting: ['Starting', 'amber'],
    finished: ['Idle', 'blue'],
    stopped: ['Stopped unexpectedly', 'red'],
    never: ['Not run yet', 'gray'],
  }
  const [dLabel, dTone] = detBadge[det?.state ?? 'never']
  const progress = pct(prog.frame, info.total_frames)
  const idTotal = d?.identity.events ?? 0
  const idRate = idTotal ? Math.round((100 * (d?.identity.identified ?? 0)) / idTotal) : null

  return (
    <>
      <PageHeader title="System status" crumbs={[{ label: 'System' }]} actions={
        <button className={btnS} disabled={dev || q.isFetching} onClick={() => q.refetch()}><RefreshCw size={16} className={q.isFetching ? 'animate-spin' : ''} />Refresh</button>} />
      {dev ? <Card><EmptyState title="System status unavailable" text="Log in with a real account to see live status." /></Card>
        : q.isLoading ? <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">{Array.from({ length: 10 }).map((_, i) => <Card key={i}><Skeleton className="h-16 w-full" /></Card>)}</div>
        : q.isError || !d ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatusCard title="Backend" badge="Offline" tone="red"><p>{normalizeApiError(q.error)}</p></StatusCard>
            <StatusCard title="Database" badge="Unknown" tone="gray"><p>Needs the backend.</p></StatusCard>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <StatusCard title="Backend" badge="Online" tone="green"><p>FastAPI · Python {d.backend.python}</p></StatusCard>

            <StatusCard title="Database" badge={d.database.ok ? 'Online' : 'Offline'} tone={d.database.ok ? 'green' : 'red'}>
              {d.database.ok ? <><p className="capitalize">{d.database.engine}</p><p>{d.database.users} users · {d.database.teams} teams · {d.database.players} players</p><p>{d.database.matches} matches · {d.database.events} events</p></> : <p>{d.database.detail}</p>}
            </StatusCard>

            <StatusCard title="Video processor" badge={dLabel} tone={dTone}>
              {det?.state === 'never' && <p>Run multi_player_injury.py and it appears here.</p>}
              {reported && <p className="truncate font-medium text-slate-700" title={info.match_name ?? ''}>{info.match_name ?? '—'}</p>}
              {(det?.state === 'running' || det?.state === 'starting') && <>
                <p>Frame {prog.frame ?? 0}{info.total_frames ? ` of ${info.total_frames}` : ''}{progress !== null ? ` (${progress}%)` : ''}</p>
                {progress !== null && <div className="h-1.5 rounded bg-slate-200"><div className="h-1.5 rounded bg-green-600" style={{ width: `${progress}%` }} /></div>}
                <p>{prog.events ?? 0} event(s) saved · last signal {ago(det.seconds_since_last_signal)}</p>
              </>}
              {det?.state === 'finished' && <p>Finished {fmtDate(det.finished_at ?? null)} · {prog.events ?? 0} event(s)</p>}
              {det?.state === 'stopped' && <p className="text-red-700">No signal since {fmtDate(det.last_seen ?? null)}. The detector was closed or crashed before finishing.</p>}
            </StatusCard>

            <StatusCard title="YOLO model" badge={reported ? info.pose_model ?? 'Unknown' : 'Not reported yet'} tone={reported ? 'green' : 'gray'}>
              {reported ? <><p>{info.device === 'GPU' ? `GPU${info.gpu_name ? ` · ${info.gpu_name}` : ''}` : 'CPU'}</p><p>Image size {info.imgsz ?? '—'}{info.model_file_mb ? ` · ${info.model_file_mb} MB` : ''}</p>{info.model_task && <p className="capitalize">Task: {info.model_task}</p>}</> : notYet}
            </StatusCard>

            <StatusCard title="Tracker" badge={reported ? TRACKER_LABEL[info.tracker_type ?? ''] ?? info.tracker_type ?? 'Unknown' : 'Not reported yet'} tone={reported ? 'green' : 'gray'}>
              {reported ? <><p>Re-identification: {info.tracker_reid === true ? 'on' : info.tracker_reid === false ? 'off' : '—'}</p><p className="truncate" title={info.tracker_file ?? ''}>{info.tracker_file}</p></> : notYet}
            </StatusCard>

            <StatusCard title="OCR" badge={!reported ? 'Not reported yet' : !info.identification ? 'Off' : info.ocr_engines?.length ? info.ocr_engines.join(', ') : 'Not loaded'} tone={!reported ? 'gray' : !info.identification ? 'gray' : info.ocr_engines?.length ? 'green' : 'amber'}>
              {reported ? <p>{info.identification ? 'Reads jersey numbers and names on shirts' : 'Player identification is switched off in the detector'}</p> : notYet}
            </StatusCard>

            <StatusCard title="Identity service" badge={!reported ? (idTotal ? `${idRate}% identified` : 'Not reported yet') : !info.identification ? 'Off' : info.face_ready ? 'Jersey + face' : 'Jersey only'} tone={!reported ? (idTotal ? 'blue' : 'gray') : !info.identification ? 'gray' : 'green'}>
              {reported && info.identification && <p>Face: {!info.face_enabled ? 'off' : info.face_ready ? `on${info.face_engines?.length ? ` (${info.face_engines.join(', ')})` : ''}` : 'waiting for first jersey read'}</p>}
              <p>{d.identity.identified ?? 0} of {idTotal} events identified{idRate !== null ? ` (${idRate}%)` : ''}</p>
              {Object.entries(d.identity.by_method ?? {}).slice(0, 3).map(([m, c]) => <p key={m}>{METHOD_LABELS[m] ?? m}: {c}</p>)}
              {reported && <p>Gemini check: {!info.gemini_enabled ? 'off' : info.gemini_available ? `on · ${d.identity.gemini_checked ?? 0} checked` : 'no API key'}</p>}
            </StatusCard>

            <StatusCard title="Medical knowledge base" badge={d.medical_knowledge_base.ok ? 'Loaded' : 'Not available'} tone={d.medical_knowledge_base.ok ? 'green' : 'red'}>
              {d.medical_knowledge_base.ok ? <><p>{d.medical_knowledge_base.injury_notes} injury notes</p><p>{d.medical_knowledge_base.safety_measure_sets} safety measure sets ({d.medical_knowledge_base.safety_measure_steps} steps)</p><p>Risk levels: {(d.medical_knowledge_base.risk_levels ?? []).join(', ')}</p></> : <p>{d.medical_knowledge_base.detail}</p>}
            </StatusCard>

            <StatusCard title="Last job" badge={d.last_job ? `${d.last_job.events} event(s)` : 'No matches yet'} tone={d.last_job ? 'blue' : 'gray'}>
              {d.last_job && <><p className="truncate font-medium text-slate-700" title={d.last_job.name}>{d.last_job.name}</p><p>{fmtDate(d.last_job.date)}</p><p>{d.last_job.identified} of {d.last_job.events} identified</p><Link to={`/matches/${d.last_job.id}`} className={btnSm + ' mt-1'}><ExternalLink size={14} />Open match</Link></>}
            </StatusCard>

            <StatusCard title="Model version" badge={reported && info.ultralytics_version ? `Ultralytics ${info.ultralytics_version}` : 'Not reported yet'} tone={reported ? 'green' : 'gray'}>
              {reported ? <><p>PyTorch {info.torch_version ?? '—'}{info.cuda_version ? ` · CUDA ${info.cuda_version}` : ''}</p><p>OpenCV {info.opencv_version ?? '—'}</p></> : notYet}
            </StatusCard>
          </div>
        )}
      {!dev && d && <p className="mt-3 text-xs text-slate-500">Checked {new Date(d.checked_at).toLocaleTimeString()} · refreshes every 5 s. Detector details come from its last run; it reports every 5 s while running.</p>}
    </>
  )
}

export function Settings() {
  const { user } = useAuth()
  if (user?.role === 'PLAYER') return <Navigate to="/player/profile" replace />
  return user && user.role !== 'ADMIN' && !user.dev ? <StaffSettings /> : <AdminSettings />
}

function AdminSettings() {
  const { user } = useAuth()
  const toast = useToast()
  const [tab, setTab] = useState('Profile')
  return (
    <>
      <PageHeader title="Settings" crumbs={[{ label: 'Settings' }]} />
      <div role="tablist" className="mb-4 flex gap-1 border-b">{['Profile', 'Preferences', 'Notifications', 'Security'].map((t) => <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`px-4 py-2 text-sm ${tab === t ? 'border-b-2 border-[#0b1f3a] font-semibold' : 'text-slate-500'}`}>{t}</button>)}</div>
      <Card className="max-w-xl space-y-3">
        {tab === 'Profile' && <><Field label="Name"><input className={inp} defaultValue={user?.name} /></Field><Field label="Role"><input className={inp} value={user?.role} readOnly /></Field></>}
        {tab === 'Preferences' && <Field label="Time format"><select className={inp}><option>24-hour</option><option>12-hour</option></select></Field>}
        {tab === 'Notifications' && ['High-risk alerts', 'Medium-risk alerts', 'Low-risk alerts'].map((n) => <label key={n} className="flex items-center gap-2 text-sm"><input type="checkbox" defaultChecked />{n}</label>)}
        {tab === 'Security' && <><Field label="Current password"><input type="password" className={inp} /></Field><Field label="New password"><input type="password" className={inp} /></Field></>}
        <button className={btnP} onClick={() => toast(NC, true)}>Save changes</button>
      </Card>
    </>
  )
}

export function Help() {
  return (
    <>
      <PageHeader title="Help &amp; about" crumbs={[{ label: 'Help' }]} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card><h2 className="font-semibold">About AthleteGuard</h2><p className="mt-2 text-sm text-slate-600">AI-Powered Football Injury Detection &amp; Medical Decision Support. Match video is analyzed for player tracking, identity, collisions and abnormal movement; incidents are routed to staff for review.</p></Card>
        <Card><h2 className="font-semibold">Roles</h2><ul className="mt-2 list-disc pl-5 text-sm text-slate-600"><li><b>Admin</b>: teams, players, matches, users, system. No clinical notes.</li><li><b>Medical</b>: review incidents and record clinical assessments.</li><li><b>Coach</b>: own team only; event status, no clinical notes.</li></ul></Card>
        <div className="lg:col-span-2"><Disclaimer /></div>
        <Card><h2 className="font-semibold">Support</h2><p className="mt-2 text-sm text-slate-600">Contact your system administrator. Support contact details are not configured.</p></Card>
      </div>
    </>
  )
}

export function ErrorPage({ kind }: { kind: '403' | '404' | 'network' | 'generic' }) {
  const { user } = useAuth()
  const I = { '403': Lock, '404': FileQuestion, network: WifiOff, generic: ServerCrash }[kind]
  const T = { '403': ['Access denied', 'You don’t have permission to access this page.'], '404': ['Page not found', 'The page you requested does not exist.'], network: ['Network unavailable', 'Check your connection and try again.'], generic: ['Something went wrong', 'An unexpected error occurred. Please try again.'] }[kind]
  return <div className="grid place-items-center py-20 text-center"><I className="text-slate-400" size={48} /><h1 className="mt-3 text-2xl font-bold">{T[0]}</h1><p className="mt-1 text-slate-500">{T[1]}</p><Link className={btnP + ' mt-5'} to={user ? home[user.role] : '/login'}>Back to dashboard</Link></div>
}

/* =====================================================================
   MEDICAL STAFF AND COACH FEATURES
   Only used when the logged-in user is not an admin: admin pages keep their own components above.
   ===================================================================== */

/** Marks alerts as read for this user (optimistic: the list updates at once). */
function useMarkRead() {
  const qc = useQueryClient()
  return async (ids: number[]) => {
    const cur = qc.getQueryData<number[]>(['alertReads']) ?? []
    const add = ids.filter((i) => !cur.includes(i))
    if (!add.length) return
    qc.setQueryData(['alertReads'], [...cur, ...add])
    try {
      qc.setQueryData(['alertReads'], await markAlertsRead(add))
    } catch (e) {
      qc.invalidateQueries({ queryKey: ['alertReads'] })
      throw e
    }
  }
}

/* ---------- event detail: assessment outcome + review state ---------- */
function AssessmentCard({ e, a, loading }: { e: InjuryEvent; a: AssessmentDto | null; loading: boolean }) {
  const { user } = useAuth()
  const toast = useToast()
  const refresh = useRefreshAll()
  const [busy, setBusy] = useState(false)
  const medical = user?.role === 'MEDICAL'

  const setReviewed = async (v: boolean) => {
    setBusy(true)
    try {
      if (v) await resolveEvent(e.id)
      else await reopenEvent(e.id)
      toast(v ? 'Marked as reviewed.' : 'Reopened: the incident is back in the review queue.')
      refresh()
    } catch (x) {
      toast(normalizeApiError(x), true)
    } finally {
      setBusy(false)
    }
  }

  const Item = ({ l, v }: { l: string; v?: string }) => <div><dt className="text-xs text-slate-500">{l}</dt><dd className="font-medium">{v || '—'}</dd></div>

  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-auto font-semibold">Medical assessment</h2>
        {a && <Badge tone={STATUS_TONE[a.status] ?? 'gray'}>{a.status}</Badge>}
        <Badge tone={e.resolved ? 'green' : 'gray'}>{e.resolved ? 'Reviewed' : 'Pending review'}</Badge>
      </div>
      {loading ? <div className="mt-3 space-y-2"><Skeleton /><Skeleton /></div>
        : !a ? (
          <p className="mt-2 text-sm text-slate-500">{medical ? 'No assessment recorded yet. Examine the player, then record the findings.' : 'Medical staff have not recorded an assessment for this incident yet.'}</p>
        ) : medical ? (
          <>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Item l="Pain" v={a.pain} /><Item l="Swelling" v={a.swelling} /><Item l="Tenderness" v={a.tenderness} /><Item l="Range of motion" v={a.rom} />
              <Item l="Weight bearing" v={a.weight} /><Item l="Neurovascular" v={a.neuro} /><Item l="Imaging considered" v={a.imaging || 'None'} /><Item l="Final status" v={a.status} />
            </dl>
            <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm"><p className="text-xs font-semibold uppercase text-slate-500">Clinical impression</p><p className="whitespace-pre-wrap">{a.impression}</p>{a.notes && <><p className="mt-2 text-xs font-semibold uppercase text-slate-500">General observations</p><p className="whitespace-pre-wrap">{a.notes}</p></>}</div>
          </>
        ) : (
          <p className="mt-2 text-sm text-slate-700">Outcome: <b>{a.status}</b>{a.status === 'Cleared' ? ' — the player has been cleared by medical staff.' : '.'} <span className="text-slate-500">Clinical notes are visible to medical staff only.</span></p>
        )}
      {a && <p className="mt-2 text-xs text-slate-500">Recorded by {a.saved_by} on {fmtDate(a.saved_at)}{a.revision && a.revision > 1 ? ` · edited ${a.revision - 1} time(s)` : ''}</p>}
      {medical && (
        <div className="mt-3 flex flex-wrap gap-2">
          <Link className={btnSm} to={`/events/${e.id}/assessment`}>{a ? <><Pencil size={14} />Edit assessment</> : <><ClipboardPlus size={14} />Record assessment</>}</Link>
          {e.resolved
            ? <button className={btnSm} disabled={busy} onClick={() => setReviewed(false)}><RotateCcw size={14} />Reopen for review</button>
            : <button className={btnSm} disabled={busy} onClick={() => setReviewed(true)}><CheckCircle2 size={14} />Mark as reviewed</button>}
        </div>
      )}
    </Card>
  )
}

/* ---------- alerts with a per-user read state ---------- */
function StaffAlerts() {
  const { user } = useAuth()
  const [pri, setPri] = useState('All')
  const [read, setRead] = useState('All')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const ev = useEvents()
  const reads = useAlertReads()
  const markRead = useMarkRead()
  const readSet = new Set(reads.data ?? [])
  const all = ev.data ?? []
  const shown = all
  const unread = shown.filter((e) => !readSet.has(e.id))
  const list = shown
    .filter((e) => (pri === 'All' || e.risk === pri.toUpperCase()) && (read === 'All' || (read === 'Unread' ? !readSet.has(e.id) : readSet.has(e.id))))
    .sort((a, b) => byRisk(a, b) || +new Date(b.timestamp) - +new Date(a.timestamp))

  const markAll = async () => {
    if (!unread.length) { toast('Every alert is already read.'); return }
    setBusy(true)
    try { await markRead(unread.map((e) => e.id)); toast(`Marked ${unread.length} alert(s) as read.`) } catch (x) { toast(normalizeApiError(x), true) } finally { setBusy(false) }
  }
  const open = (id: number) => { markRead([id]).catch(() => undefined) }

  return (
    <>
      <PageHeader title="Alerts" crumbs={[{ label: 'Alerts' }]} actions={<button className={btnS} disabled={busy || reads.isLoading} onClick={markAll}><CheckCheck size={16} />Mark all as read{unread.length > 0 && ` (${unread.length})`}</button>} />
      <Card className="!p-0">
        <div className="flex flex-wrap items-center gap-2 border-b p-3">{['All', 'High', 'Medium', 'Low'].map((p) => <button key={p} aria-pressed={pri === p} onClick={() => setPri(p)} className={`${btn} ${pri === p ? 'bg-[#0b1f3a] text-white' : 'border border-slate-300'}`}>{p}</button>)}<span className="ml-auto text-sm text-slate-500">{unread.length} unread</span><select aria-label="Read state" className={inpAuto} value={read} onChange={(e) => setRead(e.target.value)}><option>All</option><option>Unread</option><option>Read</option></select></div>
        {ev.isLoading ? <div className="space-y-2 p-4"><Skeleton /><Skeleton /></div>
          : ev.isError ? <ErrorState title="Unable to load alerts" text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} />
          : list.length === 0 ? <EmptyState title={read === 'Unread' ? 'No unread alerts' : 'No alerts'} text={read === 'Unread' ? 'You are all caught up.' : 'High, medium and low priority alerts will appear here, with unread alerts highlighted.'} />
          : <ul className="divide-y divide-slate-100">{list.map((e) => {
            const isUnread = !readSet.has(e.id)
            return (
              <li key={e.id} className={isUnread ? 'bg-sky-50/40' : ''}>
                <Link to={`/events/${e.id}`} onClick={() => open(e.id)} className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${isUnread ? 'bg-sky-500' : 'bg-transparent'}`} aria-label={isUnread ? 'Unread' : 'Read'} />
                  <div className="min-w-0 flex-1"><p className={`text-sm ${isUnread ? 'font-semibold' : 'font-medium text-slate-700'}`}>{e.player.name ?? 'Unidentified player'} · {e.eventType} · {e.region ?? '—'}</p><p className="truncate text-xs text-slate-500">{injuryText(e) ?? ''}</p><p className="text-xs text-slate-400">{fmtDate(e.timestamp)}{e.matchName ? ` · ${e.matchName}` : ''}{e.resolved ? ' · reviewed by medical staff' : ''}</p></div>
                  <RiskBadge level={e.risk} />
                </Link>
              </li>
            )
          })}</ul>}
      </Card>
    </>
  )
}

/* ---------- settings (medical staff and coaches): a full-page profile. Only the admin can change these details. ---------- */
export const ROLE_ACCESS: Record<Role, string[]> = {
  ADMIN: [],
  COACH: [
    'See your own team\'s incidents and every unidentified fall',
    'Identify the player in an unidentified fall from its clip',
    'Add and edit your players\' previous injury history',
    'Upload reference photos of your players',
    'Download the injury report as PDF',
  ],
  MEDICAL: [
    'Review every incident from both teams',
    'Record medical assessments and mark incidents as reviewed',
    'Log manual events seen by staff',
    'Correct the identified player of any fall',
    'Download the injury report as PDF',
  ],
  PLAYER: [
    'See your own falls with the clip, possible injuries and expected rest',
    'See your previous injury history',
    'See the outcome of your medical review',
    'Download your own injury report as PDF',
  ],
}

function StaffSettings() {
  const { user } = useAuth()
  const me = useQuery({ queryKey: ['me'], queryFn: getMe })
  const teams = useTeams()
  const ev = useEvents()
  const assessments = useAssessments(user?.role === 'MEDICAL')
  if (!user) return null

  const coach = user.role === 'COACH'
  const name = me.data?.username ?? user.name
  const teamName = me.data?.teamName ?? null
  const myTeam = coach ? (teams.data ?? [])[0] : undefined
  const events = ev.data ?? []
  const mySaved = (assessments.data ?? []).filter((a) => a.saved_by === name)

  const Info = ({ label, value }: { label: string; value: ReactNode }) => (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 py-3.5 last:border-0">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="flex items-center gap-2 text-right text-sm font-semibold text-slate-800">{value}<Lock size={13} className="shrink-0 text-slate-300" aria-label="Set by the administrator" /></dd>
    </div>
  )
  const Stat = ({ label, value, tone = '' }: { label: string; value: ReactNode; tone?: string }) => (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="text-xs text-slate-500">{label}</p><p className={`mt-1 text-2xl font-bold ${tone}`}>{value}</p></div>
  )

  const stats: [string, ReactNode, string?][] = coach
    ? [
        ['Players in your team', myTeam ? myTeam.playerCount : '—'],
        ['Team incidents', myTeam ? myTeam.injuryEvents : '—'],
        ['High-risk incidents', myTeam ? myTeam.highRiskEvents : '—', 'text-red-700'],
        ['Unidentified falls', ev.data ? events.filter((e) => !e.identified).length : '—', 'text-amber-600'],
      ]
    : [
        ['Waiting for review', ev.data ? events.filter((e) => !e.resolved).length : '—', 'text-amber-600'],
        ['High priority open', ev.data ? events.filter((e) => !e.resolved && e.risk === 'HIGH').length : '—', 'text-red-700'],
        ['Assessments you saved', assessments.data ? mySaved.length : '—'],
        ['Incidents reviewed', ev.data ? events.filter((e) => e.resolved).length : '—', 'text-green-700'],
      ]

  return (
    <>
      <PageHeader title="Profile" crumbs={[{ label: 'Profile' }]} />

      {/* Header banner across the full width */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="h-28 bg-gradient-to-r from-[#0b1f3a] via-[#16325c] to-sky-600" />
        <div className="flex flex-wrap items-end gap-5 px-6 pb-6">
          <span className="-mt-12 grid h-24 w-24 shrink-0 place-items-center rounded-2xl border-4 border-white bg-sky-500 text-4xl font-bold text-white shadow-md">{(name[0] || '?').toUpperCase()}</span>
          <div className="min-w-0 flex-1 pt-3">
            <h2 className="truncate text-2xl font-bold">{name}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              <Badge tone={ROLE_TONE[user.role]}>{ROLE_LABEL[user.role]}</Badge>
              {coach && <span className="flex items-center gap-1"><Shield size={14} />{me.isLoading ? 'Loading team…' : teamName ?? 'No team'}</span>}
              <span className="flex items-center gap-1"><CheckCircle2 size={14} className="text-green-600" />Active account</span>
            </div>
          </div>
          <p className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500"><Lock size={13} />Managed by the administrator</p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {/* Personal and account details */}
        <Card className="lg:col-span-2">
          <h2 className="font-semibold">Account details</h2>
          <p className="text-xs text-slate-500">These details are set by the administrator and cannot be changed here.</p>
          {me.isError && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{normalizeApiError(me.error)}</p>}
          <dl className="mt-2">
            <Info label="Username" value={name} />
            <Info label="Role" value={ROLE_LABEL[user.role]} />
            {coach && <Info label="Team" value={me.isLoading ? 'Loading…' : teamName ?? '—'} />}
            {coach && <Info label="Coach of" value={myTeam ? `${myTeam.playerCount} players` : '—'} />}
            <Info label="Data you can see" value={coach ? 'Your team + unidentified falls' : 'Both teams'} />
            <Info label="User ID" value={me.data ? `#${me.data.id}` : '—'} />
            <Info label="Account status" value={<span className="text-green-700">Active</span>} />
          </dl>
        </Card>

        {/* What this role can do */}
        <Card>
          <h2 className="font-semibold">What you can do</h2>
          <p className="text-xs text-slate-500">Access given to the {ROLE_LABEL[user.role].toLowerCase()} role.</p>
          <ul className="mt-3 space-y-2.5">
            {ROLE_ACCESS[user.role].map((t) => <li key={t} className="flex items-start gap-2 text-sm text-slate-700"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-green-600" />{t}</li>)}
          </ul>
          <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">Need a change to your username, role{coach ? ', team' : ''} or password? Contact your administrator.</p>
        </Card>
      </div>

      {/* Activity summary */}
      <Card className="mt-4">
        <h2 className="font-semibold">{coach ? 'Your team at a glance' : 'Your review work at a glance'}</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {stats.map(([l, v, t]) => <Stat key={l} label={l} value={ev.isLoading ? '…' : v} tone={t} />)}
        </div>
      </Card>
    </>
  )
}

/* ---------- player reference photos (known_players folder, used for face recognition) ---------- */
const PHOTO_RE = /\.(jpe?g|png|webp|bmp)$/i
const MAX_PHOTO_MB = 8

function PhotoThumb({ playerId, name, onDelete }: { playerId: number; name: string; onDelete: () => void }) {
  const q = useQuery({ queryKey: ['photo', playerId, name], queryFn: () => getPlayerPhotoBlob(playerId, name), staleTime: Infinity })
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!q.data) return
    const u = URL.createObjectURL(q.data)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [q.data])
  return (
    <figure className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="grid aspect-square place-items-center bg-slate-100">
        {url ? <img src={url} alt={`Reference photo ${name}`} className="h-full w-full object-cover" /> : q.isError ? <ImageOff className="text-slate-400" /> : <Loader2 className="animate-spin text-slate-400" />}
      </div>
      <figcaption className="flex items-center gap-2 p-2 text-xs"><span className="min-w-0 flex-1 truncate text-slate-600" title={name}>{name}</span><button aria-label={`Delete ${name}`} title="Delete photo" className="text-red-600 hover:text-red-800" onClick={onDelete}><Trash2 size={14} /></button></figcaption>
    </figure>
  )
}

function PlayerPhotos({ playerId, name }: { playerId: number; name: string }) {
  const qc = useQueryClient()
  const toast = useToast()
  const q = useQuery({ queryKey: ['photos', playerId], queryFn: () => getPlayerPhotos(playerId) })
  const [left, setLeft] = useState(0)
  const [del, setDel] = useState<string | null>(null)

  const upload = async (files: FileList | null) => {
    const list = Array.from(files ?? [])
    if (!list.length) return
    const bad = list.filter((x) => !PHOTO_RE.test(x.name) || x.size > MAX_PHOTO_MB * 1024 * 1024)
    const good = list.filter((x) => !bad.includes(x))
    if (bad.length) toast(`Skipped ${bad.map((x) => x.name).join(', ')}: use JPG, PNG, WEBP or BMP up to ${MAX_PHOTO_MB} MB.`, true)
    let done = 0
    for (let i = 0; i < good.length; i++) {
      setLeft(good.length - i)
      try { await uploadPlayerPhoto(playerId, good[i]); done++ } catch (x) { toast(`${good[i].name}: ${normalizeApiError(x)}`, true) }
    }
    setLeft(0)
    if (done) toast(`Uploaded ${done} photo(s) for ${name}.`)
    qc.invalidateQueries({ queryKey: ['photos', playerId] })
  }

  const remove = async (file: string) => {
    try {
      await deletePlayerPhoto(playerId, file)
      toast('Photo deleted.')
      qc.invalidateQueries({ queryKey: ['photos', playerId] })
    } catch (x) {
      toast(normalizeApiError(x), true)
    }
  }

  if (q.isLoading) return <div className="space-y-2"><Skeleton /><Skeleton /></div>
  if (q.isError) return <ErrorState title="Reference photos unavailable" text={normalizeApiError(q.error)} onRetry={() => q.refetch()} />
  const d = q.data!

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start gap-3">
        <p className="min-w-0 flex-1 text-sm text-slate-600">Add clear photos of {name}'s face (front, and side if you have them). They are saved in the <code>known_players</code> folder as <b>{d.folder}</b>. The detector loads them the next time it starts and uses them to recognise the player by face.</p>
        <label className={btnP + (left ? ' pointer-events-none opacity-60' : ' cursor-pointer')}>
          {left ? <Loader2 size={16} className="animate-spin" /> : <Upload size={16} />}{left ? `Uploading… ${left} left` : 'Upload photos'}
          <input type="file" accept=".jpg,.jpeg,.png,.webp,.bmp,image/jpeg,image/png,image/webp,image/bmp" multiple className="sr-only" disabled={!!left} onChange={(e) => { upload(e.target.files); e.target.value = '' }} />
        </label>
      </div>
      {d.photos.length === 0 ? <EmptyState title="No reference photos yet" text="Upload one or more face photos to help the detector recognise this player." />
        : <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{d.photos.map((ph) => <PhotoThumb key={ph.name} playerId={playerId} name={ph.name} onDelete={() => setDel(ph.name)} />)}</div>}
      <p className="text-xs text-slate-500">{d.photos.length} photo(s) uploaded · {d.auto_learned} face(s) learned automatically by the detector during matches.</p>
      <Confirm open={!!del} title="Delete photo?" text={`${del ?? ''} will be removed from ${d.folder}. The detector stops using it the next time it starts.`} confirmLabel="Delete photo" onConfirm={() => { if (del) remove(del) }} onClose={() => setDel(null)} />
    </div>
  )
}

/* ---------- match processing status from the detector's heartbeat ---------- */
function matchState(d: DetectorProgressDto | undefined, matchId: number, known: boolean): { label: string; tone: Tone; pct: number | null; live: boolean } {
  if (d && d.match_id === matchId) {
    if (d.state === 'running' || d.state === 'starting') {
      const pct = d.frame && d.total_frames ? Math.min(100, Math.round((100 * d.frame) / d.total_frames)) : null
      return { label: d.state === 'starting' ? 'Starting' : 'Processing', tone: 'blue', pct, live: true }
    }
    if (d.state === 'stopped') return { label: 'Stopped early', tone: 'amber', pct: null, live: false }
  }
  return known ? { label: 'Completed', tone: 'green', pct: null, live: false } : { label: 'Status unknown', tone: 'gray', pct: null, live: false }
}

function MatchStatusBadge({ matchId, known }: { matchId: number; known: boolean }) {
  const s = matchState(useDetector().data, matchId, known)
  return <Badge tone={s.tone}>{s.live && <Loader2 size={12} className="animate-spin" />}{s.label}{s.pct !== null && ` · ${s.pct}%`}</Badge>
}

function MatchProgress({ matchId, events, known }: { matchId: number; events: number; known: boolean }) {
  const d = useDetector()
  const s = matchState(d.data, matchId, known)
  const p = d.data
  return (
    <Card>
      <h2 className="font-semibold">AI processing</h2>
      <p className="mt-2 text-sm">Status: <MatchStatusBadge matchId={matchId} known={known} /></p>
      {s.live && p ? (
        <div className="mt-3">
          <div className="h-2 overflow-hidden rounded bg-slate-200"><div className={`h-2 rounded bg-sky-500 transition-all ${s.pct === null ? 'w-1/3 animate-pulse' : ''}`} style={s.pct !== null ? { width: `${s.pct}%` } : undefined} /></div>
          <p className="mt-1 text-xs text-slate-500">{p.frame ? `Frame ${p.frame.toLocaleString()}${p.total_frames ? ` of ${p.total_frames.toLocaleString()}` : ''}` : 'Loading the video…'} · {p.events ?? events} event(s) so far · updates every 5 s</p>
        </div>
      ) : s.label === 'Stopped early' ? (
        <p className="mt-2 text-sm text-slate-600">The detector stopped before the end of the video. The {events} event(s) found so far are kept.</p>
      ) : (
        <p className="mt-2 text-sm text-slate-600">{known ? `Analysis finished · ${events} event(s) detected.` : 'This match has not been reported by the detector.'}</p>
      )}
      <p className="mt-3 text-xs text-slate-500">Only administrators can start an analysis.</p>
    </Card>
  )
}