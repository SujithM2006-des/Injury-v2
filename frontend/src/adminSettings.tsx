/* =====================================================================
   ADMIN SETTINGS
   Profile, Detection (AI thresholds used by the detector on its next run; the Gemini
   double-check is not shown here and keeps its saved value),
   Wristband (band key + how long the band keeps its colour), Data (clips + backup)
   and Security (change password). Backend: /admin/settings*, /admin/clips/cleanup,
   /admin/backup, /auth/change-password. Only the admin sees this page.
   ===================================================================== */
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, CheckCircle2, Cpu, Database, Download, Eye, EyeOff, KeyRound, RotateCcw, Save, Server, ShieldCheck, Trash2, Trophy, UserCog, UserRound, Users, Watch } from 'lucide-react'
import { api, devMode, normalizeApiError } from './api/client'
import { useAuth } from './auth'
import { Card, Confirm, EmptyState, ErrorState, Field, PageHeader, Skeleton, btnD, btnP, btnS, inp, useToast } from './ui'

type Detection = {
  fall_angle: number; fall_downward_ratio: number; lying_angle: number; lying_aspect_ratio: number
  keypoint_confidence: number; person_confidence: number; risk_medium_from: number; risk_high_from: number
  fall_cooldown_seconds: number; gemini_check: boolean; gemini_delete_min_confidence: number
}
type SettingsDto = {
  detection: Detection
  detection_defaults: Detection
  detection_limits: Record<string, [number, number]>
  band: { key: string; hold_minutes: number; custom_key: boolean }
  info: { gemini_key: boolean; gemini_injury_key: boolean; clips: { count: number; size_mb: number; oldest_days: number | null }; events: number; players: number; matches: number }
}

const TABS: [string, typeof Cpu][] = [['Profile', UserRound], ['Detection', Cpu], ['Wristband', Watch], ['Data', Database], ['Security', KeyRound]]

/** One numeric setting: label, help text, input with its allowed range and the default. */
function NumberSetting({ label, help, unit, value, def, limits, step, onChange }: { label: string; help: string; unit?: string; value: number; def: number; limits?: [number, number]; step: string; onChange: (v: number) => void }) {
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-navy-900">{label}</p>
          <p className="mt-0.5 text-xs text-slate-500">{help}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <input type="number" step={step} min={limits?.[0]} max={limits?.[1]} className={inp + ' !w-24 text-right'} value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label={label} />
          {unit && <span className="w-6 text-xs text-slate-500">{unit}</span>}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-slate-400">Default {def}{unit ? ` ${unit}` : ''}{limits ? ` · allowed ${limits[0]}–${limits[1]}` : ''}{value !== def && <span className="ml-2 font-semibold text-amber-600">changed</span>}</p>
    </div>
  )
}

const Section = ({ title, text, children }: { title: string; text?: string; children: ReactNode }) => (
  <section className="space-y-3">
    <div><h3 className="font-semibold text-navy-900">{title}</h3>{text && <p className="text-xs text-slate-500">{text}</p>}</div>
    {children}
  </section>
)

function DetectionTab({ s }: { s: SettingsDto }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [v, setV] = useState<Detection>(s.detection)
  const [busy, setBusy] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)
  const d = s.detection_defaults
  const lim = s.detection_limits
  const set = (k: keyof Detection) => (x: number) => setV({ ...v, [k]: x })
  const save = async () => {
    setBusy(true)
    try { await api.put('/admin/settings/detection', v); qc.invalidateQueries({ queryKey: ['adminSettings'] }); toast('Detection settings saved. They apply the next time the detector starts.') } catch (e) { toast(normalizeApiError(e), true) } finally { setBusy(false) }
  }
  const reset = async () => {
    try { const r = await api.post<{ detection: Detection }>('/admin/settings/detection/reset'); setV(r.data.detection); qc.invalidateQueries({ queryKey: ['adminSettings'] }); toast('Detection settings back to the defaults.') } catch (e) { toast(normalizeApiError(e), true) }
  }
  return (
    <div className="space-y-6">
      <p className="rounded-xl bg-brand-50 p-3 text-sm text-navy-800">These settings are read by the detector when it starts. Restart the detector (run the match video again) after saving.</p>
      <Section title="Fall detection" text="When the AI counts a movement as a fall.">
        <div className="grid gap-3 md:grid-cols-2">
          <NumberSetting label="Falling movement angle" help="Body tilt from upright while dropping." unit="°" step="1" value={v.fall_angle} def={d.fall_angle} limits={lim.fall_angle} onChange={set('fall_angle')} />
          <NumberSetting label="Drop size" help="How much of their height the player must drop (0.18 = 18%)." step="0.01" value={v.fall_downward_ratio} def={d.fall_downward_ratio} limits={lim.fall_downward_ratio} onChange={set('fall_downward_ratio')} />
          <NumberSetting label="Lying-down angle" help="Torso tilt that counts as lying on the ground." unit="°" step="1" value={v.lying_angle} def={d.lying_angle} limits={lim.lying_angle} onChange={set('lying_angle')} />
          <NumberSetting label="Lying-down shape" help="Body box at least this many times wider than tall." step="0.1" value={v.lying_aspect_ratio} def={d.lying_aspect_ratio} limits={lim.lying_aspect_ratio} onChange={set('lying_aspect_ratio')} />
          <NumberSetting label="Time between falls" help="The same player can trigger a new fall after this." unit="s" step="1" value={v.fall_cooldown_seconds} def={d.fall_cooldown_seconds} limits={lim.fall_cooldown_seconds} onChange={set('fall_cooldown_seconds')} />
        </div>
      </Section>
      <Section title="Risk levels" text="How hard the body moved during the fall, in % of the player's height per frame.">
        <div className="grid gap-3 md:grid-cols-2">
          <NumberSetting label="Medium risk from" help="Below this the fall is Low risk." unit="%" step="1" value={v.risk_medium_from} def={d.risk_medium_from} limits={lim.risk_medium_from} onChange={set('risk_medium_from')} />
          <NumberSetting label="High risk from" help="Must be higher than Medium." unit="%" step="1" value={v.risk_high_from} def={d.risk_high_from} limits={lim.risk_high_from} onChange={set('risk_high_from')} />
        </div>
        {(() => { const max = Math.max(1, v.risk_high_from * 1.6); const pct = (x: number) => Math.max(0, Math.min(100, (x / max) * 100)); return (
          <div className="flex h-3 overflow-hidden rounded-full" aria-hidden="true">
            <span className="bg-green-500" style={{ width: `${pct(v.risk_medium_from)}%` }} />
            <span className="bg-amber-400" style={{ width: `${Math.max(0, pct(v.risk_high_from) - pct(v.risk_medium_from))}%` }} />
            <span className="flex-1 bg-red-500" />
          </div>
        ) })()}
        <p className="text-xs text-slate-500">Low below {v.risk_medium_from}% · Medium {v.risk_medium_from}–{v.risk_high_from}% · High from {v.risk_high_from}%</p>
      </Section>
      <Section title="Pose model" text="How sure the model must be before it uses a person or a body point.">
        <div className="grid gap-3 md:grid-cols-2">
          <NumberSetting label="Person confidence" help="People detected below this are ignored." step="0.05" value={v.person_confidence} def={d.person_confidence} limits={lim.person_confidence} onChange={set('person_confidence')} />
          <NumberSetting label="Body point confidence" help="Joints (knees, ankles…) below this are ignored." step="0.05" value={v.keypoint_confidence} def={d.keypoint_confidence} limits={lim.keypoint_confidence} onChange={set('keypoint_confidence')} />
        </div>
      </Section>
      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
        <button className={btnP} disabled={busy} onClick={save}><Save size={16} />{busy ? 'Saving…' : 'Save detection settings'}</button>
        <button className={btnS} onClick={() => setResetOpen(true)}><RotateCcw size={16} />Reset to defaults</button>
      </div>
      <Confirm open={resetOpen} title="Reset detection settings?" text="All detection settings go back to the defaults the detector was built with." confirmLabel="Reset" onConfirm={() => { setResetOpen(false); reset() }} onClose={() => setResetOpen(false)} />
    </div>
  )
}

function WristbandTab({ s }: { s: SettingsDto }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [key, setKey] = useState(s.band.key)
  const [hold, setHold] = useState(s.band.hold_minutes)
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const newKey = () => setKey('ag-' + Array.from(crypto.getRandomValues(new Uint8Array(9)), (b) => b.toString(36).padStart(2, '0')).join('').slice(0, 16))
  const save = async () => {
    setBusy(true)
    try { await api.put('/admin/settings/band', { key, hold_minutes: hold }); qc.invalidateQueries({ queryKey: ['adminSettings'] }); toast('Wristband settings saved. Use the same key in the band code (BAND_KEY).') } catch (e) { toast(normalizeApiError(e), true) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-6">
      <Section title="Band key" text="Every band sends this key. A band with a different key gets no data.">
        <div className="rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <input type={show ? 'text' : 'password'} className={inp + ' max-w-sm font-mono'} value={key} onChange={(e) => setKey(e.target.value)} aria-label="Band key" />
            <button className={btnS} onClick={() => setShow(!show)} aria-label={show ? 'Hide key' : 'Show key'}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button>
            <button className={btnS} onClick={() => { newKey(); setShow(true) }}><RotateCcw size={16} />New random key</button>
          </div>
          <p className="mt-2 text-xs text-slate-500">{s.band.custom_key ? 'A custom key is in use.' : 'The default key is in use. Set your own before a real match.'} After changing it, put the same key in <code className="rounded bg-slate-100 px-1">BAND_KEY</code> in the band code and upload it again.</p>
        </div>
      </Section>
      <Section title="After the match" text="How long the band keeps its colour after the match video finishes.">
        <div className="flex items-center gap-2 rounded-xl border border-slate-200 p-4">
          <input type="number" min={0} max={180} className={inp + ' !w-24 text-right'} value={hold} onChange={(e) => setHold(Number(e.target.value))} aria-label="Minutes" />
          <span className="text-sm text-slate-600">minutes, then the band turns blue again</span>
        </div>
      </Section>
      <Section title="Colours" text="What the band shows during a match.">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {[['bg-blue-600', 'Blue', 'No falls'], ['bg-green-500', 'Green', '1–2 low falls'], ['bg-amber-400', 'Amber', '1 medium or 3+ low'], ['bg-red-600', 'Red (blinking)', 'Any high or 2+ medium']].map(([c, n, t]) => (
            <div key={n} className="flex items-center gap-3 rounded-xl border border-slate-200 p-3"><span className={`h-6 w-6 rounded-full ${c} shadow`} /><span><span className="block text-sm font-semibold">{n}</span><span className="block text-xs text-slate-500">{t}</span></span></div>
          ))}
        </div>
      </Section>
      <div className="border-t border-slate-100 pt-4"><button className={btnP} disabled={busy} onClick={save}><Save size={16} />{busy ? 'Saving…' : 'Save wristband settings'}</button></div>
    </div>
  )
}

function DataTab({ s }: { s: SettingsDto }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [days, setDays] = useState(30)
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const c = s.info.clips
  const backup = async () => {
    setBusy(true)
    try {
      const r = await api.get('/admin/backup', { responseType: 'blob' })
      const url = URL.createObjectURL(r.data as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `athleteguard-backup-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast('Backup downloaded.')
    } catch (e) { toast(normalizeApiError(e), true) } finally { setBusy(false) }
  }
  const cleanup = async () => {
    try {
      const r = await api.post<{ deleted: number; freed_mb: number }>('/admin/clips/cleanup', { older_than_days: days })
      qc.invalidateQueries({ queryKey: ['adminSettings'] }); qc.invalidateQueries({ queryKey: ['events'] })
      toast(r.data.deleted ? `Deleted ${r.data.deleted} clip(s), freed ${r.data.freed_mb} MB.` : `No clips older than ${days} days.`)
    } catch (e) { toast(normalizeApiError(e), true) }
  }
  const Stat = ({ l, v }: { l: string; v: ReactNode }) => <div className="rounded-xl border border-slate-200 p-4"><p className="text-xs text-slate-500">{l}</p><p className="mt-1 text-2xl font-bold text-navy-900">{v}</p></div>
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat l="Injury events" v={s.info.events} /><Stat l="Players" v={s.info.players} /><Stat l="Matches" v={s.info.matches} />
        <Stat l="Clips" v={c.count} /><Stat l="Clip storage" v={`${c.size_mb} MB`} />
      </div>
      <Section title="Delete old clips" text="Frees disk space. The events stay, only their video clip is removed.">
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 p-4">
          <span className="text-sm text-slate-600">Delete clips older than</span>
          <input type="number" min={1} max={3650} className={inp + ' !w-24 text-right'} value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Days" />
          <span className="text-sm text-slate-600">days</span>
          <button className={btnD + ' ml-auto'} disabled={!c.count} onClick={() => setConfirm(true)}><Trash2 size={16} />Delete old clips</button>
          {c.oldest_days !== null && <p className="w-full text-xs text-slate-500">Oldest clip: {c.oldest_days} days old.</p>}
        </div>
      </Section>
      <Section title="Backup" text="Everything in one JSON file: events, teams, players, matches, injury history, assessments and settings (no passwords, no clips).">
        <button className={btnP} disabled={busy} onClick={backup}><Download size={16} />{busy ? 'Preparing…' : 'Download backup'}</button>
      </Section>
      <Confirm open={confirm} title={`Delete clips older than ${days} days?`} text="The clip files are removed from the disk. This cannot be undone. The events themselves are kept." confirmLabel="Delete clips" onConfirm={() => { setConfirm(false); cleanup() }} onClose={() => setConfirm(false)} />
    </div>
  )
}

function SecurityTab() {
  const toast = useToast()
  const [v, setV] = useState({ current: '', next: '', again: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async () => {
    setErr('')
    if (v.next !== v.again) { setErr('The new passwords do not match.'); return }
    setBusy(true)
    try { await api.post('/auth/change-password', { current_password: v.current, new_password: v.next }); setV({ current: '', next: '', again: '' }); toast('Password changed.') } catch (e) { setErr(normalizeApiError(e)) } finally { setBusy(false) }
  }
  return (
    <div className="grid gap-6 md:grid-cols-2">
    <div className="space-y-3">
      <div><h3 className="font-semibold text-navy-900">Change password</h3><p className="text-xs text-slate-500">Enter your current password to confirm it is you.</p></div>
      <Field label="Current password"><input type="password" autoComplete="current-password" className={inp} value={v.current} onChange={(e) => setV({ ...v, current: e.target.value })} /></Field>
      <Field label="New password"><input type="password" autoComplete="new-password" className={inp} value={v.next} onChange={(e) => setV({ ...v, next: e.target.value })} /></Field>
      <Field label="Repeat new password"><input type="password" autoComplete="new-password" className={inp} value={v.again} onChange={(e) => setV({ ...v, again: e.target.value })} /></Field>
      {err && <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-800">{err}</p>}
      <button className={btnP} disabled={busy || !v.current || !v.next} onClick={save}><KeyRound size={16} />{busy ? 'Saving…' : 'Change password'}</button>
    </div>
    <div className="h-fit rounded-xl bg-slate-50 p-5 ring-1 ring-slate-200">
      <p className="flex items-center gap-2 font-semibold text-navy-900"><ShieldCheck size={16} className="text-brand-600" />Tips for a strong password</p>
      <ul className="mt-3 space-y-2.5">{['At least 8 characters long', 'Mix letters, numbers and symbols', 'Not your username or team name', 'Do not reuse a password from another site'].map((t) => <li key={t} className="flex items-start gap-2 text-sm text-slate-700"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600" />{t}</li>)}</ul>
    </div>
    </div>
  )
}

function ProfileTab({ name, s, loading, goTo }: { name: string; s?: SettingsDto; loading: boolean; goTo: (tab: string) => void }) {
  const stats: [string, number | undefined, typeof Users, string][] = [
    ['Players', s?.info.players, Users, 'bg-brand-50 text-brand-600'],
    ['Matches analysed', s?.info.matches, Trophy, 'bg-amber-50 text-amber-600'],
    ['Injury events', s?.info.events, Activity, 'bg-red-50 text-red-600'],
  ]
  const access = [
    'Create teams, register players and manage every login',
    'See every injury event, clip and medical review',
    'Tune the fall detection and the wristband',
    'Clean up clips and download full backups',
  ]
  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
        <div className="h-24 bg-gradient-to-r from-navy-950 via-navy-800 to-brand-600" />
        <div className="flex flex-wrap items-end gap-4 px-6 pb-5">
          <span className="-mt-10 grid h-20 w-20 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-sky-400 to-brand-600 text-3xl font-bold text-white shadow-lg ring-4 ring-white">{(name[0] || 'A').toUpperCase()}</span>
          <div className="min-w-0 flex-1 pt-3">
            <p className="truncate text-xl font-bold text-navy-900">{name}</p>
            <p className="flex items-center gap-1.5 text-sm text-slate-500"><ShieldCheck size={15} className="text-brand-600" />Administrator · full access</p>
          </div>
          <button className={btnS} onClick={() => goTo('Security')}><KeyRound size={16} />Change password</button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {stats.map(([l, v, I, tone]) => (
          <div key={l} className="flex items-center gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <span className={`grid h-11 w-11 place-items-center rounded-xl ${tone}`}><I size={20} /></span>
            <div><p className="text-xs text-slate-500">{l}</p>{loading || v === undefined ? <Skeleton className="mt-1 h-6 w-12" /> : <p className="text-2xl font-bold text-navy-900">{v}</p>}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
          <h3 className="font-semibold text-navy-900">What you can do</h3>
          <ul className="mt-3 space-y-2.5">{access.map((a) => <li key={a} className="flex items-start gap-2 text-sm text-slate-700"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600" />{a}</li>)}</ul>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
          <h3 className="font-semibold text-navy-900">Quick actions</h3>
          <div className="mt-3 grid gap-2">
            <Link to="/admin/users" className={btnS + ' !justify-start'}><UserCog size={16} />Manage users and logins</Link>
            <Link to="/admin/system" className={btnS + ' !justify-start'}><Server size={16} />System status</Link>
            <button className={btnS + ' !justify-start'} onClick={() => goTo('Detection')}><Cpu size={16} />Detection settings</button>
            <button className={btnS + ' !justify-start'} onClick={() => goTo('Data')}><Database size={16} />Clips and backup</button>
          </div>
        </div>
      </div>
    </div>
  )
}

export function AdminSettingsPage() {
  const { user } = useAuth()
  const [tab, setTab] = useState('Profile')
  const q = useQuery({ queryKey: ['adminSettings'], queryFn: async () => (await api.get<SettingsDto>('/admin/settings')).data, enabled: !devMode.get() })
  const needsData = tab === 'Detection' || tab === 'Wristband' || tab === 'Data'
  return (
    <>
      <PageHeader title="Settings" crumbs={[{ label: 'Settings' }]} />
      <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b">
        {TABS.map(([t, I]) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)} className={`flex shrink-0 items-center gap-2 px-4 py-2 text-sm ${tab === t ? 'border-b-2 border-brand-600 font-semibold text-navy-900' : 'text-slate-500 hover:text-navy-900'}`}><I size={16} />{t}</button>
        ))}
      </div>
      {tab === 'Profile' && <ProfileTab name={user?.name ?? 'admin'} s={q.data} loading={q.isLoading} goTo={setTab} />}
      {tab !== 'Profile' && <Card>
        {needsData && (devMode.get() ? <EmptyState title="Log in to change settings" text="The developer preview has no backend." />
          : q.isLoading ? <div className="space-y-2"><Skeleton /><Skeleton /><Skeleton /></div>
          : q.isError || !q.data ? <ErrorState title="Unable to load settings" text={normalizeApiError(q.error)} onRetry={() => q.refetch()} />
          : tab === 'Detection' ? <DetectionTab key={JSON.stringify(q.data.detection)} s={q.data} />
          : tab === 'Wristband' ? <WristbandTab key={q.data.band.key} s={q.data} />
          : <DataTab s={q.data} />)}
        {tab === 'Security' && <SecurityTab />}
      </Card>}
    </>
  )
}