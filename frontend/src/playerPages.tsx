/* =====================================================================
   PLAYER DASHBOARD
   A player login (created by the admin in Users -> Create user -> Player) only sees
   their own data: profile, previous injury history, current injury events and report.
   The backend filters every list to that one player.
   ===================================================================== */
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, CheckCircle2, Download, ExternalLink, FileText, HeartPulse, Lock, Shield, ShieldAlert, ShieldCheck, Timer, Watch } from 'lucide-react'
import { useAuth } from './auth'
import { getMe } from './api/services'
import { normalizeApiError } from './api/client'
import { useAssessments, useEvents, useInjuryHistory } from './queries'
import type { InjuryEvent, RiskLevel } from './types'
import type { AssessmentDto } from './api/dto'
import { Badge, Card, EmptyState, ErrorState, Na, PageHeader, RiskBadge, SafetyMeasures, Skeleton, btnS } from './ui'
import { EventLine, PossibleInjuries, PreviousInjuries, ReportsPage, ROLE_ACCESS, STATUS_TONE, btnSm, fmtDate, fmtVideo } from './pages'

/** The logged-in player's account (name, jersey, team, coach). */
const useMe = () => {
  const { user } = useAuth()
  return useQuery({ queryKey: ['me'], queryFn: getMe, enabled: !!user && !user.dev })
}

const newestFirst = (a: InjuryEvent, b: InjuryEvent) => +new Date(b.timestamp) - +new Date(a.timestamp)

/** Match name without the date the backend adds ("fall_test - 19 Oct 2026 17:30" -> "fall_test"). */
const baseMatch = (m: string | null) => (m ?? '').replace(/\s+-\s+\d{1,2}\s+\w{3}\s+\d{4}.*$/, '').trim().toLowerCase()

/** The same match video analysed again gives the same fall again (same moment in the video,
 *  same body area). Keep only the newest of those, so every clip is shown once. */
function uniqueFalls(list: InjuryEvent[]): InjuryEvent[] {
  const kept: InjuryEvent[] = []
  for (const e of [...list].sort(newestFirst)) {
    const dup = e.videoTimeSec !== null && kept.some((k) => k.videoTimeSec !== null
      && Math.abs(k.videoTimeSec - e.videoTimeSec!) <= 2
      && baseMatch(k.matchName) === baseMatch(e.matchName)
      && (k.region ?? '').toLowerCase() === (e.region ?? '').toLowerCase()
      && k.eventType.toUpperCase() === e.eventType.toUpperCase())
    if (!dup) kept.push(e)
  }
  return kept
}

/** Assessment outcome per event (players get the status only, never the clinical notes). */
const useReviewByEvent = () => {
  const a = useAssessments()
  const map = new Map<number, AssessmentDto>()
  for (const r of a.data ?? []) map.set(r.event_id, r)
  return map
}

/** One fall: clip on the left, possible injuries, rest, safety measures and review status on the right. */
function FallCard({ e, review }: { e: InjuryEvent; review?: AssessmentDto }) {
  return (
    <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
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
          <span className="ml-auto">{review ? <Badge tone={STATUS_TONE[review.status] ?? 'gray'}>{review.status}</Badge> : <Badge tone={e.resolved ? 'green' : 'gray'}>{e.resolved ? 'Reviewed' : 'Waiting for medical review'}</Badge>}</span>
        </div>
        <PossibleInjuries e={e} />
        <SafetyMeasures eventType={e.eventType} region={e.region} risk={e.risk} />
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
          <dt className="text-slate-500">Match</dt><dd className="truncate" title={e.matchName ?? ''}>{e.matchName ?? 'No match'}</dd>
          <dt className="text-slate-500">Time in video</dt><dd><Na v={fmtVideo(e.videoTimeSec)} /></dd>
          <dt className="text-slate-500">Recorded</dt><dd>{fmtDate(e.timestamp)}</dd>
          {review && <><dt className="text-slate-500">Medical review</dt><dd>{review.status} · {fmtDate(review.saved_at)}</dd></>}
        </dl>
        <div className="mt-auto flex flex-wrap gap-2">
          <Link to={`/events/${e.id}`} className={btnSm}><ExternalLink size={14} />Open event</Link>
          {e.clipUrl && <a href={e.clipUrl} download className={btnSm}><Download size={14} />Download clip</a>}
        </div>
      </div>
    </div>
  )
}

function FallList({ list, loading, error, retry, emptyTitle, emptyText }: { list: InjuryEvent[]; loading: boolean; error: unknown; retry: () => void; emptyTitle: string; emptyText: string }) {
  const reviews = useReviewByEvent()
  if (loading) return <Card><div className="space-y-2"><Skeleton /><Skeleton /></div></Card>
  if (error) return <Card><ErrorState title="Unable to load your injury events" text={normalizeApiError(error)} onRetry={retry} /></Card>
  if (!list.length) return <Card><EmptyState title={emptyTitle} text={emptyText} /></Card>
  return <div className="space-y-3">{list.map((e) => <FallCard key={e.id} e={e} review={reviews.get(e.id)} />)}</div>
}

/* ---------- Dashboard helpers ---------- */
const RANK: Record<RiskLevel, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 }
const RISK_FILL: Record<RiskLevel, string> = { HIGH: '#ef4444', MEDIUM: '#f59e0b', LOW: '#22c55e' }
const worst = (list: InjuryEvent[]): RiskLevel | null =>
  list.reduce<RiskLevel | null>((w, e) => (e.risk && (!w || RANK[e.risk] > RANK[w]) ? e.risk : w), null)

type Zone = 'head' | 'torso' | 'hip' | 'rArm' | 'lArm' | 'rLeg' | 'lLeg'
/** Body area text from the detector ("RIGHT LEG", "Left knee", "Head") -> body map zones. */
function zonesOf(region: string | null): Zone[] {
  if (!region) return []
  const r = region.toLowerCase()
  const side = r.includes('left') ? 'l' : r.includes('right') ? 'r' : null
  const both = (a: Zone, b: Zone): Zone[] => (side === 'r' ? [a] : side === 'l' ? [b] : [a, b])
  if (/head|face|neck|skull|jaw|eye|nose/.test(r)) return ['head']
  if (/hip|pelvis|groin/.test(r)) return ['hip']
  if (/arm|shoulder|elbow|wrist|hand|finger|collar/.test(r)) return both('rArm', 'lArm')
  if (/leg|knee|ankle|thigh|foot|shin|calf|hamstring|toe|heel/.test(r)) return both('rLeg', 'lLeg')
  if (/chest|back|torso|rib|abdomen|spine|trunk|stomach/.test(r)) return ['torso']
  return []
}

/** "1-3 weeks", "2 days", "4-12 weeks" -> the upper number of days (14, 2, 84). */
function restDays(rest: string | null | undefined): number | null {
  if (!rest) return null
  const nums = rest.match(/\d+(\.\d+)?/g)
  if (!nums) return null
  const n = Math.max(...nums.map(Number))
  const r = rest.toLowerCase()
  return Math.round(n * (r.includes('month') ? 30 : r.includes('week') ? 7 : 1))
}

/** Same colour rules as the wristband during a match, applied to the player's open falls. */
function bandColour(open: InjuryEvent[]) {
  const c = (l: RiskLevel) => open.filter((e) => e.risk === l).length
  if (c('HIGH') > 0 || c('MEDIUM') >= 2) return { name: 'Red', hex: '#dc2626', text: 'Any high or 2+ medium falls', blink: true }
  if (c('MEDIUM') === 1 || c('LOW') >= 3) return { name: 'Amber', hex: '#f59e0b', text: '1 medium or 3+ low falls', blink: false }
  if (c('LOW') > 0) return { name: 'Green', hex: '#22c55e', text: '1–2 low falls', blink: false }
  return { name: 'Blue', hex: '#2563eb', text: 'No open falls', blink: false }
}

function StatusBanner({ open, rest }: { open: InjuryEvent[]; rest: string | null }) {
  const w = worst(open)
  const s = w === 'HIGH' ? { cls: 'from-red-600 to-red-500', icon: ShieldAlert, title: 'Rest advised', text: `You have a high-risk fall waiting for medical review${rest ? `. Expected rest ${rest}.` : '.'} Do not train until medical staff clear you.` }
    : w === 'MEDIUM' ? { cls: 'from-amber-500 to-orange-500', icon: ShieldAlert, title: 'Play with care', text: `A medium-risk fall needs a medical check${rest ? ` (expected rest ${rest})` : ''}. Tell medical staff if anything hurts.` }
    : w === 'LOW' ? { cls: 'from-emerald-600 to-green-500', icon: ShieldCheck, title: 'Minor knocks only', text: 'Only low-risk falls are open. Follow the safety measures and report any pain.' }
    : { cls: 'from-emerald-600 to-teal-500', icon: ShieldCheck, title: 'Fit to play', text: 'No open injury events. Keep it up.' }
  const I = s.icon
  return (
    <div className={`mb-4 flex items-center gap-4 rounded-2xl bg-gradient-to-r ${s.cls} p-5 text-white shadow-sm`}>
      <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-white/20"><I size={26} /></span>
      <div className="min-w-0"><p className="text-lg font-bold">{s.title}</p><p className="text-sm text-white/90">{s.text}</p></div>
    </div>
  )
}

function BodyMap({ list }: { list: InjuryEvent[] }) {
  const by = new Map<Zone, InjuryEvent[]>()
  for (const e of list) for (const z of zonesOf(e.region)) by.set(z, [...(by.get(z) ?? []), e])
  const fill = (z: Zone) => { const w = worst(by.get(z) ?? []); return w ? RISK_FILL[w] : '#e2e8f0' }
  const tip = (z: Zone, label: string) => { const n = by.get(z)?.length ?? 0; return `${label}: ${n} fall${n === 1 ? '' : 's'}` }
  const hit = [...by.entries()].sort((a, b) => b[1].length - a[1].length)
  const LABEL: Record<Zone, string> = { head: 'Head', torso: 'Chest / back', hip: 'Hip', rArm: 'Right arm', lArm: 'Left arm', rLeg: 'Right leg', lLeg: 'Left leg' }
  return (
    <Card className="h-full">
      <h2 className="font-semibold">Where you got hurt</h2>
      <p className="text-xs text-slate-500">All your detected falls, coloured by the highest risk.</p>
      <div className="mt-3 flex items-center gap-5">
        <svg viewBox="0 0 120 230" className="h-56 w-auto shrink-0" role="img" aria-label="Body map">
          <text x="10" y="12" fontSize="9" fill="#94a3b8">R</text><text x="104" y="12" fontSize="9" fill="#94a3b8">L</text>
          <circle cx="60" cy="22" r="15" fill={fill('head')} stroke="#fff" strokeWidth="2"><title>{tip('head', 'Head')}</title></circle>
          <rect x="38" y="40" width="44" height="62" rx="12" fill={fill('torso')} stroke="#fff" strokeWidth="2"><title>{tip('torso', 'Chest / back')}</title></rect>
          <rect x="40" y="100" width="40" height="22" rx="8" fill={fill('hip')} stroke="#fff" strokeWidth="2"><title>{tip('hip', 'Hip')}</title></rect>
          <rect x="18" y="42" width="17" height="72" rx="8" fill={fill('rArm')} stroke="#fff" strokeWidth="2"><title>{tip('rArm', 'Right arm')}</title></rect>
          <rect x="85" y="42" width="17" height="72" rx="8" fill={fill('lArm')} stroke="#fff" strokeWidth="2"><title>{tip('lArm', 'Left arm')}</title></rect>
          <rect x="40" y="122" width="18" height="98" rx="8" fill={fill('rLeg')} stroke="#fff" strokeWidth="2"><title>{tip('rLeg', 'Right leg')}</title></rect>
          <rect x="62" y="122" width="18" height="98" rx="8" fill={fill('lLeg')} stroke="#fff" strokeWidth="2"><title>{tip('lLeg', 'Left leg')}</title></rect>
        </svg>
        <div className="min-w-0 flex-1 space-y-2">
          {hit.length === 0 ? <p className="text-sm text-slate-500">No body area recorded yet.</p>
            : hit.map(([z, l]) => { const w = worst(l); return (
              <div key={z} className="flex items-center gap-2 text-sm">
                <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: w ? RISK_FILL[w] : '#e2e8f0' }} />
                <span className="flex-1 font-medium text-slate-700">{LABEL[z]}</span>
                <span className="text-slate-500">{l.length}×</span>
              </div>) })}
          <div className="flex flex-wrap gap-3 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
            {(['HIGH', 'MEDIUM', 'LOW'] as RiskLevel[]).map((r) => <span key={r} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: RISK_FILL[r] }} />{r[0] + r.slice(1).toLowerCase()}</span>)}
          </div>
        </div>
      </div>
    </Card>
  )
}

function RecoveryRing({ from }: { from?: InjuryEvent }) {
  const total = restDays(from?.aiInjury?.rest)
  const start = from ? new Date(from.timestamp) : null
  const day = start ? Math.max(1, Math.floor((Date.now() - +start) / 86400000) + 1) : 0
  const pct = total ? Math.min(1, day / total) : 0
  const done = !!total && day > total
  const R = 42, C = 2 * Math.PI * R
  return (
    <Card className="h-full">
      <h2 className="flex items-center gap-2 font-semibold"><Timer size={18} className="text-amber-600" />Recovery</h2>
      {!from || !total ? <p className="mt-3 text-sm text-slate-500">No rest period right now.</p> : (
        <div className="mt-3 flex items-center gap-5">
          <svg viewBox="0 0 100 100" className="h-28 w-28 shrink-0 -rotate-90">
            <circle cx="50" cy="50" r={R} fill="none" stroke="#f1f5f9" strokeWidth="10" />
            <circle cx="50" cy="50" r={R} fill="none" stroke={done ? '#22c55e' : '#f59e0b'} strokeWidth="10" strokeLinecap="round" strokeDasharray={C} strokeDashoffset={C * (1 - pct)} />
            <text x="50" y="50" transform="rotate(90 50 50)" textAnchor="middle" dominantBaseline="central" fontSize="18" fontWeight="700" fill="#0f172a">{Math.round(pct * 100)}%</text>
          </svg>
          <div className="min-w-0">
            <p className="text-2xl font-bold text-navy-900">{done ? 'Rest done' : `Day ${day}`}<span className="text-base font-medium text-slate-500">{done ? '' : ` of ~${total}`}</span></p>
            <p className="text-sm text-slate-500">Expected rest {from.aiInjury?.rest} · since {new Date(from.timestamp).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</p>
            <p className="mt-1 text-xs text-slate-500">{done ? 'Get cleared by medical staff before playing.' : `About ${total - day} day(s) left. Medical staff decide when you return.`}</p>
          </div>
        </div>
      )}
    </Card>
  )
}

function BandCard({ open }: { open: InjuryEvent[] }) {
  const b = bandColour(open)
  return (
    <Card className="h-full">
      <h2 className="flex items-center gap-2 font-semibold"><Watch size={18} className="text-sky-600" />Your wristband</h2>
      <div className="mt-3 flex items-center gap-4">
        <div className="relative grid h-24 w-14 shrink-0 place-items-center rounded-2xl bg-slate-800 shadow-inner">
          <span className={`h-8 w-8 rounded-full ${b.blink ? 'animate-pulse' : ''}`} style={{ background: b.hex, boxShadow: `0 0 18px 4px ${b.hex}99` }} />
        </div>
        <div className="min-w-0">
          <p className="text-2xl font-bold" style={{ color: b.hex }}>{b.name}{b.blink ? ' (blinking)' : ''}</p>
          <p className="text-sm text-slate-500">{b.text}</p>
          <p className="mt-1 text-xs text-slate-400">Worked out from your open injury events, with the same rules the band uses.</p>
        </div>
      </div>
    </Card>
  )
}

/* ---------- Dashboard ---------- */
export function PlayerDashboard() {
  const { user } = useAuth()
  const me = useMe()
  const ev = useEvents()
  const h = useInjuryHistory()
  const dev = !!user?.dev

  const all = uniqueFalls(ev.data ?? [])
  const current = all.filter((e) => !e.resolved)
  const restFrom = current.find((e) => e.aiInjury?.rest) ?? all.find((e) => e.aiInjury?.rest)
  const name = me.data?.playerName ?? user?.name ?? 'Player'

  const KPI: [string, number | string | null, string?][] = [
    ['Current injury events', ev.data ? current.length : null, current.length ? 'text-red-700' : ''],
    ['Expected rest', ev.data ? restFrom?.aiInjury?.rest ?? '—' : null, 'text-amber-600'],
    ['Previous injuries', h.data ? h.data.length : null],
    ['High-risk falls', ev.data ? all.filter((e) => e.risk === 'HIGH').length : null, 'text-red-700'],
  ]

  return (
    <>
      <PageHeader back={false} title="Player dashboard" crumbs={[{ label: 'Dashboard' }]} actions={<Link to="/player/reports" className={btnS}><FileText size={16} />My report</Link>} />
      {ev.data && <StatusBanner open={current} rest={current.find((e) => e.aiInjury?.rest)?.aiInjury?.rest ?? null} />}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {KPI.map(([k, v, t]) => <Card key={k}><p className="text-xs text-slate-500">{k}</p>{ev.isLoading ? <Skeleton className="mt-2 h-8 w-12" /> : <p className={`mt-1 truncate font-bold ${typeof v === 'string' ? 'text-2xl' : 'text-3xl'} ${t ?? ''}`} title={typeof v === 'string' ? v : undefined}><Na v={v} /></p>}</Card>)}
      </div>
      <p className="mt-2 text-xs text-slate-500">{dev ? 'Metrics are shown only when real backend data is available.' : `Welcome, ${name}. You see only your own injury data.`}</p>

      {ev.data && (
        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          <BodyMap list={all} />
          <RecoveryRing from={current.find((e) => e.aiInjury?.rest)} />
          <BandCard open={current} />
        </div>
      )}

      <div className="mt-4">
        <Card>
          <div className="flex items-center justify-between"><h2 className="font-semibold">Current injury events</h2>{all.length > 0 && <Link to="/player/events" className={btnSm}>View all</Link>}</div>
          {ev.isError ? <ErrorState title="Unable to load your injury events" text={normalizeApiError(ev.error)} onRetry={() => ev.refetch()} />
            : ev.isLoading ? <div className="mt-3 space-y-2"><Skeleton /><Skeleton /></div>
            : current.length === 0 ? <EmptyState title="No current injury events" text="Falls detected in a match video that are not reviewed yet appear here." />
            : <ul className="mt-2 divide-y divide-slate-100">{current.slice(0, 6).map((e) => <EventLine key={e.id} e={e} />)}</ul>}
        </Card>
      </div>

      <div className="mt-4">
        <Card>
          {me.data?.playerId ? <PreviousInjuries playerId={me.data.playerId} name={name} />
            : <><h2 className="flex items-center gap-2 font-semibold"><HeartPulse size={18} className="text-rose-600" />Previous injury history</h2><p className="mt-2 text-sm text-slate-500">{dev ? 'Log in with a player account to see your injury history.' : me.isLoading ? 'Loading…' : 'This login is not linked to a player yet. Ask your administrator.'}</p></>}
          <div className="mt-3"><Link to="/player/history" className={btnSm}>Open full history</Link></div>
        </Card>
      </div>
    </>
  )
}

/* ---------- Profile ---------- */
export function PlayerProfile() {
  const { user } = useAuth()
  const me = useMe()
  const ev = useEvents()
  const h = useInjuryHistory()
  if (!user) return null

  const d = me.data
  const name = d?.playerName ?? user.name
  const events = uniqueFalls(ev.data ?? [])

  const Info = ({ label, value }: { label: string; value: ReactNode }) => (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 py-3.5 last:border-0">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="flex items-center gap-2 text-right text-sm font-semibold text-slate-800">{value}<Lock size={13} className="shrink-0 text-slate-300" aria-label="Set by the administrator" /></dd>
    </div>
  )
  const Stat = ({ label, value, tone = '' }: { label: string; value: ReactNode; tone?: string }) => (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><p className="text-xs text-slate-500">{label}</p><p className={`mt-1 text-2xl font-bold ${tone}`}>{value}</p></div>
  )

  return (
    <>
      <PageHeader title="Profile" crumbs={[{ label: 'Profile' }]} />

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="h-28 bg-gradient-to-r from-[#0b1f3a] via-[#16325c] to-sky-600" />
        <div className="flex flex-wrap items-end gap-5 px-6 pb-6">
          <span className="-mt-12 grid h-24 w-24 shrink-0 place-items-center rounded-2xl border-4 border-white bg-sky-500 text-3xl font-bold text-white shadow-md">{d?.jersey !== null && d?.jersey !== undefined ? `#${d.jersey}` : (name[0] || '?').toUpperCase()}</span>
          <div className="min-w-0 flex-1 pt-3">
            <h2 className="truncate text-2xl font-bold">{name}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
              <Badge tone="violet">Player</Badge>
              <span className="flex items-center gap-1"><Shield size={14} />{me.isLoading ? 'Loading team…' : d?.teamName ?? 'No team'}</span>
              <span className="flex items-center gap-1"><CheckCircle2 size={14} className="text-green-600" />Active account</span>
            </div>
          </div>
          <p className="flex items-center gap-1.5 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500"><Lock size={13} />Managed by the administrator</p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <h2 className="font-semibold">Player details</h2>
          <p className="text-xs text-slate-500">These details are set by the administrator and cannot be changed here.</p>
          {me.isError && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{normalizeApiError(me.error)}</p>}
          <dl className="mt-2">
            <Info label="Player" value={d?.playerName ?? '—'} />
            <Info label="Jersey number" value={d?.jersey !== null && d?.jersey !== undefined ? `#${d.jersey}` : '—'} />
            <Info label="Team" value={d?.teamName ?? '—'} />
            <Info label="Coach" value={d?.coaches.length ? d.coaches.join(', ') : '—'} />
            <Info label="Username" value={d?.username ?? user.name} />
            <Info label="Account status" value={<span className="text-green-700">Active</span>} />
          </dl>
        </Card>

        <Card>
          <h2 className="font-semibold">What you can do</h2>
          <p className="text-xs text-slate-500">Access given to player logins.</p>
          <ul className="mt-3 space-y-2.5">
            {ROLE_ACCESS.PLAYER.map((t) => <li key={t} className="flex items-start gap-2 text-sm text-slate-700"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-green-600" />{t}</li>)}
          </ul>
          <p className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-500">Something wrong in your details or need a new password? Contact your administrator.</p>
        </Card>
      </div>

      <Card className="mt-4">
        <h2 className="font-semibold">Your injuries at a glance</h2>
        <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Stat label="Detected falls" value={ev.isLoading ? '…' : events.length} />
          <Stat label="Current injury events" value={ev.isLoading ? '…' : events.filter((e) => !e.resolved).length} tone="text-red-700" />
          <Stat label="Reviewed by medical staff" value={ev.isLoading ? '…' : events.filter((e) => e.resolved).length} tone="text-green-700" />
          <Stat label="Previous injuries" value={h.isLoading ? '…' : (h.data ?? []).length} tone="text-amber-600" />
        </div>
      </Card>
    </>
  )
}

/* ---------- History: previous injuries + falls already reviewed ---------- */
export function PlayerHistoryPage() {
  const { user } = useAuth()
  const me = useMe()
  const ev = useEvents()
  const past = uniqueFalls(ev.data ?? []).filter((e) => e.resolved)
  const name = me.data?.playerName ?? user?.name ?? 'Player'

  return (
    <>
      <PageHeader title="Injury history" crumbs={[{ label: 'History' }]} />
      <Card>
        {me.data?.playerId ? <PreviousInjuries playerId={me.data.playerId} name={name} />
          : <p className="text-sm text-slate-500">{user?.dev ? 'Log in with a player account to see your injury history.' : me.isLoading ? 'Loading…' : 'This login is not linked to a player yet. Ask your administrator.'}</p>}
      </Card>
      <h2 className="mb-3 mt-6 flex items-center gap-2 font-semibold"><CalendarDays size={18} className="text-sky-600" />Past detected falls <span className="text-sm font-normal text-slate-500">· reviewed by medical staff</span></h2>
      <FallList list={past} loading={ev.isLoading} error={ev.isError ? ev.error : null} retry={() => ev.refetch()} emptyTitle="No past falls" emptyText="Falls appear here once medical staff have reviewed them." />
    </>
  )
}

/* ---------- Events: current (not yet reviewed) injury events ---------- */
export function PlayerEvents() {
  const ev = useEvents()
  const current = uniqueFalls(ev.data ?? []).filter((e) => !e.resolved)
  return (
    <>
      <PageHeader title="My injury events" crumbs={[{ label: 'Events' }]} />
      <p className="mb-3 text-sm text-slate-500">Falls detected in match videos that are still waiting for, or under, medical review. Reviewed falls move to History.</p>
      <FallList list={current} loading={ev.isLoading} error={ev.isError ? ev.error : null} retry={() => ev.refetch()} emptyTitle="No current injury events" emptyText="You have no falls waiting for medical review." />
    </>
  )
}

/* ---------- Reports: the same report page, filled with this player's events only ---------- */
export function PlayerReports() {
  return <ReportsPage />
}