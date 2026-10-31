"""
band_tester.py - buttons to set the AthleteGuard band colour by hand, to check the band works.
HIGH / MEDIUM / LOW / NONE force that level on every band; AUTO gives the real level back.
Uses POST /band/force on the backend. Nothing is saved: the backend forgets it on restart.
Run (with the backend running):  python band_tester.py
"""
import json
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request

SERVER = "http://127.0.0.1:8000"
PLAYER_ID = 0                       # the band to read back (0 = team doctor's band)
BAND_KEY = "athleteguard-band-key"  # must match the backend
MINUTES = 30                        # how long a forced colour stays

COLORS = {"HIGH": "#e11d48", "MEDIUM": "#f59e0b", "LOW": "#16a34a", "NONE": "#2563eb", "AUTO": "#475569"}
BG = "#0f172a"

root = tk.Tk()
root.title("AthleteGuard band tester")
root.geometry("360x330")
root.configure(bg=BG)
tk.Label(root, text="Set the band colour", font=("Segoe UI", 14, "bold"), bg=BG, fg="white").pack(pady=(14, 8))
buttons = tk.Frame(root, bg=BG)
buttons.pack()
now_label = tk.Label(root, text="Band now: ...", font=("Segoe UI", 13, "bold"), bg=BG, fg="white")
now_label.pack(pady=(14, 2))
msg = tk.Label(root, text="", font=("Segoe UI", 10), bg=BG, fg="#94a3b8", wraplength=330)
msg.pack()


def call(path, method="GET", **params):
    url = f"{SERVER}{path}?" + urllib.parse.urlencode({"key": BAND_KEY, **params})
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=3) as r:
        return r.read().decode()


def force(level):
    try:
        info = json.loads(call("/band/force", "POST", level=level, minutes=MINUTES))
        msg.config(text=f"Forced {level} for {MINUTES} min" if info.get("forced") else "Back to the real level")
    except urllib.error.HTTPError as e:
        msg.config(text="Wrong band key" if e.code == 403 else
                   "Backend has no /band/force - restart it" if e.code in (404, 405) else f"Error {e.code}")
    except Exception:
        msg.config(text="Backend not reachable")
    read_back()


def read_back():
    try:
        level = call(f"/band/{PLAYER_ID}/status").strip().strip('"')
        now_label.config(text=f"Band now: {level}", fg=COLORS.get(level, "white"))
    except Exception:
        now_label.config(text="Band now: backend not reachable", fg="#9333ea")


for i, lv in enumerate(("HIGH", "MEDIUM", "LOW", "NONE", "AUTO")):
    tk.Button(buttons, text=lv, width=10, font=("Segoe UI", 11, "bold"), fg="white", bg=COLORS[lv],
              activebackground=COLORS[lv], relief="flat", command=lambda lv=lv: force(lv)
              ).grid(row=i // 2, column=i % 2, padx=6, pady=5)


def poll():
    read_back()
    root.after(2000, poll)


poll()
root.mainloop()
