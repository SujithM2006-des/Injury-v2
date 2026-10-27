import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, NavLink, Navigate, Outlet, useNavigate } from 'react-router-dom'
import { MonitorPlay } from 'lucide-react'
import { LayoutDashboard, Users, Shield, Video, Activity, Zap, Bell, FileText, UserCog, Server, Settings, Menu, PanelLeft, Search, LogOut, HelpCircle, ChevronDown, UserRound, History, Info, X, type LucideIcon } from 'lucide-react'
import { useAuth, home } from './auth'
import type { InjuryEvent, Role } from './types'
import { useQueryClient } from '@tanstack/react-query'
import { useAlertReads, useDetector, useEvents } from './queries'
import { markAlertsRead } from './api/services'
import { Badge, Logo, LogoMark, RiskBadge, useDismiss } from './ui'
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
  { label: 'Match Analysis', to: '/matches', icon: Video },
  { label: 'Injury Events', to: '/events', icon: Activity },
  { label: 'Collisions', to: '/collisions', icon: Zap },
  { label: 'Alerts', to: '/alerts', icon: Bell },
]
export const navFor = (r: Role): N[] => {
  const dash: N = { label: 'Dashboard', to: home[r], icon: LayoutDashboard }
  // every role: the detection of the match being analysed, live
  const live: N = { label: 'Watch Live', to: '/live', icon: MonitorPlay }
  return [dash, live, ...navRest(r)]
}

const navRest = (r: Role): N[] => {
  const set: N = { label: 'Settings', to: '/settings', icon: Settings }
  const rep: N = { label: 'Reports', to: '/reports', icon: FileText }
  // Menu: Injury Events, Teams & Players, Alerts. Players live inside "Teams & Players";
  // Match Analysis and Collisions are not in the menu (they still open from links inside events).
  const adminCommon = common().filter((i) => i.to !== '/players' && i.to !== '/matches' && i.to !== '/collisions')
  // Injury Events, Teams & Players, Alerts
  const main = (teamsLabel: string): N[] => [adminCommon[0], { label: teamsLabel, to: '/teams', icon: Shield }, ...adminCommon.slice(1)]
  // Player: only their own pages
  if (r === 'PLAYER') return [{ label: 'Profile', to: '/player/profile', icon: UserRound }, { label: 'History', to: '/player/history', icon: History }, { label: 'Events', to: '/player/events', icon: Activity }, { label: 'Reports', to: '/player/reports', icon: FileText }]
  if (r === 'ADMIN') return [...main('Teams & Players'), rep, { label: 'Users', to: '/admin/users', icon: UserCog }, { label: 'System', to: '/admin/system', icon: Server }, set]
  // Team owner: the admin menu, limited to their own team (the pages themselves only show that team)
  if (r === 'OWNER') return [...main('Team & Players'), rep, { label: 'Users', to: '/admin/users', icon: UserCog }, { label: 'System', to: '/admin/system', icon: Server }, set]
  // Medical staff and coaches: same short menu as admin (Players, Matches and Collisions are reached from
  // inside "Team & Players" and the events), plus Reports.
  return [...main(r === 'COACH' ? 'Team & Players' : 'Teams & Players'), rep, set]
}

export default function Layout() {
  const { user, logout } = useAuth()
  const nav = useNavigate()
  const [collapsed, setCollapsed] = useState(false)
  const [drawer, setDrawer] = useState(false)
  const [bell, setBell] = useState(false)
  const [menu, setMenu] = useState(false)
  const bellRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  // red LIVE tag on "Watch Live" while a match is being analysed
  const detector = useDetector(!!user && !user.dev)
  const isLive = ['launching', 'starting', 'running'].includes(detector.data?.state ?? '')
  const closeBell = useCallback(() => setBell(false), [])
  const closeMenu = useCallback(() => setMenu(false), [])
  useDismiss(bell, closeBell, bellRef)
  useDismiss(menu, closeMenu, menuRef)
  const [q, setQ] = useState('')
  const events = useEvents()
  // Every logged-in user: the bell shows their own unread alerts (every risk level).
  const staff = !!user && !user.dev
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

  const ROLE_NAME: Record<Role, string> = { ADMIN: 'Administrator', MEDICAL: 'Medical staff', COACH: 'Coach', PLAYER: 'Player', OWNER: 'Team owner' }
  const player = user.role === 'PLAYER'
  const side = (mobile: boolean) => {
    const wide = mobile || !collapsed
    const link = (isActive: boolean) => `group relative flex items-center gap-3 rounded-xl ${wide ? 'px-3.5' : 'justify-center px-0'} py-2.5 text-sm font-medium transition ${isActive ? 'bg-brand-600 text-white shadow-lg shadow-brand-600/30' : 'text-slate-300 hover:bg-white/[.06] hover:text-white'}`
    return (
      <nav aria-label="Main" className="flex h-full flex-col bg-gradient-to-b from-navy-900 to-navy-950 text-slate-200">
        <div className={`flex h-[72px] shrink-0 items-center border-b border-white/[.07] ${wide ? 'px-5' : 'justify-center'}`}>{wide ? <Logo size={32} /> : <LogoMark size={32} />}</div>
        {wide && <p className="px-6 pb-2 pt-6 text-[11px] font-semibold uppercase tracking-wider text-slate-500">Menu</p>}
        <ul className={`ag-scroll flex-1 space-y-1 overflow-y-auto px-3 ${wide ? 'pb-4' : 'py-6'}`}>
          {items.map((i) => (
            <li key={i.to}>
              <NavLink to={i.to} onClick={() => setDrawer(false)} title={i.label} className={({ isActive }) => link(isActive)}>
                <i.icon size={19} className="shrink-0" />{wide && i.label}
                {i.to === '/live' && isLive && (wide
                  ? <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />LIVE</span>
                  : <span className="absolute right-2 top-2 h-2 w-2 animate-pulse rounded-full bg-red-500" aria-label="Live now" />)}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="shrink-0 space-y-1 border-t border-white/[.07] px-3 py-4">
          {wide && (
            <div className="mb-2 flex items-center gap-3 rounded-xl bg-white/[.05] px-3 py-3 ring-1 ring-white/[.06]">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-brand-600 text-sm font-bold text-white">{(user.name[0] || '?').toUpperCase()}</span>
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
    <div className="flex min-h-screen bg-[#f3f6fb]">
      <aside className={`hidden shrink-0 bg-navy-950 lg:block ${collapsed ? 'w-[72px]' : 'w-64'}`}><div className="sticky top-0 h-screen">{side(false)}</div></aside>
      {drawer && <div className="fixed inset-0 z-40 lg:hidden"><div className="absolute inset-0 bg-navy-950/60 backdrop-blur-sm" onClick={() => setDrawer(false)} /><div className="relative h-full w-64">{side(true)}</div></div>}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[72px] items-center gap-3 border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur md:px-6">
          <button aria-label="Open menu" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setDrawer(true)}><Menu size={20} /></button>
          <button aria-label="Collapse sidebar" className="hidden rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:block" onClick={() => setCollapsed((c) => !c)}><PanelLeft size={20} /></button>
          {player ? <div className="flex-1" /> : <form onSubmit={search} className="relative max-w-md flex-1" role="search"><Search size={16} className="absolute left-3.5 top-3 text-slate-400" /><input aria-label="Search events, players" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search players, matches, events…" className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-3 text-sm outline-none transition focus:border-brand-600 focus:bg-white focus:ring-2 focus:ring-brand-600/15" /></form>}
          <div ref={bellRef} className="relative ml-auto">
            <button aria-expanded={bell} aria-label={`Notifications, ${high.length} ${staff ? 'unread' : 'high-risk'}`} onClick={() => { setBell((b) => !b); setMenu(false) }} className="relative rounded-xl border border-slate-200 bg-white p-2.5 text-slate-600 hover:bg-slate-50">
              <Bell size={18} />
              {high.length > 0 && <span className="absolute -right-0.5 -top-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">{high.length > 99 ? '99+' : high.length}</span>}
            </button>
            {bell && (
              <div className="absolute right-0 mt-2 w-80 rounded-2xl border border-slate-200 bg-white p-4 text-sm shadow-xl">
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
          <div ref={menuRef} className="relative">
            <button onClick={() => { setMenu((m) => !m); setBell(false) }} className="flex items-center gap-2.5 rounded-xl py-1 pl-1 pr-2 hover:bg-slate-100" aria-haspopup="menu" aria-expanded={menu}><span className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-brand-600 text-sm font-bold text-white">{(user.name[0] || '?').toUpperCase()}</span><span className="hidden text-left text-xs leading-tight sm:block"><b className="block text-sm text-navy-900">{user.name}</b><span className="text-slate-500">{ROLE_NAME[user.role]}</span></span><ChevronDown size={14} className="text-slate-400" /></button>
            {menu && <div role="menu" className="absolute right-0 mt-2 w-44 rounded-2xl border border-slate-200 bg-white p-1 text-sm shadow-lg"><button role="menuitem" className="block w-full rounded px-3 py-2 text-left hover:bg-slate-100" onClick={() => { setMenu(false); nav(player ? '/player/profile' : '/settings') }}>{player ? 'My profile' : 'Profile & settings'}</button><button role="menuitem" className="flex w-full items-center gap-2 rounded px-3 py-2 text-left text-red-700 hover:bg-slate-100" onClick={() => { logout(); nav('/login', { replace: true }) }}><LogOut size={14} />Log out</button></div>}
          </div>
        </header>
        {user.dev && <div className="bg-amber-100 px-4 py-1.5 text-center text-xs font-semibold text-amber-900">DEV PREVIEW: not authenticated, no backend data. <Badge tone="amber">DEV DATA</Badge></div>}
        <main className="flex-1 p-4 md:p-7"><Outlet /></main>
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