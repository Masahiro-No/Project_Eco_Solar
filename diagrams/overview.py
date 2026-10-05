"""Draws diagrams/overview.png: data flow of SolarDSS and its Public / Private zones.

    python diagrams/overview.py          (needs matplotlib)

Keep this file and the picture in step: change the system, change the boxes here, run it again.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

plt.rcParams["font.family"] = ["Segoe UI", "Tahoma", "DejaVu Sans"]
fig, ax = plt.subplots(figsize=(11.0, 6.7), dpi=200)
ax.set_xlim(0, 120)
ax.set_ylim(0, 73)
ax.axis("off")

# zone styles: fill, edge, line style
EXT = dict(fc="#ffffff", ec="#64748b", ls=(0, (4, 2)))   # external data source
PUB = dict(fc="#dcfce7", ec="#15803d", ls="-")           # public: logged-in operator
ADM = dict(fc="#ffedd5", ec="#c2410c", ls="-")           # private: admin only
DEV = dict(fc="#dbeafe", ec="#1d4ed8", ls="-")           # private: server only (127.0.0.1)
INN = dict(fc="#ffffff", ec="#1d4ed8", ls="-")           # step inside a worker
INK = "#334155"
TITLE = "#0f172a"


def box(x, y, w, h, title, sub="", st=DEV, fs=8.4, sfs=6.7):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.0",
                                fc=st["fc"], ec=st["ec"], lw=1.1, ls=st["ls"], zorder=2))
    ax.text(x + w / 2, y + h - 0.9, title, ha="center", va="top", fontsize=fs, fontweight="bold", color=TITLE, zorder=3)
    ax.text(x + w / 2, y + (h - 3.2) / 2, sub, ha="center", va="center", fontsize=sfs, color=INK, zorder=3, linespacing=1.18)


def group(x, y, w, h, fc, ec):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.0", fc=fc, ec=ec, lw=1.1, zorder=1))


def arrow(p, q, style="-|>", color=INK):
    ax.annotate("", xy=q, xytext=p, zorder=4,
                arrowprops=dict(arrowstyle=style, color=color, lw=1.15, shrinkA=0, shrinkB=0, mutation_scale=9))


def note(x, y, text, ha="center", va="center"):
    ax.text(x, y, text, ha=ha, va=va, fontsize=6.5, color=INK, style="italic", zorder=5, linespacing=1.12)


# ---------------------------------------------------------------- row 1: every 10 minutes
box(1, 61.5, 17, 8.5, "Open-Meteo API", "weather, 10-minute steps", EXT)
box(1, 50.5, 17, 8.5, "NICT Himawari", "Band 03 frame\nevery 10 minutes", EXT)
box(23, 53, 17, 14.5, "Ingestion Worker", "every 10 minutes:\nfetch, fill gaps,\nqueue one forecast\nper station")

group(44.5, 40.5, 20, 31, "#f8fafc", "#94a3b8")
box(46, 61.5, 17, 8.5, "PostgreSQL", "weather, forecasts,\nusers, frame reviews")
box(46, 51.5, 17, 8.5, "MinIO", "satellite frames,\nmodel files")
box(46, 42, 17, 8, "Redis", "job queues (ARQ)")

group(70, 45.5, 49, 26, "#eff6ff", "#1d4ed8")
ax.text(94.5, 70.6, "Inference Worker", ha="center", va="top", fontsize=8.4, fontweight="bold", color=TITLE)
note(94.5, 67.6, "one job per station from inference_queue, no click needed", va="top")
box(71.5, 56.2, 14, 8.6, "LSTM", "GHI for 18 steps (3 h)\nfrom 36 slots (6 h)", INN, fs=7.9, sfs=6.2)
box(71.5, 46.6, 14, 8.6, "ConvLSTM", "12 real frames → 18;\nlight in 5×5 px AOI", INN, fs=7.9, sfs=6.2)
box(89, 51.2, 13.5, 9, "Blend", "satellite weight\nw(t) = 0.9·exp(−t/102)", INN, fs=7.9, sfs=6.1)
box(105.5, 51.2, 12.5, 9, "Decision", "P_gen vs target,\nΔP, alert level", INN, fs=7.9, sfs=6.2)

arrow((18, 65.5), (23, 62.5))
arrow((18, 55), (23, 58))
arrow((40, 63.5), (46, 65.5))
arrow((40, 60), (46, 56))
arrow((40, 56.5), (46, 47.5))
arrow((63, 46.5), (70, 49.5))
note(66.3, 46.3, "jobs", va="top")
arrow((63, 56), (70, 56), style="<|-|>")
note(66.5, 57.0, "frames,\nmodels", va="bottom")
arrow((70, 65.5), (63, 65.5))
note(66.5, 66.4, "forecasts", va="bottom")
arrow((85.5, 60), (89, 57.2))
arrow((85.5, 51.4), (89, 54.2))
arrow((102.5, 55.7), (105.5, 55.7))

# ---------------------------------------------------------------- row 2: people
box(46, 25, 17, 9.5, "FastAPI  :8000", "JWT login,\nrole check on every call", PUB)
box(20, 25, 20, 9.5, "Web app  :3000", "dashboard, forecast, decision,\nalerts, stations, help", PUB)
box(70, 25, 23, 9.5, "Web app: admin pages", "measured GHI (file or typed),\nsatellite frame review, station setup", ADM, sfs=6.4)
arrow((54.5, 34.5), (54.5, 40.5), style="<|-|>")
note(56.0, 37.5, "read / write,\nqueue retrain", ha="left")
arrow((46, 29.75), (40, 29.75))
arrow((70, 29.75), (63, 29.75))
ax.text(8.5, 29.75, "Operator", ha="center", va="center", fontsize=7.9, color="#15803d", fontweight="bold")
arrow((14, 29.75), (20, 29.75), color="#15803d")
ax.text(103, 29.75, "Admin", ha="center", va="center", fontsize=7.9, color="#c2410c", fontweight="bold")
arrow((99, 29.75), (93, 29.75), color="#c2410c")

# ---------------------------------------------------------------- row 3: learning loop and operations
box(46, 4, 17, 9.5, "Label Studio", "measured GHI\nkept as labels")
box(68, 3, 28, 11.5, "Trainer Worker",
    "LSTM: fine-tune on measured GHI labels\nConvLSTM: retrain per 50 new real scans\ndeploy only if better on held-out data", sfs=6.4)
box(101.5, 3, 16.5, 8, "MLflow", "runs, metrics")
box(1, 3, 39, 9.5, "Observability", "OpenTelemetry → Prometheus, Loki, Tempo → Grafana")

arrow((54.5, 25), (54.5, 13.5))
note(56.0, 19.3, "GHI labels", ha="left")
arrow((63, 8.75), (68, 8.75))
note(80, 19.3, "retrain jobs arrive on train_queue")
arrow((96, 6.5), (101.5, 6.5))
ax.plot([96, 110, 110], [12.8, 12.8, 44.3], color=INK, lw=1.15, zorder=4, solid_capstyle="butt")
arrow((110, 44.2), (110, 45.5))
note(108.8, 19.3, "accepted model\n→ model/ and MinIO", ha="right")

# ---------------------------------------------------------------- legend
for i, (st, label) in enumerate([
    (EXT, "External data source"),
    (PUB, "Public zone: logged-in operator"),
    (ADM, "Private zone: admin only"),
    (DEV, "Private zone: server only (127.0.0.1)"),
]):
    y = 21.6 - i * 2.25
    ax.add_patch(FancyBboxPatch((1, y - 0.75), 2.8, 1.5, boxstyle="round,pad=0,rounding_size=0.35",
                                fc=st["fc"], ec=st["ec"], lw=1.0, ls=st["ls"], zorder=2))
    ax.text(5, y, label, ha="left", va="center", fontsize=6.9, color=INK)

fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
out = Path(__file__).with_name("overview.png")
fig.savefig(out, facecolor="white")
print(out)
