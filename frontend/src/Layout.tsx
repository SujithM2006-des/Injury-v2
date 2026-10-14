import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Users, Shield, CalendarDays, Activity, Zap, Bell, FileText, UserCog, Server, Settings, Menu, PanelLeft, Search, LogOut, HelpCircle, ChevronDown, UserRound, History, Info, X, type LucideIcon } from 'lucide-react'
import { useAuth, home } from './auth'
import type { InjuryEvent, Role } from './types'
import { useQueryClient } from '@tanstack/react-query'
import { useAlertReads, useEvents } from './queries'
import { markAlertsRead } from './api/services'
import { Badge, RiskBadge } from './ui'
import { fmtVideo, identText } from './pages'

/* ---------- identification updates ----------
 * A fall saved as "Unidentified" and named a few seconds later (jersey, face, Gemini or staff)
 * is an update. WhatsApp sends "Update: the earlier Unidentified fall was ...";
 * the web shows the same as a pop-up and in the bell. */
const LATE_ID_MS = 5000
const idKey = (e: InjuryEvent) => `${e.id}:${e.identifiedAt}`
export const identifiedLater = (e: InjuryEvent) =>
  !!e.identified && !!e.identifiedAt && +new Date(e.identifiedAt) - +new Date(e.timestamp) > LATE_ID_MS
const who = (e: InjuryEvent) => `${e.player.name ?? 'Unknown'}${e.player.jersey !== null ? ` (#${e.player.jersey})` : ''}`
const timeOnly = (v: string | null) => (v ? new Date(v).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : '')

function UpdateText({ e }: { e: InjuryEvent }) {
  const v = fmtVideo(e.videoTimeSec)
  return (
    <>
      <p className="font-medium">The earlier Unidentified {e.eventType.toLowerCase()} was {who(e)}</p>
      <p className="text-xs text-slate-500">Identified by: {identText(e) ?? '—'}{e.identifiedAt ? ` · ${timeOnly(e.identifiedAt)}` : ''}</p>
      <p className="truncate text-xs text-slate-500">{e.matchName ?? 'No match'}{v ? ` · ${v} in video` : ''}</p>
    </>
  )
}

type N = { label: string; to: string; icon: LucideIcon }
const common = (): N[] => [
  { label: 'Players', to: '/players', icon: Users },
  { label: 'Matches', to: '/matches', icon: CalendarDays },
  { label: 'Events', to: '/events', icon: Activity },
  { label: 'Collisions', to: '/collisions', icon: Zap },
  { label: 'Alerts', to: '/alerts', icon: Bell },
]
export const navFor = (r: Role): N[] => {
  const dash: N = { label: 'Dashboard', to: home[r], icon: LayoutDashboard }
  const set: N = { label: 'Settings', to: '/settings', icon: Settings }
  const rep: N = { label: 'Reports', to: '/reports', icon: FileText }
  // Admin menu: no Players, Matches or Collisions. Players live inside "Teams & Players";
  // the other pages still open from links inside events.
  const adminCommon = common().filter((i) => i.to !== '/players' && i.to !== '/matches' && i.to !== '/collisions')
  // Player: only their own pages
  if (r === 'PLAYER') return [dash, { label: 'Profile', to: '/player/profile', icon: UserRound }, { label: 'History', to: '/player/history', icon: History }, { label: 'Events', to: '/player/events', icon: Activity }, { label: 'Reports', to: '/player/reports', icon: FileText }]
  if (r === 'ADMIN') return [dash, { label: 'Teams & Players', to: '/teams', icon: Shield }, ...adminCommon, rep, { label: 'Users', to: '/admin/users', icon: UserCog }, { label: 'System', to: '/admin/system', icon: Server }, set]
  // Medical staff and coaches: same short menu as admin (Players, Matches and Collisions are reached from
  // inside "Team & Players" and the events), plus Reports.
  return [dash, { label: r === 'COACH' ? 'Team & Players' : 'Teams & Players', to: '/teams', icon: Shield }, ...adminCommon, rep, set]
}

export default function Layout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const [bell, setBell] = useState(false)
  const [menu, setMenu] = useState(false)
  const [q, setQ] = useState('')
  const events = useEvents()
  // Medical staff and coaches: the bell shows their unread alerts (every risk level).
  // Admin: unchanged, every high-risk event.
  const staff = !!user && user.role !== 'ADMIN' && !user.dev
  const reads = useAlertReads(staff)
  const qc = useQueryClient()

  // identification updates, newest first
  const updates = (events.data ?? []).filter(identifiedLater)
    .sort((a, b) => +new Date(b.identifiedAt!) - +new Date(a.identifiedAt!))
  // pop-ups only for updates that arrive while the page is open (not for old ones on first load)
  const seen = useRef<Set<string> | null>(null)
  const [popups, setPopups] = useState<InjuryEvent[]>([])
  useEffect(() => {
    if (!events.data) return
    const later = events.data.filter(identifiedLater)
    if (seen.current === null) { seen.current = new Set(later.map(idKey)); return }
    const fresh = later.filter((e) => !seen.current!.has(idKey(e)))
    if (!fresh.length) return
    fresh.forEach((e) => seen.current!.add(idKey(e)))
    setPopups((p) => [...fresh, ...p].slice(0, 3))
    fresh.forEach((e) => setTimeout(() => setPopups((p) => p.filter((x) => idKey(x) !== idKey(e))), 15000))
  }, [events.data])
  const closePopup = (e: InjuryEvent) => setPopups((p) => p.filter((x) => idKey(x) !== idKey(e)))

  if (!user) return <Navigate to="/login" replace />

  const items = navFor(user.role)
  const RISKS = ['HIGH', 'MEDIUM', 'LOW']
  const readIds = new Set(reads.data ?? [])
  const high = staff
    ? (events.data ?? []).filter((e) => !readIds.has(e.id))
      .sort((a, b) => RISKS.indexOf(a.risk ?? 'LOW') - RISKS.indexOf(b.risk ?? 'LOW') || +new Date(b.timestamp) - +new Date(a.timestamp))
    : (events.data ?? []).filter((e) => e.risk === 'HIGH')
  const markRead = (ids: number[]) => {
    if (!staff || !ids.length) return
    qc.setQueryData(['alertReads'], [...readIds, ...ids])
    markAlertsRead(ids).then((all) => qc.setQueryData(['alertReads'], all)).catch(() => qc.invalidateQueries({ queryKey: ['alertReads'] }))
  }
  const search = (e: FormEvent) => { e.preventDefault(); nav(`/events?q=${encodeURIComponent(q)}`) }

  const ROLE_NAME: Record<Role, string> = { ADMIN: 'Administrator', MEDICAL: 'Medical staff', COACH: 'Coach', PLAYER: 'Player' }
  const player = user.role === 'PLAYER'
  const side = (mobile: boolean) => {
    const wide = mobile || !collapsed
    const link = (isActive: boolean) => `group relative flex items-center gap-3 rounded-xl ${wide ? 'px-4' : 'justify-center px-0'} py-3 text-[15px] font-medium transition ${isActive ? 'bg-sky-500/20 text-white' : 'text-slate-300 hover:bg-white/10 hover:text-white'}`
    return (
      <nav aria-label="Main" className="flex h-full flex-col bg-[#0b1f3a] text-slate-200">
        <div className={`flex h-16 shrink-0 items-center gap-2 border-b border-white/10 text-white ${wide ? 'px-5' : 'justify-center'}`}><Shield className="shrink-0 text-sky-400" size={26} />{wide && <div><p className="font-bold leading-tight">AthleteGuard</p><p className="text-[10px] text-slate-400">Injury Detection</p></div>}</div>
        {wide && <p className="px-6 pb-2 pt-6 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Menu</p>}
        <ul className={`flex-1 space-y-2 overflow-y-auto px-3 ${wide ? 'pb-4' : 'py-6'}`}>
          {items.map((i) => (
            <li key={i.to}>
              <NavLink to={i.to} onClick={() => setDrawer(false)} title={i.label} className={({ isActive }) => link(isActive)}>
                {({ isActive }) => <>
                  {isActive && <span className="absolute inset-y-2 left-0 w-1 rounded-r bg-sky-400" />}
                  <i.icon size={20} className="shrink-0" />{wide && i.label}
                </>}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="shrink-0 space-y-2 border-t border-white/10 px-3 py-4">
          {wide && (
            <div className="flex items-center gap-3 rounded-xl bg-white/5 px-3 py-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-sky-500 text-sm font-bold text-white">{(user.name[0] || '?').toUpperCase()}</span>
              <div className="min-w-0"><p className="truncate text-sm font-semibold text-white">{user.name}</p><p className="truncate text-xs text-slate-400">{ROLE_NAME[user.role]}</p></div>
            </div>
          )}
          <NavLink to="/help" onClick={() => setDrawer(false)} title="Help" className={({ isActive }) => link(isActive)}><HelpCircle size={20} className="shrink-0" />{wide && 'Help'}</NavLink>
          <button title="Log out" onClick={() => { logout(); nav('/login', { replace: true }) }} className={link(false) + ' w-full hover:!bg-red-500/15 hover:!text-red-200'}><LogOut size={20} className="shrink-0" />{wide && 'Log out'}</button>
        </div>
      </nav>
    )
  }

  return (
    <div className="flex min-h-screen">
      <aside className={`hidden shrink-0 bg-[#0b1f3a] lg:block ${collapsed ? 'w-16' : 'w-60'}`}><div className="sticky top-0 h-screen">{side(false)}</div></aside>
      {drawer && <div className="fixed inset-0 z-40 lg:hidden"><div className="absolute inset-0 bg-slate-900/50" onClick={() => setDrawer(false)} /><div className="relative h-full w-64">{side(true)}</div></div>}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white px-4">
          <button aria-label="Open menu" className="lg:hidden" onClick={() => setDrawer(true)}><Menu /></button>
          <button aria-label="Collapse sidebar" className="hidden lg:block" onClick={() => setCollapsed((c) => !c)}><PanelLeft /></button>
          {player ? <div className="flex-1" /> : <form onSubmit={search} className="relative max-w-md flex-1" role="search"><Search size={16} className="absolute left-3 top-2.5 text-slate-400" /><input aria-label="Search events, players" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search players, events…" className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm" /></form>}
          <div className="relative ml-auto">
            <button aria-label={`Notifications, ${high.length} ${staff ? 'unread' : 'high-risk'}`} onClick={() => { setBell((b) => !b); setMenu(false) }} className="relative rounded-lg p-2 hover:bg-slate-100">
              <Bell size={20} />
              {high.length > 0 && <span className="absolute -right-0.5 -top-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">{high.length > 99 ? '99+' : high.length}</span>}
            </button>
            {bell && (
              <div className="absolute right-0 mt-2 w-80 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-lg">
                <p className="font-semibold">Notifications</p>
                {high.length === 0 ? <p className="py-4 text-center text-slate-500">No unread alerts</p> : (
                  <ul className="mt-2 divide-y divide-slate-100">{high.slice(0, 5).map((e) => (
                    <li key={e.id}><Link to={`/events/${e.id}`} onClick={() => { setBell(false); markRead([e.id]) }} className="flex items-center justify-between gap-2 rounded-lg px-2 py-2 hover:bg-slate-50"><span className="truncate">{e.player.name ?? 'Unidentified'} · {e.region ?? '—'}</span><RiskBadge level={e.risk} /></Link></li>
                  ))}</ul>
                )}
                {updates.length > 0 && <>
                  <p className="mt-3 flex items-center gap-1.5 border-t pt-3 font-semibold"><Info size={14} className="text-sky-600" />Player updates</p>
                  <ul className="mt-1 divide-y divide-slate-100">{updates.slice(0, 3).map((e) => (
                    <li key={idKey(e)}><Link to={`/events/${e.id}`} onClick={() => setBell(false)} className="block rounded-lg px-2 py-2 hover:bg-slate-50"><UpdateText e={e} /></Link></li>
                  ))}</ul>
                </>}
                <button className="mt-2 inline-flex w-full items-center justify-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50" onClick={() => { setBell(false); nav(player ? '/player/events' : '/alerts') }}>{player ? 'View my injury events' : 'View all alerts'}</button>
                {staff && high.length > 0 && <button className="mt-2 w-full text-center text-xs text-slate-500 underline hover:text-slate-700" onClick={() => markRead(high.map((e) => e.id))}>Mark all {high.length} as read</button>}
              </div>
            )}
          </div>
          <div className="relative">
            <button onClick={() => { setMenu((m) => !m); setBell(false) }} className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-slate-100" aria-haspopup="menu" aria-expanded={menu}><span className="grid h-8 w-8 place-items-center rounded-full bg-[#0b1f3a] text-xs font-bold text-white">{(user.name[0] || '?').toUpperCase()}</span><span className="hidden text-left text-xs sm:block"><b className="block">{user.name}</b>{user.role}</span><ChevronDown size={14} /></button>
            {menu && <div role="menu" className="absolute right-0 mt-2 w-44 rounded-xl border border-slate-200 bg-white p-1 text-sm shadow-lg"><button role="menuitem" className="block w-full rounded px-3 py-2 text-left hover:bg-slate-100" onClick={() => { setMenu(false); nav(player ? '/player/profile' : '/settings') }}>{player ? 'My profile' : 'Profile & settings'}</button><button role="menuitem" className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-red-700 hover:bg-slate-100" onClick={() => { logout(); nav('/login', { replace: true }) }}><LogOut size={14} />Log out</button></div>}
          </div>
        </header>
        {user.dev && <div className="bg-amber-100 px-4 py-1.5 text-center text-xs font-semibold text-amber-900">DEV PREVIEW: not authenticated, no backend data. <Badge tone="amber">DEV DATA</Badge></div>}
        <main className="flex-1 p-4 md:p-6"><Outlet /></main>
        {popups.length > 0 && (
          <div className="fixed bottom-4 right-4 z-50 w-80 space-y-2" aria-live="polite">
            {popups.map((e) => (
              <div key={idKey(e)} className="flex gap-3 rounded-xl border border-sky-200 bg-white p-3 text-sm shadow-lg">
                <Info size={18} className="mt-0.5 shrink-0 text-sky-600" />
                <Link to={`/events/${e.id}`} onClick={() => closePopup(e)} className="min-w-0 flex-1"><p className="text-xs font-semibold uppercase text-sky-700">Player identified</p><UpdateText e={e} /></Link>
                <button aria-label="Close" onClick={() => closePopup(e)} className="self-start text-slate-400 hover:text-slate-600"><X size={16} /></button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}