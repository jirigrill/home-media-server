import os
import shutil
from pathlib import Path

import psutil
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard · Jellyfin host</title>
<style>
:root { --bg:#0b0e13; --card:#131820; --border:#1f2632; --text:#eaf0f7; --muted:#8b98a9; --accent:#3b82f6; --bar:#1f2632; }
[data-theme="light"] { --bg:#f5f7fa; --card:#ffffff; --border:#dfe3ea; --text:#1a1f2b; --muted:#5b6678; --accent:#2563eb; --bar:#e5e9f0; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; background:var(--bg); color:var(--text); min-height:100vh; padding:40px 24px; transition:background .2s,color .2s; }
main { max-width:1080px; margin:0 auto; }
header { display:flex; justify-content:space-between; align-items:center; }
header h1 { font-size:30px; font-weight:700; letter-spacing:-.02em; }
header p { color:var(--muted); margin-top:6px; }
.toggle { background:var(--card); border:1px solid var(--border); color:var(--text); border-radius:10px; padding:8px 12px; cursor:pointer; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px; margin-top:32px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:16px; padding:20px; }
.card h3 { font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--muted); margin-bottom:10px; }
.big { font-size:24px; font-weight:700; }
.sub { color:var(--muted); font-size:13px; margin-top:4px; }
.bar { height:8px; background:var(--bar); border-radius:4px; margin-top:10px; overflow:hidden; }
.fill { height:100%; background:var(--accent); border-radius:4px; }
.row { display:flex; justify-content:space-between; align-items:baseline; }
footer { margin-top:40px; color:var(--muted); font-size:12px; text-align:center; }
</style>
</head>
<body>
<header>
  <div><h1>Host Dashboard</h1><p>Server & connected storage</p></div>
  <button class="toggle" onclick="toggleTheme()">Light/Dark</button>
</header>
<main>
  <div class="grid" id="server"></div>
  <div class="grid" id="connected" style="margin-top:24px"></div>
</main>
<footer id="ts">loading…</footer>
<script>
const saved=localStorage.getItem('theme')||'dark';
document.documentElement.setAttribute('data-theme', saved);
function toggleTheme(){const t=document.documentElement.getAttribute('data-theme')==='dark'?'light':'dark';document.documentElement.setAttribute('data-theme',t);localStorage.setItem('theme',t);}
function card(title,val,sub,pct){return `<div class="card"><h3>${title}</h3><div class="row"><div class="big">${val}</div></div><div class="sub">${sub}</div>${pct!==null?`<div class="bar"><div class="fill" style="width:${pct}%"></div></div>`:''}</div>`;}
async function load(){const r=await fetch('/api/stats');const d=await r.json();
let s='';
s+=card('CPU', d.cpu+'%', 'server load', d.cpu);
s+=card('RAM', d.ram_used_gb+' GB', 'of '+d.ram_total_gb+' GB', d.ram_pct);
s+=card('Server disk', d.server_disk_used_gb+' GB', 'of '+d.server_disk_total_gb+' GB free '+d.server_disk_free_gb, d.server_disk_pct);
s+=card('Audiobooks', d.audiobooks_gb+' GB', 'used space', null);
document.getElementById('server').innerHTML=s;
let c='';
for(const [k,v] of Object.entries(d.connected)){c+=card(k, v.used_gb+' GB', 'of '+v.total_gb+' GB (free '+v.free_gb+')', v.pct);}
document.getElementById('connected').innerHTML=c;
document.getElementById('ts').textContent='Updated '+new Date().toLocaleTimeString();
}
load();setInterval(load,10000);
</script>
</body>
</html>
"""

MOUNTS = {
    "Movies": "/movies",
    "Shows": "/shows",
    "Kids shows": "/kids_shows",
    "Kids movies": "/kids_movies",
}

@app.get("/")
def index():
    return render_template_string(HTML)

def folder_size_gb(path):
    total = 0
    root = Path(path)
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    return round(total / 1e9, 2)

@app.get("/api/stats")
def stats():
    cpu = psutil.cpu_percent(interval=0.3)
    mem = psutil.virtual_memory()
    su = shutil.disk_usage("/")
    connected = {}
    for name, path in MOUNTS.items():
        try:
            du = shutil.disk_usage(path)
            connected[name] = {
                "used_gb": round(du.used / 1e9, 2),
                "total_gb": round(du.total / 1e9, 2),
                "free_gb": round(du.free / 1e9, 2),
                "pct": round(100.0 * du.used / du.total, 1) if du.total else 0,
            }
        except OSError:
            connected[name] = {"used_gb": 0, "total_gb": 0, "free_gb": 0, "pct": 0}
    return jsonify({
        "cpu": round(cpu, 1),
        "ram_used_gb": round(mem.used / 1e9, 2),
        "ram_total_gb": round(mem.total / 1e9, 2),
        "ram_pct": round(mem.percent, 1),
        "server_disk_used_gb": round(su.used / 1e9, 2),
        "server_disk_total_gb": round(su.total / 1e9, 2),
        "server_disk_free_gb": round(su.free / 1e9, 2),
        "server_disk_pct": round(100.0 * su.used / su.total, 1) if su.total else 0,
        "connected": connected,
        "audiobooks_gb": folder_size_gb("/audiobooks"),
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("DASHBOARD_PORT", "8080")))
