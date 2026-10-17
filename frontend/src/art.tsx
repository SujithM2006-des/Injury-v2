/* =====================================================================
   ILLUSTRATIONS (drawn in SVG, no photo files needed)
   Stadium backdrop, footballer #10, role scenes, body region map.
   ===================================================================== */

/** Night stadium: floodlights, stands with crowd lights, striped pitch. Fills its parent. */
export function StadiumBackdrop({ className = '' }: { className?: string }) {
  const dots = Array.from({ length: 140 }, (_, i) => ({ x: (i * 97) % 1600, y: 300 + ((i * 53) % 120), r: 1 + (i % 3) * 0.6, o: 0.25 + ((i * 7) % 10) / 20 }))
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 1600 700" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id="sb-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#030b1d" />
          <stop offset=".55" stopColor="#0a2150" />
          <stop offset="1" stopColor="#0d2a5c" />
        </linearGradient>
        <radialGradient id="sb-glow" cx=".5" cy=".5" r=".5">
          <stop offset="0" stopColor="#dbeafe" stopOpacity=".95" />
          <stop offset=".25" stopColor="#93c5fd" stopOpacity=".45" />
          <stop offset="1" stopColor="#1d4ed8" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="sb-beam" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#bfdbfe" stopOpacity=".28" />
          <stop offset="1" stopColor="#bfdbfe" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="sb-pitch" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#14532d" />
          <stop offset="1" stopColor="#052e16" />
        </linearGradient>
        <linearGradient id="sb-stand" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0b1f45" />
          <stop offset="1" stopColor="#071530" />
        </linearGradient>
      </defs>
      <rect width="1600" height="700" fill="url(#sb-sky)" />
      {/* light beams */}
      <path d="M180 120 L40 700 L520 700 Z" fill="url(#sb-beam)" />
      <path d="M1420 120 L1080 700 L1560 700 Z" fill="url(#sb-beam)" />
      {/* stands */}
      <path d="M0 290 Q800 230 1600 290 L1600 440 L0 440 Z" fill="url(#sb-stand)" />
      <path d="M0 330 Q800 280 1600 330" fill="none" stroke="#1e3a8a" strokeOpacity=".6" />
      <path d="M0 380 Q800 335 1600 380" fill="none" stroke="#1e3a8a" strokeOpacity=".5" />
      {dots.map((d, i) => <circle key={i} cx={d.x} cy={d.y} r={d.r} fill="#93c5fd" opacity={d.o} />)}
      {/* floodlight towers */}
      {[180, 1420].map((x) => (
        <g key={x}>
          <rect x={x - 3} y="150" width="6" height="160" fill="#0b1f45" />
          <rect x={x - 60} y="96" width="120" height="44" rx="6" fill="#0f2a5a" />
          {[0, 1, 2, 3].map((c) => [0, 1].map((r) => <circle key={`${c}${r}`} cx={x - 42 + c * 28} cy={108 + r * 20} r="7" fill="#eff6ff" />))}
          <circle cx={x} cy="118" r="210" fill="url(#sb-glow)" />
        </g>
      ))}
      {/* pitch with mowing stripes */}
      <path d="M0 440 L1600 440 L1600 700 L0 700 Z" fill="url(#sb-pitch)" />
      {Array.from({ length: 9 }, (_, i) => <path key={i} d={`M${i * 200 - 40} 440 L${i * 200 + 60} 440 L${i * 260 - 120} 700 L${i * 260 - 250} 700 Z`} fill="#166534" opacity=".35" />)}
      <path d="M260 700 L520 450 L1080 450 L1340 700" fill="none" stroke="#dcfce7" strokeOpacity=".35" strokeWidth="3" />
      <ellipse cx="800" cy="560" rx="170" ry="48" fill="none" stroke="#dcfce7" strokeOpacity=".3" strokeWidth="3" />
      <path d="M800 450 L800 700" stroke="#dcfce7" strokeOpacity=".3" strokeWidth="3" />
    </svg>
  )
}

/** Footballer seen from behind in a blue #10 shirt, holding a ball. */
export function FootballerBack({ className = '', number = 10 }: { className?: string; number?: number }) {
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 420 640">
      <defs>
        <linearGradient id="fb-shirt" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2f6bff" />
          <stop offset=".55" stopColor="#1d4ed8" />
          <stop offset="1" stopColor="#13318f" />
        </linearGradient>
        <linearGradient id="fb-skin" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#8a5a3c" />
          <stop offset=".5" stopColor="#b07a52" />
          <stop offset="1" stopColor="#7a4d32" />
        </linearGradient>
        <linearGradient id="fb-shorts" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#14318a" />
          <stop offset="1" stopColor="#0b1f5c" />
        </linearGradient>
        <radialGradient id="fb-ball" cx=".38" cy=".35" r=".7">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#c7d2e0" />
        </radialGradient>
        <linearGradient id="fb-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset=".78" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity=".55" />
        </linearGradient>
        <filter id="fb-rim"><feDropShadow dx="0" dy="0" stdDeviation="6" floodColor="#93c5fd" floodOpacity=".55" /></filter>
      </defs>
      <g filter="url(#fb-rim)">
        {/* legs */}
        <path d="M150 520 L140 640 L195 640 L203 525 Z" fill="url(#fb-skin)" />
        <path d="M217 525 L225 640 L282 640 L272 520 Z" fill="url(#fb-skin)" />
        {/* arms */}
        <path d="M92 210 Q62 300 70 400 Q74 440 92 452 Q112 450 112 420 Q106 330 132 250 Z" fill="url(#fb-skin)" />
        <path d="M330 212 Q362 290 360 360 Q358 390 330 400 L306 392 Q326 330 296 250 Z" fill="url(#fb-skin)" />
        {/* neck + head */}
        <path d="M184 118 L236 118 L240 168 L180 168 Z" fill="#7a4d32" />
        <ellipse cx="210" cy="86" rx="44" ry="52" fill="url(#fb-skin)" />
        <ellipse cx="166" cy="92" rx="8" ry="14" fill="#8a5a3c" />
        <ellipse cx="254" cy="92" rx="8" ry="14" fill="#7a4d32" />
        <path d="M166 82 Q164 30 210 30 Q258 30 254 84 Q246 112 236 122 Q212 110 184 122 Q170 108 166 82 Z" fill="#1a1410" />
        <path d="M176 60 Q210 40 244 60" fill="none" stroke="#3b2c22" strokeWidth="4" strokeLinecap="round" opacity=".7" />
        {/* shirt */}
        <path d="M120 176 Q210 140 300 176 L338 212 L352 290 L308 300 L296 262 L286 420 Q210 436 134 420 L124 262 L112 300 L68 290 L82 212 Z" fill="url(#fb-shirt)" />
        <path d="M178 156 Q210 172 242 156" fill="none" stroke="#0b1f5c" strokeWidth="9" strokeLinecap="round" />
        <path d="M68 290 L112 300" stroke="#0b1f5c" strokeWidth="8" />
        <path d="M308 300 L352 290" stroke="#0b1f5c" strokeWidth="8" />
        <path d="M150 190 Q150 330 140 418" fill="none" stroke="#ffffff" strokeOpacity=".08" strokeWidth="18" />
        <path d="M276 196 Q276 330 284 416" fill="none" stroke="#000" strokeOpacity=".12" strokeWidth="22" />
        <text x="210" y="352" textAnchor="middle" fontFamily="'Barlow Condensed', Impact, sans-serif" fontWeight="800" fontSize="150" fill="#e8f0ff" stroke="#0b1f5c" strokeWidth="3">{number}</text>
        {/* shorts */}
        <path d="M134 416 Q210 432 286 416 L298 528 L216 534 L210 488 L204 534 L122 528 Z" fill="url(#fb-shorts)" />
        <path d="M298 528 L284 420" stroke="#2f6bff" strokeWidth="5" />
        <path d="M122 528 L136 420" stroke="#2f6bff" strokeWidth="5" />
        <path d="M306 380 Q318 440 372 430" fill="none" stroke="#7a4d32" strokeWidth="22" strokeLinecap="round" />
        {/* ball under the right arm */}
        <g transform="translate(338 408)">
          <circle r="54" fill="url(#fb-ball)" />
          <path d="M0 -20 L19 -6 L12 16 L-12 16 L-19 -6 Z" fill="#0f172a" />
          <path d="M0 -20 L0 -46 M19 -6 L44 -16 M12 16 L28 40 M-12 16 L-28 40 M-19 -6 L-44 -16" stroke="#0f172a" strokeWidth="3" />
          <path d="M-40 -34 L-30 -48 L-14 -52 M40 -34 L30 -48 L14 -52 M-52 8 L-46 26 M52 8 L46 26 M-14 52 L14 52" fill="none" stroke="#0f172a" strokeWidth="3" />
        </g>
      </g>
      <rect width="420" height="640" fill="url(#fb-fade)" />
    </svg>
  )
}

/** Small header scenes for the role cards. */
export function RoleArt({ kind, className = '' }: { kind: 'admin' | 'owner' | 'coach' | 'medical' | 'player'; className?: string }) {
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 320 150" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={`ra-bg-${kind}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#0f2a5a" />
          <stop offset="1" stopColor="#163f8c" />
        </linearGradient>
      </defs>
      <rect width="320" height="150" fill={`url(#ra-bg-${kind})`} />
      <circle cx="270" cy="20" r="80" fill="#3b82f6" opacity=".18" />
      {kind === 'admin' && <g>
        <rect x="70" y="30" width="180" height="100" rx="8" fill="#0b1f45" stroke="#60a5fa" strokeOpacity=".5" />
        <rect x="80" y="40" width="34" height="80" rx="4" fill="#132f63" />
        {[0, 1, 2, 3, 4].map((i) => <rect key={i} x="85" y={47 + i * 14} width="24" height="5" rx="2" fill={i === 0 ? '#3b82f6' : '#33507f'} />)}
        {[0, 1, 2].map((i) => <rect key={i} x={122 + i * 41} y="42" width="36" height="20" rx="4" fill="#1d3b73" />)}
        <path d="M124 110 L150 92 L172 100 L200 76 L238 84" fill="none" stroke="#38bdf8" strokeWidth="3" />
        <circle cx="222" cy="104" r="12" fill="none" stroke="#22c55e" strokeWidth="5" strokeDasharray="50 30" />
        <rect x="40" y="130" width="240" height="8" rx="4" fill="#0b1f45" />
      </g>}
      {kind === 'owner' && <g>
        <path d="M130 40 L190 40 L186 82 Q160 104 134 82 Z" fill="#facc15" />
        <path d="M130 48 Q106 50 112 70 Q118 84 134 82 M190 48 Q214 50 208 70 Q202 84 186 82" fill="none" stroke="#facc15" strokeWidth="6" />
        <rect x="150" y="96" width="20" height="16" fill="#eab308" />
        <rect x="132" y="112" width="56" height="12" rx="3" fill="#ca8a04" />
        <path d="M150 54 L160 46 L170 54 L166 68 L154 68 Z" fill="#fde68a" />
        {[60, 250].map((x) => <g key={x}><rect x={x - 18} y="70" width="36" height="54" rx="6" fill="#1d4ed8" /><text x={x} y="106" textAnchor="middle" fontSize="20" fontWeight="800" fill="#fff" fontFamily="'Barlow Condensed', sans-serif">{x === 60 ? 7 : 9}</text></g>)}
      </g>}
      {kind === 'coach' && <g>
        <path d="M0 112 L320 112 L320 150 L0 150 Z" fill="#166534" />
        <path d="M40 150 L120 112 M280 150 L200 112" stroke="#dcfce7" strokeOpacity=".4" strokeWidth="2" />
        <rect x="118" y="26" width="84" height="104" rx="8" fill="#e2e8f0" />
        <rect x="142" y="20" width="36" height="14" rx="4" fill="#64748b" />
        <path d="M134 56 L186 56 M134 72 L186 72 M134 88 L170 88" stroke="#94a3b8" strokeWidth="4" strokeLinecap="round" />
        <circle cx="148" cy="108" r="6" fill="none" stroke="#1d4ed8" strokeWidth="3" />
        <path d="M168 102 L180 114 M180 102 L168 114" stroke="#dc2626" strokeWidth="3" />
        {[60, 84, 250].map((x) => <path key={x} d={`M${x} 124 L${x + 10} 100 L${x + 20} 124 Z`} fill="#f97316" />)}
      </g>}
      {kind === 'medical' && <g>
        <rect x="128" y="34" width="64" height="64" rx="14" fill="#ef4444" />
        <path d="M160 48 L160 84 M142 66 L178 66" stroke="#fff" strokeWidth="10" strokeLinecap="round" />
        <path d="M70 40 Q60 100 110 108 Q150 112 150 126" fill="none" stroke="#cbd5e1" strokeWidth="6" strokeLinecap="round" />
        <circle cx="150" cy="128" r="10" fill="#94a3b8" />
        <path d="M200 110 L220 110 L230 92 L244 128 L254 110 L280 110" fill="none" stroke="#22c55e" strokeWidth="4" strokeLinejoin="round" />
      </g>}
      {kind === 'player' && <g>
        <path d="M0 116 L320 116 L320 150 L0 150 Z" fill="#166534" />
        <path d="M118 40 Q160 26 202 40 L226 58 L214 84 L200 78 L198 130 L122 130 L120 78 L106 84 L94 58 Z" fill="#1d4ed8" />
        <path d="M146 34 Q160 42 174 34" fill="none" stroke="#0b1f5c" strokeWidth="5" />
        <text x="160" y="112" textAnchor="middle" fontSize="54" fontWeight="800" fill="#e8f0ff" fontFamily="'Barlow Condensed', sans-serif">10</text>
        <circle cx="256" cy="120" r="18" fill="#f8fafc" />
        <path d="M256 112 L263 117 L260 126 L252 126 L249 117 Z" fill="#0f172a" />
      </g>}
    </svg>
  )
}

/* ---------- body region map ---------- */
type Zone = { id: string; d: string; match: RegExp }
/** Front-view figure; each zone lights up when the event's body region mentions it. */
const ZONES: Zone[] = [
  { id: 'head', d: 'M60 8 a14 16 0 1 0 0.1 0 Z', match: /head|face|skull|concussion/ },
  { id: 'neck', d: 'M54 38 h12 v9 h-12 Z', match: /neck/ },
  { id: 'lshoulder', d: 'M34 48 q-10 3 -11 15 h12 l4 -15 Z', match: /shoulder/ },
  { id: 'rshoulder', d: 'M86 48 q10 3 11 15 h-12 l-4 -15 Z', match: /shoulder/ },
  { id: 'chest', d: 'M38 48 h44 l-3 34 h-38 Z', match: /chest|rib|torso|upper body/ },
  { id: 'back', d: 'M41 82 h38 l-2 22 h-34 Z', match: /back|spine|abdomen|lumbar|core|stomach/ },
  { id: 'larm', d: 'M23 64 h12 l-5 40 l-8 20 h-7 l3 -22 Z', match: /arm|elbow|wrist|hand/ },
  { id: 'rarm', d: 'M85 64 h12 l5 38 l3 22 h-7 l-8 -20 Z', match: /arm|elbow|wrist|hand/ },
  { id: 'hip', d: 'M43 104 h34 l3 14 h-40 Z', match: /hip|groin|pelvis/ },
  { id: 'lthigh', d: 'M40 118 h19 l-2 40 h-15 Z', match: /thigh|hamstring|quad|upper leg|leg(?!.*lower)/ },
  { id: 'rthigh', d: 'M61 118 h19 l-2 40 h-15 Z', match: /thigh|hamstring|quad|upper leg|leg(?!.*lower)/ },
  { id: 'lknee', d: 'M42 158 h15 v12 h-15 Z', match: /knee/ },
  { id: 'rknee', d: 'M63 158 h15 v12 h-15 Z', match: /knee/ },
  { id: 'lshin', d: 'M43 170 h13 l-1 36 h-11 Z', match: /shin|calf|lower leg|achilles/ },
  { id: 'rshin', d: 'M64 170 h13 l-1 36 h-11 Z', match: /shin|calf|lower leg|achilles/ },
  { id: 'lfoot', d: 'M43 206 h12 l1 12 h-16 Z', match: /ankle|foot|toe|heel/ },
  { id: 'rfoot', d: 'M65 206 h12 l4 12 h-16 Z', match: /ankle|foot|toe|heel/ },
]

const sideOf = (region: string) => (/\bleft\b/.test(region) ? 'l' : /\bright\b/.test(region) ? 'r' : null)

/** Highlights the body region of an event (left/right respected: the figure faces you, so the player's right is on your left). */
export function BodyMap({ region, color = '#ef4444', className = '' }: { region: string | null; color?: string; className?: string }) {
  const r = (region ?? '').toLowerCase()
  const side = sideOf(r)
  const hit = (z: Zone) => {
    if (!r || !z.match.test(r)) return false
    const zs = z.id.startsWith('l') && z.id !== 'lumbar' ? 'l' : z.id.startsWith('r') ? 'r' : null
    // the player's right side is drawn on the viewer's left
    if (side && zs) return (side === 'r' && zs === 'l') || (side === 'l' && zs === 'r')
    return true
  }
  const any = ZONES.some(hit)
  return (
    <svg viewBox="0 0 120 224" className={className} role="img" aria-label={region ? `Body region: ${region}` : 'No body region recorded'}>
      <defs>
        <radialGradient id="bm-hot" cx=".5" cy=".5" r=".6"><stop offset="0" stopColor={color} stopOpacity=".95" /><stop offset="1" stopColor={color} stopOpacity=".35" /></radialGradient>
        <linearGradient id="bm-body" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#dbeafe" /><stop offset="1" stopColor="#bfdbfe" /></linearGradient>
      </defs>
      {ZONES.map((z) => (
        <path key={z.id} d={z.d} fill={hit(z) ? 'url(#bm-hot)' : 'url(#bm-body)'} stroke={hit(z) ? color : '#93c5fd'} strokeWidth="1">
          {hit(z) && <animate attributeName="opacity" values="1;.55;1" dur="1.6s" repeatCount="indefinite" />}
        </path>
      ))}
      {!any && <text x="60" y="222" textAnchor="middle" fontSize="7" fill="#94a3b8">{region ? 'Region not mapped' : 'No region recorded'}</text>}
    </svg>
  )
}
