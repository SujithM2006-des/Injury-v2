"""
apply_identifying.py - one-time update (run it once, then delete it)

Adds to AthleteGuard:
  1. "Identifying player... 42%" bar on Unidentified falls while the detector is still
     looking for the player (2 minutes of video). When the player is found, the bar is
     replaced by the name; when the 2 minutes pass, it shows "Unidentified player".
  2. Event rows show WHEN the fall was detected ("detected 14 Oct, 05:17 pm") and the
     match name without the run's start date (that date is why the time looked wrong).

Changes only these lines in:
  backend/main.py               (GET /detector/status also lists falls being identified)
  frontend/src/api/dto/index.ts (type for that list)
  frontend/src/pages.tsx        (bar on dashboard, events, alerts, reports, event page)

Safe: makes a .bak copy of each file first, and changes NOTHING if any file
is not the version it expects.

Run it from the Technovation-main folder:
  python apply_identifying.py
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

CHANGES = [
    ('backend/main.py',
r'''# ---------- detector progress for match pages (every role) ----------

@app.get("/detector/status")
def detector_progress(current_user: User = Depends(get_current_user)):

    status = _read_detector_status()''',
r'''# ---------- detector progress for match pages (every role) ----------

# An Unidentified fall keeps looking for its player for this long (in video time).
# Same value as IDENTIFY_WINDOW_SECONDS in src/multi_player_injury.py.
IDENTIFY_WINDOW_SEC = 120


def _identifying_events(db, match_id, frame, fps):
    """Unidentified falls of the running match that are still being identified,
    with how far along the search is: [{"event_id": 12, "pct": 40}]."""
    if not match_id or not frame or not fps:
        return []
    video_now = float(frame) / float(fps)
    rows = (
        db.query(InjuryEvent.id, InjuryEvent.video_time_sec)
        .filter(
            InjuryEvent.match_session_id == match_id,
            InjuryEvent.player_id.is_(None),
            InjuryEvent.video_time_sec.isnot(None),
            InjuryEvent.video_time_sec >= video_now - IDENTIFY_WINDOW_SEC,
        )
        .all()
    )
    out = []
    for event_id, t in rows:
        pct = int(round(100 * max(0.0, video_now - float(t)) / IDENTIFY_WINDOW_SEC))
        out.append({"event_id": event_id, "pct": max(1, min(99, pct))})
    return out


@app.get("/detector/status")
def detector_progress(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    status = _read_detector_status()'''),
    ('backend/main.py',
r'''    progress = status.get("progress") or {}

    return {
        "state": state,
        "match_id": info.get("match_id"),
        "match_name": info.get("match_name"),''',
r'''    progress = status.get("progress") or {}

    identifying = []
    if state in ("starting", "running"):
        try:
            identifying = _identifying_events(db, info.get("match_id"), progress.get("frame"), info.get("fps"))
        except Exception as e:
            print("[DETECTOR] Could not list falls being identified:", e)

    return {
        "state": state,
        "identifying": identifying,
        "match_id": info.get("match_id"),
        "match_name": info.get("match_name"),'''),
    ('frontend/src/api/dto/index.ts',
r'''  finished_at?: string | null
  seconds_since_last_signal?: number | null
}
''',
r'''  finished_at?: string | null
  seconds_since_last_signal?: number | null
  /** Unidentified falls of the running match that are still being identified (pct = search progress) */
  identifying?: { event_id: number; pct: number }[]
}
'''),
    ('frontend/src/pages.tsx',
r'''}

/** Gemini's possible injuries as one line, e.g. "Hamstring strain, Calf strain · rest 1-8+ weeks".
 *  Falls back to the detector's own note when Gemini has not reviewed the clip (yet). */''',
r'''}

/* ---------- player identification in progress ----------
 * While the detector runs, an Unidentified fall keeps looking for its player for 2 minutes of video.
 * The backend reports how far that search is (GET /detector/status -> identifying). */
export function useIdentifying() {
  const d = useDetector()
  const m = new Map<number, number>()
  for (const x of d.data?.identifying ?? []) m.set(x.event_id, x.pct)
  return m
}

/** "fall_test - 14 Oct 2026 13:54" -> "fall_test" (the date is when the run started, not when the fall happened) */
export const matchShort = (name: string | null) => (name ? name.replace(/\s+-\s+\d{1,2} \w{3} \d{4} \d{1,2}:\d{2}$/, '') : null)
/** When the fall was detected, e.g. "14 Oct, 05:17 pm" */
export const fmtWhen = (v: string | null) => (v ? new Date(v).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—')

/** Thin bar with "Identifying player… 42%" */
export function IdentifyingBar({ pct }: { pct: number }) {
  return (
    <span className="inline-flex min-w-40 max-w-56 flex-1 flex-col gap-0.5 align-middle" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Identifying player">
      <span className="flex items-center gap-1 text-xs font-medium text-sky-700"><Loader2 size={12} className="animate-spin" />Identifying player… {pct}%</span>
      <span className="h-1.5 overflow-hidden rounded-full bg-slate-200"><span className="block h-1.5 rounded-full bg-sky-500 transition-all duration-700" style={{ width: `${pct}%` }} /></span>
    </span>
  )
}

/** Player name, the identifying bar while the search runs, or "Unidentified player" when it has ended */
export function PlayerName({ e, ids, withJersey = true }: { e: InjuryEvent; ids: Map<number, number>; withJersey?: boolean }) {
  if (e.player.name) return <>{e.player.name}{withJersey && e.player.jersey !== null ? ` #${e.player.jersey}` : ''}</>
  const pct = ids.get(e.id)
  return pct !== undefined ? <IdentifyingBar pct={pct} /> : <>Unidentified player</>
}

/** Gemini's possible injuries as one line, e.g. "Hamstring strain, Calf strain · rest 1-8+ weeks".
 *  Falls back to the detector's own note when Gemini has not reviewed the clip (yet). */'''),
    ('frontend/src/pages.tsx',
r'''export function EventLine({ e, to }: { e: InjuryEvent; to?: string }) {
  const g = geminiBadge(e)
  return (
    <li>
      <Link to={to ?? `/events/${e.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-slate-50">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{e.player.name ? `${e.player.name} #${e.player.jersey ?? '?'}` : 'Unidentified player'}<span className="ml-2 text-slate-400">{e.eventType}</span></p>
          <p className="truncate text-xs text-slate-500">{e.region ?? '—'} · {e.matchName ?? 'No match'}{fmtVideo(e.videoTimeSec) && ` · ${fmtVideo(e.videoTimeSec)} in video`}</p>
          {e.aiInjury ? <p className="truncate text-xs text-slate-600" title={e.aiInjury.description ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{injuryText(e)}</p>
            : e.gemini.description && <p className="truncate text-xs text-slate-600" title={e.gemini.reason ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{e.gemini.description}</p>}''',
r'''export function EventLine({ e, to }: { e: InjuryEvent; to?: string }) {
  const g = geminiBadge(e)
  const ids = useIdentifying()
  return (
    <li>
      <Link to={to ?? `/events/${e.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-slate-50">
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-2 truncate text-sm font-medium"><PlayerName e={e} ids={ids} /><span className="text-slate-400">{e.eventType}</span></p>
          <p className="truncate text-xs text-slate-500">{e.region ?? '—'} · {matchShort(e.matchName) ?? 'No match'}{fmtVideo(e.videoTimeSec) && ` · ${fmtVideo(e.videoTimeSec)} in video`} · detected {fmtWhen(e.timestamp)}</p>
          {e.aiInjury ? <p className="truncate text-xs text-slate-600" title={e.aiInjury.description ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{injuryText(e)}</p>
            : e.gemini.description && <p className="truncate text-xs text-slate-600" title={e.gemini.reason ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{e.gemini.description}</p>}'''),
    ('frontend/src/pages.tsx',
r'''  const toast = useToast()
  const ev = useEvents()
  const matches = useMatches().data ?? []
  const [sp, setSp] = useSearchParams()''',
r'''  const toast = useToast()
  const ev = useEvents()
  const ids = useIdentifying()
  const matches = useMatches().data ?? []
  const [sp, setSp] = useSearchParams()'''),
    ('frontend/src/pages.tsx',
r'''              {!ev.isLoading && !ev.isError && rows.map((e) => (
                <tr key={e.id} className="border-t align-top hover:bg-slate-50">
                  <td className="min-w-40 px-4 py-3"><p className="font-semibold">{playerText(e)}</p>{e.player.team && <p className="text-xs text-slate-500">{e.player.team}</p>}{!e.identified && <div className="mt-1"><Badge tone="amber">Unidentified</Badge></div>}</td>
                  <td className="px-4 py-3"><p className="font-medium">{e.eventType}</p><p className="text-xs text-slate-500">{e.region ?? 'Body area not recorded'}</p><Link to={`/events/${e.id}`} className={btnSm + ' mt-2'}><ExternalLink size={14} />Open #{e.id}</Link></td>
                  <td className="px-4 py-3"><RiskBadge level={e.risk} /></td>''',
r'''              {!ev.isLoading && !ev.isError && rows.map((e) => (
                <tr key={e.id} className="border-t align-top hover:bg-slate-50">
                  <td className="min-w-40 px-4 py-3"><p className="font-semibold"><PlayerName e={e} ids={ids} /></p>{e.player.team && <p className="text-xs text-slate-500">{e.player.team}</p>}{!e.identified && !ids.has(e.id) && <div className="mt-1"><Badge tone="amber">Unidentified</Badge></div>}</td>
                  <td className="px-4 py-3"><p className="font-medium">{e.eventType}</p><p className="text-xs text-slate-500">{e.region ?? 'Body area not recorded'}</p><Link to={`/events/${e.id}`} className={btnSm + ' mt-2'}><ExternalLink size={14} />Open #{e.id}</Link></td>
                  <td className="px-4 py-3"><RiskBadge level={e.risk} /></td>'''),
    ('frontend/src/pages.tsx',
r'''function EventsList({ collisions, q, risk, type, match, identity, filtered }: { collisions: boolean; q: string; risk: string; type: string; match: string; identity: string; filtered: boolean }) {
  const ev = useEvents()
  const { user } = useAuth()
  const nav = useNavigate()''',
r'''function EventsList({ collisions, q, risk, type, match, identity, filtered }: { collisions: boolean; q: string; risk: string; type: string; match: string; identity: string; filtered: boolean }) {
  const ev = useEvents()
  const ids = useIdentifying()
  const { user } = useAuth()
  const nav = useNavigate()'''),
    ('frontend/src/pages.tsx',
r'''                  <td className="min-w-48 px-4 py-3">
                    {e.identified && e.player.playerId !== null ? <><PlayerToggle open={open === e.id} onClick={() => setOpen(open === e.id ? null : e.id)}>{e.player.name}{e.player.jersey !== null && <span className="ml-1 text-slate-400">#{e.player.jersey}</span>}</PlayerToggle>{e.player.team && <p className="text-xs text-slate-500">{e.player.team}</p>}</>
                      : e.player.trackId !== null && <p className="text-xs text-slate-500">track {e.player.trackId}</p>}
                    <div className="mt-1"><IdentityBadge s={e.player.identityStatus} label={identText(e)} title={e.idDetail ?? ''} /></div>
                    {user && canAssign(user.role, e) && <button className={btnSm + ' mt-2'} onClick={() => nav(`${base}/${e.id}`)}>{e.identified ? 'Change player' : e.clipUrl ? 'Review clip & identify' : 'Assign player'}</button>}''',
r'''                  <td className="min-w-48 px-4 py-3">
                    {e.identified && e.player.playerId !== null ? <><PlayerToggle open={open === e.id} onClick={() => setOpen(open === e.id ? null : e.id)}>{e.player.name}{e.player.jersey !== null && <span className="ml-1 text-slate-400">#{e.player.jersey}</span>}</PlayerToggle>{e.player.team && <p className="text-xs text-slate-500">{e.player.team}</p>}</>
                      : <>{ids.has(e.id) && <IdentifyingBar pct={ids.get(e.id)!} />}{e.player.trackId !== null && <p className="text-xs text-slate-500">track {e.player.trackId}</p>}</>}
                    <div className="mt-1"><IdentityBadge s={e.player.identityStatus} label={identText(e)} title={e.idDetail ?? ''} /></div>
                    {user && canAssign(user.role, e) && <button className={btnSm + ' mt-2'} onClick={() => nav(`${base}/${e.id}`)}>{e.identified ? 'Change player' : e.clipUrl ? 'Review clip & identify' : 'Assign player'}</button>}'''),
    ('frontend/src/pages.tsx',
r'''  const { user } = useAuth()
  const ev = useEvents()
  const [saved, setSaved] = useState<InjuryEvent | null>(null)
  const fromList = (ev.data ?? []).find((e) => String(e.id) === id)''',
r'''  const { user } = useAuth()
  const ev = useEvents()
  const ids = useIdentifying()
  const [saved, setSaved] = useState<InjuryEvent | null>(null)
  const fromList = (ev.data ?? []).find((e) => String(e.id) === id)'''),
    ('frontend/src/pages.tsx',
r'''        <Card>
          <p className="text-xs font-semibold uppercase text-slate-500">{collision ? 'Player A' : 'Player'}</p>
          <p className="mt-1 text-lg font-bold">{e.player.name ?? 'Unknown Player'}</p>
          <div className="mt-1"><IdentityBadge s={e.player.identityStatus} label={identText(e)} /></div>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">''',
r'''        <Card>
          <p className="text-xs font-semibold uppercase text-slate-500">{collision ? 'Player A' : 'Player'}</p>
          <p className="mt-1 text-lg font-bold">{e.player.name ?? (ids.has(e.id) ? <IdentifyingBar pct={ids.get(e.id)!} /> : 'Unknown Player')}</p>
          <div className="mt-1"><IdentityBadge s={e.player.identityStatus} label={identText(e)} /></div>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">'''),
    ('frontend/src/pages.tsx',
r'''}
function AdminAlerts() {
  const [pri, setPri] = useState('All')
  const [read, setRead] = useState('All')''',
r'''}
function AdminAlerts() {
  const ids = useIdentifying()
  const [pri, setPri] = useState('All')
  const [read, setRead] = useState('All')'''),
    ('frontend/src/pages.tsx',
r'''              <Link to={`/events/${e.id}`} className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50">
                {!e.resolved && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-sky-500" aria-label="Unread" />}
                <div className="min-w-0 flex-1"><p className="text-sm font-medium">{e.player.name ?? 'Unidentified player'} · {e.eventType} · {e.region ?? '—'}</p><p className="truncate text-xs text-slate-500">{injuryText(e) ?? ''}</p><p className="text-xs text-slate-400">{fmtDate(e.timestamp)}{e.matchName ? ` · ${e.matchName}` : ''}</p></div>
                <RiskBadge level={e.risk} />
              </Link>''',
r'''              <Link to={`/events/${e.id}`} className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50">
                {!e.resolved && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-sky-500" aria-label="Unread" />}
                <div className="min-w-0 flex-1"><p className="flex flex-wrap items-center gap-x-1 text-sm font-medium"><PlayerName e={e} ids={ids} withJersey={false} /> · {e.eventType} · {e.region ?? '—'}</p><p className="truncate text-xs text-slate-500">{injuryText(e) ?? ''}</p><p className="text-xs text-slate-400">{fmtDate(e.timestamp)}{e.matchName ? ` · ${e.matchName}` : ''}</p></div>
                <RiskBadge level={e.risk} />
              </Link>'''),
    ('frontend/src/pages.tsx',
r'''function StaffAlerts() {
  const { user } = useAuth()
  const [pri, setPri] = useState('All')
  const [read, setRead] = useState('All')''',
r'''function StaffAlerts() {
  const { user } = useAuth()
  const ids = useIdentifying()
  const [pri, setPri] = useState('All')
  const [read, setRead] = useState('All')'''),
    ('frontend/src/pages.tsx',
r'''                <Link to={`/events/${e.id}`} onClick={() => open(e.id)} className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${isUnread ? 'bg-sky-500' : 'bg-transparent'}`} aria-label={isUnread ? 'Unread' : 'Read'} />
                  <div className="min-w-0 flex-1"><p className={`text-sm ${isUnread ? 'font-semibold' : 'font-medium text-slate-700'}`}>{e.player.name ?? 'Unidentified player'} · {e.eventType} · {e.region ?? '—'}</p><p className="truncate text-xs text-slate-500">{injuryText(e) ?? ''}</p><p className="text-xs text-slate-400">{fmtDate(e.timestamp)}{e.matchName ? ` · ${e.matchName}` : ''}{e.resolved ? ' · reviewed by medical staff' : ''}</p></div>
                  <RiskBadge level={e.risk} />
                </Link>''',
r'''                <Link to={`/events/${e.id}`} onClick={() => open(e.id)} className="flex items-start gap-3 px-4 py-3 hover:bg-slate-50">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${isUnread ? 'bg-sky-500' : 'bg-transparent'}`} aria-label={isUnread ? 'Unread' : 'Read'} />
                  <div className="min-w-0 flex-1"><p className={`flex flex-wrap items-center gap-x-1 text-sm ${isUnread ? 'font-semibold' : 'font-medium text-slate-700'}`}><PlayerName e={e} ids={ids} withJersey={false} /> · {e.eventType} · {e.region ?? '—'}</p><p className="truncate text-xs text-slate-500">{injuryText(e) ?? ''}</p><p className="text-xs text-slate-400">{fmtDate(e.timestamp)}{e.matchName ? ` · ${e.matchName}` : ''}{e.resolved ? ' · reviewed by medical staff' : ''}</p></div>
                  <RiskBadge level={e.risk} />
                </Link>'''),
]


def main():
    texts = {}
    crlf = {}
    for path in sorted({c[0] for c in CHANGES}):
        full = os.path.join(ROOT, *path.split("/"))
        if not os.path.isfile(full):
            print("NOT FOUND:", full)
            print("Run this script from the Technovation-main folder.")
            sys.exit(1)
        with open(full, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
        crlf[path] = "\r\n" in raw
        texts[path] = raw.replace("\r\n", "\n")

    # check everything first, so nothing is half-changed
    problems = []
    for i, (path, old, new) in enumerate(CHANGES, 1):
        t = texts[path]
        if new in t and old not in t:
            problems.append("change %d in %s is already applied" % (i, path))
        elif t.count(old) != 1:
            problems.append("change %d in %s: expected text not found (file is a different version)" % (i, path))
    if problems:
        print("Nothing was changed:")
        for p in problems:
            print("  -", p)
        sys.exit(1)

    for path, old, new in CHANGES:
        texts[path] = texts[path].replace(old, new, 1)

    for path, t in texts.items():
        full = os.path.join(ROOT, *path.split("/"))
        shutil.copyfile(full, full + ".bak")
        if crlf[path]:
            t = t.replace("\n", "\r\n")
        with open(full, "w", encoding="utf-8", newline="") as f:
            f.write(t)
        print("Updated", path, "(backup:", os.path.basename(full) + ".bak)")

    print("Done. Restart the backend; the frontend reloads by itself.")


if __name__ == "__main__":
    main()