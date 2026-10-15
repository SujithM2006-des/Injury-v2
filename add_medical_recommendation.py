"""
add_medical_recommendation.py - one-time update (run it once, then delete it)

Adds KEY 3 (medical recommendation) to the backend and the website:
  backend/main.py                   PATCH /events/{id}/ai-treatment -> output/ai_treatment.json,
                                    every event now carries "ai_treatment"
  frontend/src/types.ts             AiTreatment type
  frontend/src/api/dto/index.ts     AiTreatmentDto
  frontend/src/api/mappers/index.ts maps ai_treatment -> aiTreatment
  frontend/src/pages.tsx            "Medical recommendation" card on the event page
                                    (severity, urgency, mechanism, likely injuries, on-field steps,
                                    recommended tests, treatment, red flags, specialist, return to play)

Makes a .bak copy of each file first, and changes NOTHING if a file is not the version
it expects. Run it from the Technovation-main folder:
  python add_medical_recommendation.py
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

CHANGES = [
    ('backend/main.py',
r'''

# ============================================
# SERIALIZER''',
r'''

# Medical recommendation per event (src/gemini_treatment.py, KEY 3): tests, treatment,
# specialist, red flags, return to play. Kept in output/ai_treatment.json (no database change).
AI_TREATMENT_FILE = os.path.join(PROJECT_ROOT, "output", "ai_treatment.json")
_ai_treatment_cache = {"mtime": None, "data": {}}


def _ai_treatment_all():
    try:
        st = os.stat(AI_TREATMENT_FILE)
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    if _ai_treatment_cache["mtime"] != mtime:
        try:
            with open(AI_TREATMENT_FILE, "r", encoding="utf-8") as f:
                _ai_treatment_cache["data"] = _json.load(f)
        except (OSError, ValueError):
            _ai_treatment_cache["data"] = {}
        _ai_treatment_cache["mtime"] = mtime
    return _ai_treatment_cache["data"]


def _ai_treatment_for(event_id):
    return _ai_treatment_all().get(str(event_id))


# ============================================
# SERIALIZER'''),
    ('backend/main.py',
r'''        "gemini_checked_at": e.gemini_checked_at,
        "ai_injury": _ai_injury_for(e.id),
        "match_session_id": e.match_session_id,
        "match_name": (e.match.name if e.match is not None and e.match.name else''',
r'''        "gemini_checked_at": e.gemini_checked_at,
        "ai_injury": _ai_injury_for(e.id),
        "ai_treatment": _ai_treatment_for(e.id),
        "match_session_id": e.match_session_id,
        "match_name": (e.match.name if e.match is not None and e.match.name else'''),
    ('backend/main.py',
r'''
    return {"action": "stored", "event": event_to_dict(event)}

''',
r'''
    return {"action": "stored", "event": event_to_dict(event)}


# ============================================
# EVENTS — MEDICAL RECOMMENDATION (sent by src/gemini_treatment.py, KEY 3)
# Detailed review of the clip: mechanism, likely injuries, on-field safety measures,
# recommended tests (CT / MRI / X-ray ...), treatment, specialist, red flags and return
# to play. Stored in output/ai_treatment.json. Never deletes anything.
# ============================================

AI_TREATMENT_SEVERITIES = ("Low", "Medium", "High", "Critical")
AI_TREATMENT_URGENCIES = ("Emergency", "Same day", "Within 48 hours", "Routine")


class AiTreatmentInjury(BaseModel):
    injury: str
    likelihood: Optional[float] = None
    why: Optional[str] = None


class AiTreatmentTest(BaseModel):
    test: str
    why: Optional[str] = None


class AiTreatmentRequest(BaseModel):
    mechanism: Optional[str] = None
    body_part: Optional[str] = None
    side: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    confidence: Optional[float] = None
    injuries: list[AiTreatmentInjury] = []
    on_field: list[str] = []
    tests: list[AiTreatmentTest] = []
    treatment: list[str] = []
    specialist: Optional[str] = None
    red_flags: list[str] = []
    return_to_play: Optional[str] = None
    model: Optional[str] = None


def _clip_list(items, n_items, n_chars):
    return [t for t in (_clip_text(i, n_chars) for i in (items or [])[:n_items]) if t]


@app.patch("/events/{event_id}/ai-treatment")
def ai_treatment_result(event_id: int, request: AiTreatmentRequest, db: Session = Depends(get_db)):

    event = db.query(InjuryEvent).filter(InjuryEvent.id == event_id).first()

    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    record = {
        "mechanism": _clip_text(request.mechanism, 400),
        "body_part": _clip_text(request.body_part, 60),
        "side": request.side if request.side in ("left", "right") else None,
        "severity": request.severity if request.severity in AI_TREATMENT_SEVERITIES else None,
        "urgency": request.urgency if request.urgency in AI_TREATMENT_URGENCIES else None,
        "confidence": max(0.0, min(1.0, request.confidence)) if request.confidence is not None else None,
        "injuries": [
            {"injury": _clip_text(i.injury, 80),
             "likelihood": max(0.0, min(1.0, i.likelihood)) if i.likelihood is not None else None,
             "why": _clip_text(i.why, 200)}
            for i in request.injuries[:3] if _clip_text(i.injury, 80)
        ],
        "on_field": _clip_list(request.on_field, 6, 160),
        "tests": [{"test": _clip_text(t.test, 100), "why": _clip_text(t.why, 200)}
                  for t in request.tests[:5] if _clip_text(t.test, 100)],
        "treatment": _clip_list(request.treatment, 6, 160),
        "specialist": _clip_text(request.specialist, 120),
        "red_flags": _clip_list(request.red_flags, 5, 120),
        "return_to_play": _clip_text(request.return_to_play, 200),
        "model": _clip_text(request.model, 60),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    if not (record["injuries"] or record["tests"] or record["on_field"]):
        raise HTTPException(status_code=400, detail="Nothing to store")

    data = dict(_load_json(AI_TREATMENT_FILE, {}))
    data[str(event_id)] = record
    _save_json(AI_TREATMENT_FILE, data)

    print("[TREATMENT-AI] event", event_id, "->", record["severity"], "/", record["urgency"],
          "| tests:", ", ".join(t["test"] for t in record["tests"]) or "-")

    return {"action": "stored", "event": event_to_dict(event)}

'''),
    ('frontend/src/types.ts',
r'''}

/** One injury event (AI-detected fall or staff-logged event). */
export interface InjuryEvent {''',
r'''}

/** Detailed medical recommendation from the clip: tests, treatment, specialist, return to play. */
export interface AiTreatment {
  mechanism: string | null
  bodyPart: string | null
  side: string | null
  severity: string | null
  urgency: string | null
  confidence: number | null
  injuries: { injury: string; likelihood: number | null; why: string | null }[]
  onField: string[]
  tests: { test: string; why: string | null }[]
  treatment: string[]
  specialist: string | null
  redFlags: string[]
  returnToPlay: string | null
  checkedAt: string | null
}

/** One injury event (AI-detected fall or staff-logged event). */
export interface InjuryEvent {'''),
    ('frontend/src/types.ts',
r'''  gemini: GeminiInfo
  aiInjury: AiInjury | null
}
''',
r'''  gemini: GeminiInfo
  aiInjury: AiInjury | null
  aiTreatment: AiTreatment | null
}
'''),
    ('frontend/src/api/dto/index.ts',
r'''  gemini_jersey_confidence: number | null
  ai_injury?: AiInjuryDto | null
  match_session_id: number | null
  match_name: string | null''',
r'''  gemini_jersey_confidence: number | null
  ai_injury?: AiInjuryDto | null
  ai_treatment?: AiTreatmentDto | null
  match_session_id: number | null
  match_name: string | null'''),
    ('frontend/src/api/dto/index.ts',
r'''  model: string | null
  checked_at: string | null
}
''',
r'''  model: string | null
  checked_at: string | null
}

/** Medical recommendation (src/gemini_treatment.py, KEY 3): tests, treatment, specialist, return to play */
export interface AiTreatmentDto {
  mechanism: string | null
  body_part: string | null
  side: string | null
  severity: string | null
  urgency: string | null
  confidence: number | null
  injuries: { injury: string; likelihood: number | null; why: string | null }[]
  on_field: string[]
  tests: { test: string; why: string | null }[]
  treatment: string[]
  specialist: string | null
  red_flags: string[]
  return_to_play: string | null
  model: string | null
  checked_at: string | null
}
'''),
    ('frontend/src/api/mappers/index.ts',
r'''      checkedAt: e.ai_injury.checked_at ?? null,
    } : null,
  }
}''',
r'''      checkedAt: e.ai_injury.checked_at ?? null,
    } : null,
    aiTreatment: e.ai_treatment ? {
      mechanism: e.ai_treatment.mechanism ?? null,
      bodyPart: e.ai_treatment.body_part ?? null,
      side: e.ai_treatment.side ?? null,
      severity: e.ai_treatment.severity ?? null,
      urgency: e.ai_treatment.urgency ?? null,
      confidence: e.ai_treatment.confidence ?? null,
      injuries: (e.ai_treatment.injuries ?? []).map((i) => ({ injury: i.injury, likelihood: i.likelihood ?? null, why: i.why ?? null })),
      onField: e.ai_treatment.on_field ?? [],
      tests: (e.ai_treatment.tests ?? []).map((t) => ({ test: t.test, why: t.why ?? null })),
      treatment: e.ai_treatment.treatment ?? [],
      specialist: e.ai_treatment.specialist ?? null,
      redFlags: e.ai_treatment.red_flags ?? [],
      returnToPlay: e.ai_treatment.return_to_play ?? null,
      checkedAt: e.ai_treatment.checked_at ?? null,
    } : null,
  }
}'''),
    ('frontend/src/pages.tsx',
r'''          <p className="mt-2 text-sm font-semibold">AI-suggested screening categories, NOT a confirmed diagnosis.</p>
        </Card>
        <Card>
          <h2 className="font-semibold">Related</h2>''',
r'''          <p className="mt-2 text-sm font-semibold">AI-suggested screening categories, NOT a confirmed diagnosis.</p>
        </Card>
        <MedicalRecommendation e={e} />
        <Card>
          <h2 className="font-semibold">Related</h2>'''),
    ('frontend/src/pages.tsx',
r'''  )
}

/* ---------- MEDICAL ASSESSMENT (Medical only; route-guarded). Saved in output/assessments.json ---------- */''',
r'''  )
}

/* ---------- MEDICAL RECOMMENDATION (KEY 3, src/gemini_treatment.py) ---------- */
const URGENCY_TONE: Record<string, Tone> = { Emergency: 'red', 'Same day': 'amber', 'Within 48 hours': 'blue', Routine: 'green' }
const REC_SEVERITY_TONE: Record<string, Tone> = { Critical: 'red', High: 'red', Medium: 'amber', Low: 'green' }

function RecList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-800">{items.map((t) => <li key={t}>{t}</li>)}</ul>
    </div>
  )
}

/** Tests, treatment, specialist, red flags and return to play for one fall (shown on the event page). */
export function MedicalRecommendation({ e }: { e: InjuryEvent }) {
  const t = e.aiTreatment
  if (!t) return null
  return (
    <Card className="md:col-span-2 xl:col-span-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="flex items-center gap-2 font-semibold"><HeartPulse size={18} className="text-rose-600" />Medical recommendation</h2>
        {t.severity && <Badge tone={REC_SEVERITY_TONE[t.severity] ?? 'gray'}>Severity: {t.severity}</Badge>}
        {t.urgency && <Badge tone={URGENCY_TONE[t.urgency] ?? 'gray'}>Urgency: {t.urgency}</Badge>}
        {t.bodyPart && <span className="text-sm font-medium text-slate-600">{t.bodyPart}</span>}
      </div>
      {t.mechanism && <p className="mt-2 text-sm text-slate-700"><b>Mechanism:</b> {t.mechanism}</p>}
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        {t.injuries.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Likely injuries</p>
            <ul className="mt-1 space-y-1.5">{t.injuries.map((i) => (
              <li key={i.injury} className="rounded-lg bg-slate-50 px-2.5 py-1.5 text-sm">
                <span className="font-semibold">{i.injury}</span>{i.likelihood !== null && <span className="ml-2 text-xs text-slate-500">{Math.round(i.likelihood * 100)}%</span>}
                {i.why && <p className="text-xs text-slate-600">{i.why}</p>}
              </li>
            ))}</ul>
          </div>
        )}
        <RecList title="On the pitch now" items={t.onField} />
        {t.tests.length > 0 && (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Recommended tests</p>
            <ul className="mt-1 space-y-1.5">{t.tests.map((x) => (
              <li key={x.test} className="rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1.5 text-sm">
                <span className="font-semibold text-sky-900">{x.test}</span>
                {x.why && <p className="text-xs text-sky-800">{x.why}</p>}
              </li>
            ))}</ul>
          </div>
        )}
        <RecList title="Treatment" items={t.treatment} />
        {t.redFlags.length > 0 && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-2.5">
            <p className="text-xs font-semibold uppercase tracking-wide text-red-800">Red flags - emergency care if</p>
            <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-red-900">{t.redFlags.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        )}
        <div className="space-y-1 text-sm">
          {t.specialist && <p><b>Specialist:</b> {t.specialist}</p>}
          {t.returnToPlay && <p><b>Return to play:</b> {t.returnToPlay}</p>}
        </div>
      </div>
      <p className="mt-3 text-xs font-semibold text-slate-600">AI decision support from the clip, NOT a diagnosis. A qualified medical professional must confirm every test and treatment.</p>
    </Card>
  )
}

/* ---------- MEDICAL ASSESSMENT (Medical only; route-guarded). Saved in output/assessments.json ---------- */'''),
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

    print("Done. Restart the backend; the website reloads by itself.")


if __name__ == "__main__":
    main()