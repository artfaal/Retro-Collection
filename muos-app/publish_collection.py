#!/usr/bin/env python3
"""Build and publish HTML collection page from playtime data and box art."""

import json
import os
import hashlib
import shutil
import subprocess
from pathlib import Path

# Paths on muOS console
SCRIPT_DIR = Path(__file__).parent
CATALOGUE_DIR = Path("/mnt/sdcard/MUOS/info/catalogue")
PLAYTIME_FILE = Path("/mnt/sdcard/MUOS/info/track/playtime_data.json")
OUTPUT_DIR = Path("/tmp/retro_publish")
OUTPUT_FILE = OUTPUT_DIR / "index.html"
COVERS_DIR = OUTPUT_DIR / "covers"
SSH_KEY = SCRIPT_DIR / "retro_publish_key"
REMOTE_HOST = "orion.artfaal.ru"
REMOTE_PORT = "22124"
REMOTE_USER = "artfaal"
REMOTE_BASE = "/var/docker/compose/retro/html"
PUBLISH_URL = "https://retro.artfaal.ru"

SYSTEM_MAP = {
    "Ports": "External - Ports",
    "Symbian": "Java J2ME",
}

SYSTEM_COLORS = {
    "Nintendo NES - Famicom": "#c4272e",
    "Nintendo SNES - SFC": "#7b5ea7",
    "Nintendo Game Boy": "#2f6b3a",
    "Nintendo Game Boy Color": "#5b3a8c",
    "Nintendo Game Boy Advance": "#354fa0",
    "Nintendo DS": "#999999",
    "Nintendo N64": "#009e42",
    "Sega Mega Drive - Genesis": "#1a6eb5",
    "Sega Pico": "#1a6eb5",
    "Sony PlayStation": "#003087",
    "Sony PlayStation Portable": "#003087",
    "External - Ports": "#e07020",
    "Java J2ME": "#5382a1",
}

SYSTEM_SHORT = {
    "Nintendo NES - Famicom": "NES",
    "Nintendo SNES - SFC": "SNES",
    "Nintendo Game Boy": "Game Boy",
    "Nintendo Game Boy Color": "GBC",
    "Nintendo Game Boy Advance": "GBA",
    "Nintendo DS": "NDS",
    "Nintendo N64": "N64",
    "Sega Mega Drive - Genesis": "Genesis",
    "Sega Pico": "Pico-8",
    "Sony PlayStation": "PS1",
    "Sony PlayStation Portable": "PSP",
    "External - Ports": "Ports",
    "Java J2ME": "J2ME",
}


def format_time(seconds):
    if seconds < 60:
        return f"{seconds}s"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def format_time_full(seconds):
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours} hr {mins} min"
    return f"{mins} min"


def safe_filename(name):
    """Create a safe filename from game name."""
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
    return f"{safe[:50]}_{h}.png"


def parse_games(data):
    games = []
    seen = {}

    for key, val in data.items():
        parts = key.split("/ROMS/")
        if len(parts) < 2:
            continue

        rest = parts[1]
        system = rest.split("/")[0]
        game_file = rest.split("/")[-1]
        game_name = os.path.splitext(game_file)[0]
        cat_system = SYSTEM_MAP.get(system, system)

        dedup_key = f"{cat_system}::{val['name']}"
        if dedup_key in seen:
            existing = seen[dedup_key]
            existing["total_time"] += val["total_time"]
            existing["launches"] += val["launches"]
            if val.get("start_time", 0) > existing.get("start_time", 0):
                existing["start_time"] = val.get("start_time", 0)
                existing["last_session"] = val.get("last_session", 0)
            for dev, cnt in val.get("device_launches", {}).items():
                existing["device_launches"][dev] = (
                    existing["device_launches"].get(dev, 0) + cnt
                )
            existing["avg_time"] = (
                existing["total_time"] / existing["launches"]
                if existing["launches"]
                else 0
            )
            continue

        # Look for box art in catalogue
        box_path = CATALOGUE_DIR / cat_system / "box" / f"{game_name}.png"
        cover_file = None
        if box_path.exists():
            cover_file = safe_filename(val["name"])
            try:
                shutil.copy(box_path, COVERS_DIR / cover_file)
            except Exception:
                cover_file = None

        game = {
            "name": val["name"],
            "system": cat_system,
            "system_short": SYSTEM_SHORT.get(cat_system, cat_system),
            "system_color": SYSTEM_COLORS.get(cat_system, "#666"),
            "total_time": val["total_time"],
            "launches": val["launches"],
            "avg_time": val.get("avg_time", 0),
            "last_session": val.get("last_session", 0),
            "start_time": val.get("start_time", 0),
            "device_launches": val.get("device_launches", {}),
            "cover_file": cover_file,
        }
        games.append(game)
        seen[dedup_key] = game

    games.sort(key=lambda g: -g["total_time"])
    return games


def build_html(games):
    from collections import defaultdict

    total_time = sum(g["total_time"] for g in games)
    total_launches = sum(g["launches"] for g in games)
    total_games = len(games)

    systems = defaultdict(int)
    for g in games:
        systems[g["system"]] += g["total_time"]
    top_system = max(systems, key=systems.get) if systems else "N/A"
    top_system_short = SYSTEM_SHORT.get(top_system, top_system)

    # Find "Now Playing" - game with most recent session
    now_playing = max(games, key=lambda g: g.get("start_time", 0)) if games else None

    # Now Playing section
    now_playing_html = ""
    if now_playing and now_playing.get("start_time", 0) > 0:
        g = now_playing
        if g["cover_file"]:
            img = f'<img src="covers/{g["cover_file"]}" alt="{g["name"]}" />'
        else:
            img = f'<div class="no-art"><span>{g["name"][0]}</span></div>'

        time_str = format_time(g["total_time"])
        now_playing_html = f"""
    <div class="now-playing">
        <div class="now-playing-label">Now Playing</div>
        <div class="now-playing-card">
            <div class="now-playing-art">{img}</div>
            <div class="now-playing-info">
                <div class="now-playing-name">{g['name']}</div>
                <span class="system-badge" style="background:{g['system_color']}">{g['system_short']}</span>
                <div class="now-playing-time">{time_str} played</div>
            </div>
        </div>
    </div>"""

    cards_html = ""
    for i, g in enumerate(games):
        if g["cover_file"]:
            img = f'<img src="covers/{g["cover_file"]}" alt="{g["name"]}" loading="lazy" />'
        else:
            img = f'<div class="no-art"><span>{g["name"][0]}</span></div>'

        devices = ""
        for dev, cnt in g["device_launches"].items():
            dev_short = dev.replace("rg40xx-v", "RG40").replace("rg35xx-pro", "RG30").replace("rg34xx-sp", "RG34")
            devices += f'<span class="device-tag">{dev_short}: {cnt}</span>'

        time_str = format_time(g["total_time"])
        avg_str = format_time(int(g["avg_time"]))

        cards_html += f"""
        <div class="game-card" data-system="{g['system']}" data-time="{g['total_time']}">
            <div class="card-art">{img}</div>
            <div class="card-info">
                <div class="card-name" title="{g['name']}">{g['name']}</div>
                <span class="system-badge" style="background:{g['system_color']}">{g['system_short']}</span>
                <div class="card-stats">
                    <div class="stat">
                        <span class="stat-val">{time_str}</span>
                        <span class="stat-label">played</span>
                    </div>
                    <div class="stat">
                        <span class="stat-val">{g['launches']}</span>
                        <span class="stat-label">runs</span>
                    </div>
                    <div class="stat">
                        <span class="stat-val">{avg_str}</span>
                        <span class="stat-label">avg</span>
                    </div>
                </div>
                <div class="card-devices">{devices}</div>
            </div>
        </div>"""

    sys_buttons = '<button class="filter-btn active" data-filter="all">All</button>'
    for sys_name in sorted(systems, key=lambda s: -systems[s]):
        short = SYSTEM_SHORT.get(sys_name, sys_name)
        color = SYSTEM_COLORS.get(sys_name, "#666")
        count = len([g for g in games if g["system"] == sys_name])
        sys_buttons += f'<button class="filter-btn" data-filter="{sys_name}" style="--btn-color:{color}">{short} ({count})</button>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Game Collection</title>
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
        font-family: 'Inter', -apple-system, sans-serif;
        background: #0f0f13;
        color: #e0e0e0;
        min-height: 100vh;
    }}

    .hero {{
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 48px 32px 40px;
        text-align: center;
        border-bottom: 1px solid rgba(255,255,255,0.06);
    }}

    .hero h1 {{
        font-size: 2.2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #e2e8f0, #94a3b8);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 28px;
        letter-spacing: -0.5px;
    }}

    .stats-row {{
        display: flex;
        justify-content: center;
        gap: 48px;
        flex-wrap: wrap;
    }}

    .hero-stat {{
        text-align: center;
    }}

    .hero-stat .val {{
        font-size: 2rem;
        font-weight: 700;
        color: #fff;
        line-height: 1.2;
    }}

    .hero-stat .label {{
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        color: #64748b;
        margin-top: 4px;
    }}

    .now-playing {{
        max-width: 600px;
        margin: 0 auto;
        padding: 32px;
    }}

    .now-playing-label {{
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 2px;
        color: #10b981;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }}

    .now-playing-label::before {{
        content: '';
        width: 8px;
        height: 8px;
        background: #10b981;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }}

    @keyframes pulse {{
        0%, 100% {{ opacity: 1; }}
        50% {{ opacity: 0.5; }}
    }}

    .now-playing-card {{
        display: flex;
        gap: 20px;
        background: linear-gradient(135deg, #1a2e1a 0%, #162e16 100%);
        border: 1px solid rgba(16, 185, 129, 0.2);
        border-radius: 16px;
        padding: 16px;
        align-items: center;
    }}

    .now-playing-art {{
        width: 100px;
        height: 100px;
        border-radius: 8px;
        overflow: hidden;
        flex-shrink: 0;
        background: #12131a;
    }}

    .now-playing-art img {{
        width: 100%;
        height: 100%;
        object-fit: contain;
    }}

    .now-playing-info {{
        flex: 1;
    }}

    .now-playing-name {{
        font-size: 1.1rem;
        font-weight: 700;
        color: #f1f5f9;
        margin-bottom: 8px;
    }}

    .now-playing-time {{
        font-size: 0.85rem;
        color: #94a3b8;
        margin-top: 8px;
    }}

    .controls {{
        padding: 20px 32px;
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
        position: sticky;
        top: 0;
        background: rgba(15, 15, 19, 0.95);
        backdrop-filter: blur(12px);
        z-index: 100;
        border-bottom: 1px solid rgba(255,255,255,0.04);
    }}

    .filter-btn {{
        padding: 6px 14px;
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 20px;
        background: transparent;
        color: #94a3b8;
        font-size: 0.8rem;
        font-family: inherit;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
    }}

    .filter-btn:hover {{
        border-color: rgba(255,255,255,0.25);
        color: #e2e8f0;
    }}

    .filter-btn.active {{
        background: var(--btn-color, #3b82f6);
        border-color: var(--btn-color, #3b82f6);
        color: #fff;
    }}

    .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 16px;
        padding: 24px 32px 48px;
        max-width: 1400px;
        margin: 0 auto;
    }}

    .game-card {{
        background: #1a1b23;
        border-radius: 12px;
        overflow: hidden;
        transition: transform 0.2s, box-shadow 0.2s;
        border: 1px solid rgba(255,255,255,0.04);
    }}

    .game-card:hover {{
        transform: translateY(-4px);
        box-shadow: 0 12px 32px rgba(0,0,0,0.4);
        border-color: rgba(255,255,255,0.1);
    }}

    .game-card.hidden {{
        display: none;
    }}

    .card-art {{
        width: 100%;
        aspect-ratio: 1;
        overflow: hidden;
        background: #12131a;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    .card-art img {{
        width: 100%;
        height: 100%;
        object-fit: contain;
        transition: transform 0.3s;
    }}

    .game-card:hover .card-art img {{
        transform: scale(1.05);
    }}

    .no-art {{
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: linear-gradient(135deg, #1e293b, #0f172a);
    }}

    .no-art span {{
        font-size: 3rem;
        font-weight: 800;
        color: #334155;
    }}

    .card-info {{
        padding: 14px 16px 16px;
    }}

    .card-name {{
        font-size: 0.9rem;
        font-weight: 600;
        color: #f1f5f9;
        margin-bottom: 8px;
        line-height: 1.3;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
    }}

    .system-badge {{
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 600;
        color: #fff;
        margin-bottom: 10px;
    }}

    .card-stats {{
        display: flex;
        gap: 16px;
        margin-bottom: 8px;
    }}

    .stat {{
        display: flex;
        flex-direction: column;
    }}

    .stat-val {{
        font-size: 0.9rem;
        font-weight: 700;
        color: #e2e8f0;
    }}

    .stat-label {{
        font-size: 0.65rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #475569;
    }}

    .card-devices {{
        display: flex;
        gap: 6px;
        flex-wrap: wrap;
    }}

    .device-tag {{
        font-size: 0.65rem;
        padding: 2px 8px;
        border-radius: 8px;
        background: rgba(255,255,255,0.05);
        color: #64748b;
        font-weight: 500;
    }}

    @media (max-width: 640px) {{
        .hero {{ padding: 32px 16px; }}
        .hero h1 {{ font-size: 1.6rem; }}
        .stats-row {{ gap: 24px; }}
        .now-playing {{ padding: 24px 16px; }}
        .now-playing-card {{ flex-direction: column; text-align: center; }}
        .now-playing-art {{ width: 120px; height: 120px; margin: 0 auto; }}
        .grid {{ padding: 16px; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); }}
        .card-name {{ font-size: 0.8rem; }}
    }}
</style>
</head>
<body>
    <div class="hero">
        <h1>Game Collection</h1>
        <div class="stats-row">
            <div class="hero-stat">
                <div class="val">{total_games}</div>
                <div class="label">Games Played</div>
            </div>
            <div class="hero-stat">
                <div class="val">{format_time_full(total_time)}</div>
                <div class="label">Total Playtime</div>
            </div>
            <div class="hero-stat">
                <div class="val">{total_launches}</div>
                <div class="label">Total Launches</div>
            </div>
            <div class="hero-stat">
                <div class="val">{top_system_short}</div>
                <div class="label">Most Played System</div>
            </div>
        </div>
    </div>
    {now_playing_html}
    <div class="controls">
        {sys_buttons}
    </div>

    <div class="grid">
        {cards_html}
    </div>

    <script>
        document.querySelectorAll('.filter-btn').forEach(btn => {{
            btn.addEventListener('click', () => {{
                document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const filter = btn.dataset.filter;
                document.querySelectorAll('.game-card').forEach(card => {{
                    if (filter === 'all' || card.dataset.system === filter) {{
                        card.classList.remove('hidden');
                    }} else {{
                        card.classList.add('hidden');
                    }}
                }});
            }});
        }});
    </script>
</body>
</html>"""
    return html


def publish():
    # Copy key to /tmp with proper permissions (SD card is FAT32, no chmod)
    tmp_key = Path("/tmp/retro_publish_key")
    shutil.copy(SSH_KEY, tmp_key)
    os.chmod(tmp_key, 0o600)

    print(f"Publishing to {REMOTE_HOST}...")

    # Use rsync for efficient sync (only uploads changed files)
    rsync_cmd = [
        "rsync", "-avz", "--checksum",
        "-e", f"/opt/openssh/bin/ssh -i {tmp_key} -p {REMOTE_PORT} -o StrictHostKeyChecking=no",
        f"{OUTPUT_DIR}/",
        f"{REMOTE_USER}@{REMOTE_HOST}:{REMOTE_BASE}/"
    ]

    result = subprocess.run(rsync_cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Publish failed: {result.stderr.strip()}")
        return False

    # Show rsync stats
    for line in result.stdout.strip().split('\n'):
        if line and not line.startswith('sending') and not line.startswith('created'):
            print(line)

    print(f"Published! View at {PUBLISH_URL}")
    return True


def main():
    # Prepare output directory
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)
    COVERS_DIR.mkdir(parents=True)

    print("Loading playtime data...")
    if not PLAYTIME_FILE.exists():
        print(f"Error: {PLAYTIME_FILE} not found")
        return

    with open(PLAYTIME_FILE) as f:
        data = json.load(f)

    print("Parsing games...")
    games = parse_games(data)

    print("Building HTML...")
    html = build_html(games)

    with open(OUTPUT_FILE, "w") as f:
        f.write(html)

    cover_count = len(list(COVERS_DIR.glob("*.png")))
    print(f"Built: {len(games)} games, {cover_count} covers")
    size_kb = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"HTML size: {size_kb:.0f} KB")

    publish()


if __name__ == "__main__":
    main()
