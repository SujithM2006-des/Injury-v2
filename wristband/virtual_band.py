"""
virtual_band.py - a window that behaves exactly like the AthleteGuard wristband (match mode).
Asks the backend every 2 seconds for the level in the current match and shows it:
Blue = no falls, Green = low, Amber = medium, Red blinking = high,
Purple blinking = backend not reachable.
Below the light: the match, and WHO fell (name, jersey, team, falls), worst first.
Run (with the backend running):  python virtual_band.py
"""
import json
import tkinter as tk
import urllib.request

SERVER = "http://127.0.0.1:8000"
PLAYER_ID = 0                       # 0 = any player (team doctor's band), or a roster player id
BAND_KEY = "athleteguard-band-key"  # must match the backend
MAX_PLAYERS = 6                     # how many players to list under the light

COLORS = {"HIGH": "#e11d48", "MEDIUM": "#f59e0b", "LOW": "#16a34a", "NONE": "#2563eb"}
DOTS = {"HIGH": "#fb7185", "MEDIUM": "#fbbf24", "LOW": "#4ade80", "NONE": "#60a5fa"}
LABELS = {"HIGH": "HIGH risk - check the player", "MEDIUM": "Medium risk", "LOW": "Low risk",
          "NONE": "No falls this match", "ERROR": "Backend not reachable", "WAIT": "Connecting..."}
BG = "#0f172a"

root = tk.Tk()
root.title("AthleteGuard band (virtual)")
root.geometry("420x560")
root.configure(bg=BG)
canvas = tk.Canvas(root, width=420, height=200, bg=BG, highlightthickness=0)
canvas.pack()
dot = canvas.create_oval(150, 30, 270, 150, fill="#334155", outline="")
label = tk.Label(root, text="Connecting...", font=("Segoe UI", 14, "bold"), bg=BG, fg="white")
label.pack()
who = tk.Label(root, text="", font=("Segoe UI", 18, "bold"), bg=BG, fg="white", wraplength=400)
who.pack(pady=(6, 0))
match_label = tk.Label(root, text="", font=("Segoe UI", 10), bg=BG, fg="#94a3b8")
match_label.pack(pady=(4, 10))
players_frame = tk.Frame(root, bg=BG)
players_frame.pack(fill="x", padx=18)

state = {"level": "WAIT", "info": {}, "blink": False}


def player_title(p):
    jersey = f"#{p['jersey_number']} " if p.get("jersey_number") is not None else ""
    team = f" ({p['team']})" if p.get("team") else ""
    return f"{jersey}{p.get('name') or 'Unidentified player'}{team}"


def fall_text(p):
    parts = []
    for k, name in (("high", "high"), ("medium", "medium"), ("low", "low")):
        if p.get(k):
            parts.append(f"{p[k]} {name}")
    return f"{p.get('falls', 0)} fall{'s' if p.get('falls', 0) != 1 else ''}: " + ", ".join(parts)


def show_players(players):
    for w in players_frame.winfo_children():
        w.destroy()
    for p in players[:MAX_PLAYERS]:
        row = tk.Frame(players_frame, bg=BG)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="●", font=("Segoe UI", 14), bg=BG, fg=DOTS.get(p.get("level"), "#94a3b8")).pack(side="left")
        tk.Label(row, text=player_title(p), font=("Segoe UI", 11, "bold"), bg=BG, fg="white").pack(side="left", padx=6)
        tk.Label(row, text=fall_text(p), font=("Segoe UI", 10), bg=BG, fg="#94a3b8").pack(side="right")
    if len(players) > MAX_PLAYERS:
        tk.Label(players_frame, text=f"+ {len(players) - MAX_PLAYERS} more player(s)", font=("Segoe UI", 10),
                 bg=BG, fg="#94a3b8").pack(anchor="w", pady=3)


def poll():
    url = f"{SERVER}/band/{PLAYER_ID}/summary?key={BAND_KEY}"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            info = json.loads(r.read().decode())
        state["info"] = info
        state["level"] = str(info.get("level", "NONE")).upper()
    except Exception:
        state["level"] = "ERROR"
        state["info"] = {}
    i = state["info"]
    players = i.get("players") or []
    top = player_title(players[0]) if players else "-"
    print("Band ->", state["level"], "| falls:", i.get("falls", "-"), "| worst:", top, "| match:", i.get("match_name") or "-")
    show_players(players)
    root.after(2000, poll)


def draw():
    state["blink"] = not state["blink"]
    lv = state["level"]
    if lv == "HIGH":
        color = COLORS["HIGH"] if state["blink"] else "#334155"
    elif lv in COLORS:
        color = COLORS[lv]
    else:
        color = "#9333ea" if state["blink"] else "#334155"
    canvas.itemconfig(dot, fill=color)
    label.config(text=LABELS.get(lv, lv))
    i = state["info"]
    players = i.get("players") or []
    who.config(text=player_title(players[0]) if players and lv in ("HIGH", "MEDIUM", "LOW") else "")
    if i:
        match = i.get("match_name") or ("Match #" + str(i["match_id"]) if i.get("match_id") else "No match")
        status = {"running": "live", "finished": "finished", "over": "over"}.get(i.get("match_state"), "")
        match_label.config(text=f"{match} ({status})  ·  {i.get('falls', 0)} falls in total")
    else:
        match_label.config(text="")
    root.after(300, draw)


poll()
draw()
root.mainloop()