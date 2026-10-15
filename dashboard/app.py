import os
import shutil
from pathlib import Path

import psutil
import requests
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://jellyfin:8096").rstrip("/")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")
AUDIOBOOKS_PATH = os.getenv("AUDIOBOOKS_PATH_DASH", "/audiobooks")

HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dash · Jellyfin host</title>
<style>
:root{--bg:#0b0e13;--card:#131820;--border:#1f2632;--text:#eaf0f7;--muted:#8b98a9;--accent:#3b82f6}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:radial-gradient(900px 500px at 15% -10%,rgba(59,130,246,.15),transparent 60%),radial-gradient(800px 500px at 90% -10%,rgba(34,197,94,.1),transparent 60%),var(--bg);color:var(--text);min-height:100vh;padding:40px 24px}
main{max-width:960px;margin:0 auto}h1{font-size:30px;font-weight:700;letter-spacing:-.02em}header p{color:var(--muted);margin-top:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;margin-top:32px}
.card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:20px}
.card h3{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:10px}
.big{font-size:28px;font-weight:700}
.sub{color:var(--muted);font-size:13px;margin-top:4px}
.bar{height:8px;background:#1f2632;border-radius:4px;margin-top:10px;overflow:hidden}.fill{height:100%;background:var(--accent);border-radius:4px}
.row{display:flex;justify-content:space-between;align-items:baseline}
footer{margin-top:40px;color:var(--muted);font-size:12px;text-align:center}
</style></head><body><header><h1>Jellyfin Host Dashboard</h1><p>dash.nofiat.me</p></header><main>
<div class="grid" id="g"></div></main><footer id="ts">loading…</footer>
<script>
async function load(){const r=await fetch('/api/stats');const d=await r.json();const g=document.getElementById('g');
function card(title,val,sub,pct){return `<div class="card"><h3>${title}</h3><div class="row"><div class="big">${val}</div></div><div class="sub">${sub}</div>${pct!==null?`<div class="bar"><div class="fill" style="width:${pct}%"></div></div>`:''}</div>`;}
g.innerHTML=
 card('CPU', d.cpu+'%', 'processor load', d.cpu)+
 card('RAM', d.ram_used_gb+' GB', 'of '+d.ram_total_gb+' GB used', d.ram_pct)+
 card('Disk', d.disk_used_gb+' GB', 'of '+d.disk_total_gb+' GB used', d.disk_pct)+
 card('Audiobooks', d.audiobooks_gb+' GB', 'library on disk', null)+
 card('Movies', d.movies, 'in Jellyfin', null)+
 card('Shows', d.shows, 'series in Jellyfin', null)+
 card('Episodes', d.episodes, 'episodes in Jellyfin', null);
document.getElementById('ts').textContent='Updated '+new Date().toLocaleTimeString();
}
load();setInterval(load,10000);
</script></body></html>"""

@app.get("/")
def index():
    return render_template_string(HTML)

@app.get("/api/stats")
def stats():
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    disk_path = "/"
    try:
        du = shutil.disk_usage(disk_path)
    except Exception:
        du = (0, 0, 0)
    audiobooks_bytes = 0
    try:
        root = Path(AUDIOBOOKS_PATH)
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file():
                    try:
                        audiobooks_bytes += p.stat().st_size
                    except OSError:
                        pass
    except Exception:
        pass
    counts = {}
    if JELLYFIN_API_KEY:
        try:
            r = requests.get(f"{JELLYFIN_URL}/Items/Counts",
                             headers={"X-Emby-Token": JELLYFIN_API_KEY}, timeout=5)
            r.raise_for_status()
            counts = r.json()
        except Exception:
            counts = {}
    return jsonify({
        "cpu": round(cpu, 1),
        "ram_used_gb": round(mem.used / 1e9, 2),
        "ram_total_gb": round(mem.total / 1e9, 2),
        "ram_pct": round(mem.percent, 1),
        "disk_used_gb": round(du.used / 1e9, 2),
        "disk_total_gb": round(du.total / 1e9, 2),
        "disk_pct": round(100.0 * du.used / du.total, 1) if du.total else 0,
        "audiobooks_gb": round(audiobooks_bytes / 1e9, 2),
        "movies": counts.get("MovieCount", 0),
        "shows": counts.get("SeriesCount", 0),
        "episodes": counts.get("EpisodeCount", 0),
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("DASHBOARD_PORT", "8080")))
