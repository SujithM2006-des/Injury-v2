"""
remove_description.py - one-time update (run it once, then delete it)

Removes the one-line description of what happened in the clip
(e.g. "A Dutch player goes to ground during a challenge near the goal.")
from the dashboard, events, alerts and the possible-injuries box.
The possible injuries and expected rest stay.

Changes only frontend/src/pages.tsx. Makes a .bak copy first, and changes
NOTHING if the file is not the version it expects.

Run it from the Technovation-main folder:
  python remove_description.py
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

CHANGES = [
    ('frontend/src/pages.tsx',
r'''        {a.rest && <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-amber-900 ring-1 ring-amber-200"><CalendarDays size={12} />Expected rest {a.rest}</span>}
      </div>
      {a.description && <p className="mt-1 text-xs text-amber-900">{a.description}</p>}
      <ul className="mt-2 space-y-1.5">
        {a.injuries.map((i, k) => (''',
r'''        {a.rest && <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-0.5 text-xs font-semibold text-amber-900 ring-1 ring-amber-200"><CalendarDays size={12} />Expected rest {a.rest}</span>}
      </div>
      <ul className="mt-2 space-y-1.5">
        {a.injuries.map((i, k) => ('''),
    ('frontend/src/pages.tsx',
r'''          <p className="flex items-center gap-2 truncate text-sm font-medium"><PlayerName e={e} ids={ids} /><span className="text-slate-400">{e.eventType}</span></p>
          <p className="truncate text-xs text-slate-500">{e.region ?? '—'} · {matchShort(e.matchName) ?? 'No match'}{fmtVideo(e.videoTimeSec) && ` · ${fmtVideo(e.videoTimeSec)} in video`} · detected {fmtWhen(e.timestamp)}</p>
          {e.aiInjury ? <p className="truncate text-xs text-slate-600" title={e.aiInjury.description ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{injuryText(e)}</p>
            : e.gemini.description && <p className="truncate text-xs text-slate-600" title={e.gemini.reason ?? ''}><Sparkles size={11} className="mr-1 inline text-emerald-600" />{e.gemini.description}</p>}
        </div>
        {g && <span className="hidden sm:inline-flex" title={e.gemini.reason ?? ''}><Badge tone={g.tone}>{g.text}</Badge></span>}''',
r'''          <p className="flex items-center gap-2 truncate text-sm font-medium"><PlayerName e={e} ids={ids} /><span className="text-slate-400">{e.eventType}</span></p>
          <p className="truncate text-xs text-slate-500">{e.region ?? '—'} · {matchShort(e.matchName) ?? 'No match'}{fmtVideo(e.videoTimeSec) && ` · ${fmtVideo(e.videoTimeSec)} in video`} · detected {fmtWhen(e.timestamp)}</p>
          {e.aiInjury && <p className="truncate text-xs text-slate-600"><Sparkles size={11} className="mr-1 inline text-emerald-600" />{injuryText(e)}</p>}
        </div>
        {g && <span className="hidden sm:inline-flex" title={e.gemini.reason ?? ''}><Badge tone={g.tone}>{g.text}</Badge></span>}'''),
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

    print("Done. The website reloads by itself (press Ctrl+Shift+R if not).")


if __name__ == "__main__":
    main()