import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Inbox, AlertTriangle, X, CheckCircle2, ShieldAlert, UserX, UserCheck, HelpCircle, type LucideIcon } from 'lucide-react'
import type { IdentityStatus, RiskLevel } from './types'
import { SAFETY_DISCLAIMER, safetyMeasures } from './safety'

export const DISCLAIMER_1 = 'Body area, risk and injury notes are AI estimates, NOT a confirmed diagnosis.'
export const DISCLAIMER_2 = 'This system is intended for screening and decision support only. Final clinical assessment must be performed by a qualified medical professional.'

export const btn = 'inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed'
export const btnP = `${btn} bg-brand-600 text-white shadow-sm shadow-brand-600/30 hover:bg-brand-700`
export const btnS = `${btn} border border-slate-200 bg-white text-slate-700 hover:border-brand-600/40 hover:bg-brand-50 hover:text-brand-700`
export const btnD = `${btn} bg-red-600 text-white hover:bg-red-700`
export const inp = 'w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-brand-600 focus:ring-2 focus:ring-brand-600/15'
/** Same as inp but without w-full (for filter bars) */
export const inpAuto = 'rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition focus:border-brand-600 focus:ring-2 focus:ring-brand-600/15'

export const Card = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <div className={`rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(10,26,53,.04),0_8px_24px_-12px_rgba(10,26,53,.12)] ${className}`}>{children}</div>
)

const tones = {
  green: 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20',
  amber: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20',
  red: 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20',
  blue: 'bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-600/20',
  violet: 'bg-violet-50 text-violet-700 ring-1 ring-inset ring-violet-600/20',
  orange: 'bg-orange-50 text-orange-700 ring-1 ring-inset ring-orange-600/20',
  gray: 'bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-500/15',
}
export type Tone = keyof typeof tones

export const Badge = ({ tone = 'gray', children, title }: { tone?: Tone; children: ReactNode; title?: string }) => (
  <span title={title} className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${tones[tone]}`}>
    {children}
  </span>
)

export const RiskBadge = ({ level }: { level: RiskLevel | null }) =>
  level ? (
    <Badge tone={level === 'HIGH' ? 'red' : level === 'MEDIUM' ? 'amber' : 'green'}>
      {level === 'HIGH' && <ShieldAlert size={12} />}
      {level.charAt(0) + level.slice(1).toLowerCase()}
    </Badge>
  ) : (
    <Badge>Unrated</Badge>
  )

/** Confirmed / Uncertain / Unknown. `label` replaces the default text, e.g. "Jersey number · 94%". */
export const IdentityBadge = ({ s, label, title }: { s: IdentityStatus; label?: string | null; title?: string }) =>
  s === 'CONFIRMED' ? (
    <Badge tone="green" title={title}><UserCheck size={12} />{label || 'Confirmed'}</Badge>
  ) : s === 'UNCERTAIN' ? (
    <Badge tone="amber" title={title}><HelpCircle size={12} />{label || 'Uncertain'}</Badge>
  ) : (
    <Badge tone="orange" title={title}><UserX size={12} />Unidentified</Badge>
  )

export const EmptyState = ({ title, text, action }: { title: string; text?: string; action?: ReactNode }) => (
  <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
    <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-50 text-brand-600"><Inbox size={24} /></span>
    <p className="font-semibold">{title}</p>
    {text && <p className="max-w-md text-sm text-slate-500">{text}</p>}
    {action}
  </div>
)

export const ErrorState = ({ title, text, onRetry }: { title: string; text?: string; onRetry?: () => void }) => (
  <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
    <span className="grid h-12 w-12 place-items-center rounded-2xl bg-red-50 text-red-600"><AlertTriangle size={24} /></span>
    <p className="font-semibold">{title}</p>
    {text && <p className="text-sm text-slate-500">{text}</p>}
    {onRetry && <button className={btnS} onClick={onRetry}>Try again</button>}
  </div>
)

export const Skeleton = ({ className = 'h-4 w-full' }: { className?: string }) => (
  <div className={`animate-pulse rounded-lg bg-slate-200/70 ${className}`} />
)

export const Disclaimer = () => (
  <div role="note" className="rounded-xl border border-brand-100 bg-brand-50 p-3 text-sm text-navy-800">
    <p className="font-semibold">{DISCLAIMER_1}</p>
    <p className="mt-1">{DISCLAIMER_2}</p>
  </div>
)

export const Na = ({ v }: { v?: string | number | null }) => <>{v === null || v === undefined || v === '' ? '—' : v}</>

export const Field = ({ label, err, children }: { label: string; err?: string; children: ReactNode }) => (
  <label className="block text-sm">
    <span className="mb-1.5 block font-medium text-slate-700">{label}</span>
    {children}
    {err && <span role="alert" className="mt-1 block text-xs text-red-600">{err}</span>}
  </label>
)

const SAFETY_TONE: Record<RiskLevel, { box: string; head: string }> = {
  HIGH: { box: 'border-red-200 bg-red-50', head: 'text-red-800' },
  MEDIUM: { box: 'border-amber-200 bg-amber-50', head: 'text-amber-800' },
  LOW: { box: 'border-green-200 bg-green-50', head: 'text-green-800' },
}

/** Recommended first-aid / referral steps for one event (same text as the WhatsApp alert). */
export function SafetyMeasures({ eventType, region, risk }: { eventType: string; region: string | null; risk: RiskLevel | null }) {
  const steps = safetyMeasures(eventType, region, risk)
  if (!steps.length) return null
  const t = SAFETY_TONE[risk ?? 'LOW']
  return (
    <div className={`rounded-xl border p-3 text-sm text-slate-800 ${t.box}`}>
      <p className={`text-xs font-semibold uppercase tracking-wide ${t.head}`}>Recommended safety measures</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5">
        {steps.map((s) => <li key={s}>{s}</li>)}
      </ul>
      <p className="mt-1 text-xs text-slate-500">{SAFETY_DISCLAIMER}</p>
    </div>
  )
}

export function PageHeader({ title, crumbs = [], actions, back = true }: { title: string; crumbs?: { label: string; to?: string }[]; actions?: ReactNode; back?: boolean }) {
  const nav = useNavigate()
  return (
    <div className="mb-6">
      <nav aria-label="Breadcrumb" className="mb-1.5 flex flex-wrap items-center gap-1 text-xs font-medium text-slate-400">
        <Link to="/" className="hover:text-brand-600">Home</Link>
        {crumbs.map((c) => (
          <span key={c.label} className="flex gap-1">
            / {c.to ? <Link to={c.to} className="hover:text-brand-600">{c.label}</Link> : <span aria-current="page" className="text-slate-500">{c.label}</span>}
          </span>
        ))}
      </nav>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {back && <button aria-label="Back" className={btnS + ' !px-2.5'} onClick={() => nav(-1)}><ArrowLeft size={16} /></button>}
          <h1 className="text-2xl font-bold tracking-tight text-navy-900">{title}</h1>
        </div>
        <div className="flex flex-wrap gap-2">{actions}</div>
      </div>
    </div>
  )
}

export function Modal({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy-950/60 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-2xl bg-white p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-navy-900">{title}</h2>
          <button aria-label="Close" className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" onClick={onClose}><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function Confirm({ open, title, text, confirmLabel, onConfirm, onClose }: { open: boolean; title: string; text: string; confirmLabel: string; onConfirm: () => void; onClose: () => void }) {
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <p className="text-sm text-slate-600">{text}</p>
      <div className="mt-5 flex justify-end gap-2">
        <button className={btnS} onClick={onClose}>Cancel</button>
        <button className={btnD} onClick={() => { onConfirm(); onClose() }}>{confirmLabel}</button>
      </div>
    </Modal>
  )
}

type T = { id: number; msg: string; err?: boolean }
const TC = createContext<(m: string, err?: boolean) => void>(() => {})
export const useToast = () => useContext(TC)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [ts, setTs] = useState<T[]>([])
  const push = useCallback((msg: string, err?: boolean) => {
    const id = Date.now() + Math.random()
    setTs((t) => [...t, { id, msg, err }])
    setTimeout(() => setTs((t) => t.filter((x) => x.id !== id)), 4000)
  }, [])
  return (
    <TC.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] space-y-2" aria-live="polite">
        {ts.map((t) => (
          <div key={t.id} className={`flex items-center gap-2 rounded-xl px-4 py-3 text-sm text-white shadow-lg ${t.err ? 'bg-red-600' : 'bg-navy-900'}`}>
            {!t.err && <CheckCircle2 size={16} className="text-sky-300" />}
            {t.msg}
          </div>
        ))}
      </div>
    </TC.Provider>
  )
}

/* =====================================================================
   NEW BUILDING BLOCKS (logo, KPI card, charts)
   ===================================================================== */

/** AthleteGuard mark: a shield with a pulse line. */
export function LogoMark({ size = 36 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <defs>
        <linearGradient id="ag-shield" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5aa9ff" />
          <stop offset="1" stopColor="#1463ff" />
        </linearGradient>
      </defs>
      <path d="M24 3 6 9.5v12.2C6 33.6 13.7 41.9 24 45c10.3-3.1 18-11.4 18-23.3V9.5L24 3Z" fill="url(#ag-shield)" />
      <path d="M24 7.4 10 12.5v9.3c0 9.6 6 16.6 14 19.3 8-2.7 14-9.7 14-19.3v-9.3L24 7.4Z" fill="none" stroke="#fff" strokeOpacity=".35" strokeWidth="1.5" />
      <path d="M12 25h6l3-7 5 13 3-6h7" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** Logo + ATHLETEGUARD wordmark. `dark` = on a navy background. */
export function Logo({ dark = true, tagline = true, size = 36 }: { dark?: boolean; tagline?: boolean; size?: number }) {
  return (
    <span className="flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="leading-none">
        <span className={`block whitespace-nowrap font-display text-[1.3em] font-bold tracking-wide ${dark ? 'text-white' : 'text-navy-900'}`}>ATHLETE<span className="text-brand-500">GUARD</span></span>
        {tagline && <span className={`mt-0.5 block whitespace-nowrap text-[9.5px] font-medium ${dark ? 'text-slate-400' : 'text-slate-500'}`}>Prevent Injuries. Keep Athletes Stronger.</span>}
      </span>
    </span>
  )
}

const TILE = {
  blue: 'bg-brand-50 text-brand-600',
  green: 'bg-emerald-50 text-emerald-600',
  red: 'bg-red-50 text-red-600',
  amber: 'bg-amber-50 text-amber-600',
  violet: 'bg-violet-50 text-violet-600',
  sky: 'bg-sky-50 text-sky-600',
}
export type TileTone = keyof typeof TILE

export const IconTile = ({ icon: I, tone = 'blue', size = 'md' }: { icon: LucideIcon; tone?: TileTone; size?: 'sm' | 'md' }) => (
  <span className={`grid shrink-0 place-items-center rounded-xl ${TILE[tone]} ${size === 'sm' ? 'h-9 w-9' : 'h-12 w-12'}`}><I size={size === 'sm' ? 18 : 22} /></span>
)

/** Dashboard KPI card: icon tile, label, big value, optional note. */
export function KpiCard({ label, value, icon, tone = 'blue', valueClass = '', note, loading }: { label: string; value: ReactNode; icon: LucideIcon; tone?: TileTone; valueClass?: string; note?: ReactNode; loading?: boolean }) {
  const long = typeof value === 'string' && value.length > 6
  return (
    <Card className="!p-4">
      <div className="flex items-center gap-3">
        <IconTile icon={icon} tone={tone} />
        <div className="min-w-0 flex-1">
          <p className="line-clamp-2 text-xs font-semibold leading-tight text-slate-500" title={label}>{label}</p>
          {loading ? <Skeleton className="mt-1.5 h-7 w-12" /> : <p className={`mt-0.5 truncate font-bold tracking-tight text-navy-900 ${long ? 'text-lg' : 'text-[28px] leading-8'} ${valueClass}`} title={typeof value === 'string' ? value : undefined}>{value}</p>}
          {note && <p className="truncate text-[11px] text-slate-400">{note}</p>}
        </div>
      </div>
    </Card>
  )
}

/** Categorical series colors (validated order) and reserved status colors. */
export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#6250d6']
export const STATUS_COLOR = { HIGH: '#dc2626', MEDIUM: '#d97706', LOW: '#16a34a' }

export type Slice = { label: string; value: number; color: string }

/** Donut with the total (or the hovered slice) in the middle and a legend with counts beside it. */
export function Donut({ data, centerLabel, size = 132 }: { data: Slice[]; centerLabel: string; size?: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const total = data.reduce((s, d) => s + d.value, 0)
  const r = 42, c = 2 * Math.PI * r, gap = total > 0 && data.filter((d) => d.value > 0).length > 1 ? 1.6 : 0
  let acc = 0
  const h = hover !== null ? data[hover] : null
  return (
    <div className="flex flex-wrap items-center gap-5">
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" role="img" aria-label={`${centerLabel}: ${data.map((d) => `${d.label} ${d.value}`).join(', ')}`}>
          <circle cx="50" cy="50" r={r} fill="none" stroke="#eef2f7" strokeWidth="11" />
          {total > 0 && data.map((d, i) => {
            if (!d.value) return null
            const len = (d.value / total) * c
            const seg = <circle key={d.label} cx="50" cy="50" r={r} fill="none" stroke={d.color} strokeWidth={hover === i ? 13 : 11}
              strokeDasharray={`${Math.max(len - gap, 0.01)} ${c}`} strokeDashoffset={-acc} className="cursor-pointer transition-[stroke-width]"
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}><title>{`${d.label}: ${d.value} (${Math.round((d.value / total) * 100)}%)`}</title></circle>
            acc += len
            return seg
          })}
        </svg>
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
          <div>
            <p className="text-2xl font-bold leading-none text-navy-900">{h ? h.value : total}</p>
            <p className="mt-1 max-w-[80px] truncate text-[10px] font-medium text-slate-500">{h ? h.label : centerLabel}</p>
          </div>
        </div>
      </div>
      <ul className="min-w-[150px] flex-1 space-y-2 text-sm">
        {data.map((d, i) => (
          <li key={d.label} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} className={`flex items-center gap-2 rounded-lg px-1.5 py-0.5 ${hover === i ? 'bg-slate-50' : ''}`}>
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: d.color }} />
            <span className="min-w-0 flex-1 truncate text-slate-600">{d.label}</span>
            <span className="font-semibold text-navy-900">{d.value}</span>
            <span className="w-10 text-right text-xs text-slate-400">{total ? Math.round((d.value / total) * 100) : 0}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Single-series line chart with a hover crosshair + tooltip. */
export function TrendLine({ points, color = '#1463ff', unit = 'events', height = 170 }: { points: { label: string; value: number }[]; color?: string; unit?: string; height?: number }) {
  const [hover, setHover] = useState<number | null>(null)
  // drawn at the real pixel width, so the text stays the same size on every screen
  const box = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(600)
  useEffect(() => {
    const el = box.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const H = height, L = 30, R = 10, T = 12, B = 24
  const max = Math.max(1, ...points.map((p) => p.value))
  const top = Math.ceil(max / 2) * 2 || 2
  const x = (i: number) => L + (points.length <= 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (points.length - 1))
  const y = (v: number) => T + (H - T - B) * (1 - v / top)
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ')
  const area = points.length ? `${path} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z` : ''
  const ticks = [0, top / 2, top]
  const every = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor(W / 70))))
  const hp = hover !== null ? points[hover] : null
  return (
    <div ref={box} className="relative">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block max-w-full" role="img" aria-label={points.map((p) => `${p.label}: ${p.value}`).join(', ')}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const b = (e.currentTarget as SVGSVGElement).getBoundingClientRect()
          const px = ((e.clientX - b.left) / b.width) * W
          let best = 0
          points.forEach((_, i) => { if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i })
          setHover(points.length ? best : null)
        }}>
        <defs><linearGradient id="ag-area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".18" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
        {ticks.map((t) => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke="#eef2f7" /><text x={L - 6} y={y(t) + 3} textAnchor="end" fontSize="11" fill="#94a3b8">{t}</text></g>)}
        {points.map((p, i) => i % every === 0 && <text key={p.label + i} x={x(i)} y={H - 6} textAnchor={i === 0 ? 'start' : i === points.length - 1 ? 'end' : 'middle'} fontSize="11" fill="#94a3b8">{p.label}</text>)}
        {area && <path d={area} fill="url(#ag-area)" />}
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={y(0)} stroke="#cbd5e1" strokeDasharray="3 3" />}
        {points.map((p, i) => p.value > 0 || hover === i ? <circle key={i} cx={x(i)} cy={y(p.value)} r={hover === i ? 4.5 : 3} fill={color} stroke="#fff" strokeWidth="2" /> : null)}
      </svg>
      {hp && hover !== null && (
        <div className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-lg bg-navy-900 px-2.5 py-1.5 text-xs text-white shadow-lg"
          style={{ left: `${(x(hover) / W) * 100}%`, top: `${(y(hp.value) / H) * 100}%`, marginTop: -8 }}>
          <span className="font-semibold">{hp.value}</span> {unit} · {hp.label}
        </div>
      )}
    </div>
  )
}

/** Horizontal bars with the value written beside each bar (e.g. events per body region). */
export function BarList({ data, color = '#1463ff' }: { data: { label: string; value: number }[]; color?: string }) {
  const max = Math.max(1, ...data.map((d) => d.value))
  return (
    <ul className="space-y-2.5">
      {data.map((d) => (
        <li key={d.label} title={`${d.label}: ${d.value}`} className="text-sm">
          <div className="mb-1 flex justify-between gap-2"><span className="truncate text-slate-600">{d.label}</span><span className="font-semibold text-navy-900">{d.value}</span></div>
          <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full" style={{ width: `${(d.value / max) * 100}%`, background: color }} /></div>
        </li>
      ))}
    </ul>
  )
}