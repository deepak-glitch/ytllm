"""
Story Director LLM — YouTube Channel Transcript Scraper (v2)
Same scraping engine as scrape_channels.py — verified handles only.

Run on YOUR machine: python3 scrape_story_v2.py
Output: story-v2-dataset.zip → upload back to Claude.

Requirements: pip install yt-dlp
"""

import os, json, re, glob, subprocess, sys, shutil, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# VERIFIED CHANNEL HANDLES (web-searched)
# Format: ("@handle", "category", priority 1-5)
# ─────────────────────────────────────────────
CHANNELS = [

    # ── ZACKDFILMS-STYLE — live-action narrative shorts ──
    ("@ryan",                "zackd_style",      5),   # Ryan Trahan
    ("@NasDaily",            "zackd_style",      5),   # Nas Daily
    ("@CALEBWSIMPSON",       "zackd_style",      5),   # Caleb Simpson ("how much rent" shorts)
    ("@clintcoley",          "zackd_style",      5),   # Comedian Clint Coley (viral shorts)
    ("@jordanmatter",        "zackd_style",      5),   # Jordan Matter
    ("@brentrivera",         "zackd_style",      4),   # Brent Rivera
    ("@ZHC",                 "zackd_style",      4),   # ZHC art challenges
    ("@michaelreeves",       "zackd_style",      4),   # Michael Reeves
    ("@JoshuaWeissman",      "zackd_style",      4),   # Joshua Weissman
    ("@WhistlinDiesel",      "zackd_style",      4),   # WhistlinDiesel
    ("@IShowSpeed",          "zackd_style",      3),   # IShowSpeed
    ("@LazarBeam",           "zackd_style",      3),   # LazarBeam
    ("@TommyInnit",          "zackd_style",      3),   # TommyInnit
    ("@WilburSoot",          "zackd_style",      3),   # WilburSoot
    ("@GeorgeNotFound",      "zackd_style",      3),   # GeorgeNotFound

    # ── SUPERFICIAL2-STYLE — animated story shorts ──
    ("@casvandepol",         "animated_story",   5),   # Cas van de Pol
    ("@itsalexclark",        "animated_story",   5),   # Alex Clark
    ("@Haminations",         "animated_story",   5),   # Haminations
    ("@CircleToonsHD",       "animated_story",   5),   # CircleToonsHD
    ("@jaidenanimations",    "animated_story",   5),   # Jaiden Animations
    ("@TheOdd1sOut",         "animated_story",   5),   # TheOdd1sOut
    ("@AlanBecker",          "animated_story",   5),   # Alan Becker
    ("@kevinparry",          "animated_story",   5),   # Kevin Parry
    ("@inanutshell",         "animated_story",   5),   # Kurzgesagt
    ("@TED-Ed",              "animated_story",   5),   # TED-Ed
    ("@danielthrasher",      "animated_story",   4),   # Daniel Thrasher
    ("@SomethingElseYT",     "animated_story",   4),   # SomethingElseYT
    ("@GingerPale",          "animated_story",   4),   # GingerPale
    ("@Domics",              "animated_story",   4),   # Domics
    ("@LetMeExplainStudios", "animated_story",   4),   # Let Me Explain Studios
    ("@SwooZie",             "animated_story",   4),   # sWooZie
    ("@illymation",          "animated_story",   4),   # illymation
    ("@CasuallyExplained",   "animated_story",   4),   # Casually Explained

    # ── 3D / pixel / game-dev story ──
    ("@TanTanDev",           "pixel_3d_story",   5),
    ("@SebastianLague",      "pixel_3d_story",   5),
    ("@PolyMars",            "pixel_3d_story",   5),
    ("@t3ssel8r",            "pixel_3d_story",   5),
    ("@HeartBeast",          "pixel_3d_story",   4),
    ("@AdamCYounis",         "pixel_3d_story",   4),
    ("@MortMort",            "pixel_3d_story",   4),
    ("@DaFluffyPotato",      "pixel_3d_story",   4),
    ("@GodotEngine",         "pixel_3d_story",   3),

    # ── HOOK-FIRST COMMENTARY ──
    ("@drewisgooden",        "commentary_story", 5),   # Drew Gooden
    ("@Danny-Gonzalez",      "commentary_story", 5),   # Danny Gonzalez
    ("@EddyBurback",         "commentary_story", 5),   # Eddy Burback
    ("@KurtisConner",        "commentary_story", 4),
    ("@penguinz0",           "commentary_story", 4),   # MoistCr1TiKaL
    ("@JarvisJohnson",       "commentary_story", 4),
    ("@ScottTheWoz",         "commentary_story", 4),
    ("@SunnyV2",             "commentary_story", 4),
    ("@EmpLemon",            "commentary_story", 5),

    # ── EMOTIONAL / DRAMATIC SHORT FILMS ──
    ("@Struthless",          "emotional_story",  5),
    ("@AnthonyPadilla",      "emotional_story",  5),
    ("@yestheory",           "emotional_story",  5),   # Yes Theory
    ("@Omeleto",             "emotional_story",  5),
    ("@ShortoftheWeek",      "emotional_story",  5),
    ("@dust",                "emotional_story",  5),   # Dust sci-fi
    ("@Primer",              "emotional_story",  5),
    ("@WongFuProductions",   "emotional_story",  5),
    ("@MyStoryAnimated",     "emotional_story",  4),   # My Story Animated

    # ── TRUE CRIME / SUSPENSE ──
    ("@Nightmind",           "true_crime_story", 4),   # Nightmind
    ("@CreepsMcPasta",       "true_crime_story", 4),
    ("@ScaryInteresting",    "true_crime_story", 4),
    ("@Charismaoncommand",   "true_crime_story", 4),

    # ── REDDIT / KARMA ──
    ("@rSlash",              "reddit_story",     5),   # r/Slash
    ("@MrRedditStories",     "reddit_story",     4),
    ("@DnDShorts",           "reddit_story",     4),

    # ── WORLD BUILDING / LORE ──
    ("@Oversimplified",      "worldbuild_story", 5),
    ("@SamONellaAcademy",   "worldbuild_story", 5),   # Sam O'Nella Academy
    ("@TierZoo",             "worldbuild_story", 5),
    ("@Nerdwriter1",         "worldbuild_story", 5),   # Nerdwriter1
    ("@LEMMiNO",             "worldbuild_story", 5),   # LEMMiNO
    ("@halfasinteresting",   "worldbuild_story", 4),
    ("@MapMen",              "worldbuild_story", 4),
    ("@AlternateHistoryHub", "worldbuild_story", 4),
    ("@WhatifAltHist",       "worldbuild_story", 4),
    ("@HistoryMarche",       "worldbuild_story", 4),
    ("@RealLifeLore",        "worldbuild_story", 4),
    ("@HelloFutureMe",       "worldbuild_story", 5),

    # ── STORY CRAFT / SCREENWRITING ──
    ("@StudioBinder",        "story_craft",      5),
    ("@TaleFoundry",         "story_craft",      5),
    ("@BrandonSanderson",    "story_craft",      5),
    ("@FilmRiot",            "story_craft",      4),
    ("@Veritasium",          "story_craft",      5),

    # ── DOCUMENTARY SHORTS ──
    ("@MarkRober",           "doc_short",        5),
    ("@ColdFusion",          "doc_short",        4),
    ("@RealEngineering",     "doc_short",        4),
    ("@PracticalEngineering","doc_short",        4),   # Practical Engineering
    ("@Wendoverproductions", "doc_short",        4),
    ("@CGPGrey",             "doc_short",        5),
    ("@3blue1brown",         "doc_short",        5),
    ("@TomScottGo",          "doc_short",        5),   # Tom Scott
    ("@Vox",                 "doc_short",        4),   # Vox
    ("@ElectroBOOM",         "doc_short",        4),
    ("@ContraPoints",        "doc_short",        4),
    ("@PhilosophyTube",      "doc_short",        4),

    # ── COMEDY STORY ──
    ("@jacksfilms",          "comedy_story",     4),
    ("@SMii7Y",              "comedy_story",     4),
    ("@DidYouKnowGaming",    "comedy_story",     4),
]

# ─────────────────────────────────────────────
# SCRAPER CONFIG
# ─────────────────────────────────────────────
MAX_VIDEOS_PER_CHANNEL = 150
MIN_PRIORITY = 3
MAX_WORKERS = 4
OUT_DIR = Path("story_v2_transcripts")
OUT_DIR.mkdir(exist_ok=True)


def run_ytdlp(handle, tab, out_dir, max_duration):
    """Run yt-dlp for one channel tab. Returns (stdout, stderr)."""
    url = f"https://www.youtube.com/{handle}{tab}"
    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "json3",
        "--skip-download",
        "--ignore-errors",
        "--no-warnings",
        "--match-filter", f"duration < {max_duration}",
        "--max-downloads", str(MAX_VIDEOS_PER_CHANNEL),
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return result.stdout, result.stderr


def scrape_channel(handle, category, priority):
    out = OUT_DIR / category / handle.lstrip("@")
    out.mkdir(parents=True, exist_ok=True)

    # Strategy: try /shorts first (fast, only short videos).
    # If 0 results, fall back to /videos with duration<180s filter
    # (catches both shorts and short narrative videos).
    _, err1 = run_ytdlp(handle, "/shorts", out, max_duration=65)
    saved = list(out.glob("*.json3"))

    used_fallback = False
    err2 = ""
    if not saved:
        _, err2 = run_ytdlp(handle, "/videos", out, max_duration=180)
        saved = list(out.glob("*.json3"))
        used_fallback = True

    # Surface the most relevant error line if we got nothing
    err_snippet = ""
    if not saved:
        combined = (err2 or err1 or "").strip().split("\n")
        for line in reversed(combined):
            if "ERROR" in line or "WARNING" in line:
                err_snippet = line[:130]
                break
        if not err_snippet and combined:
            err_snippet = combined[-1][:130]

    return {
        "handle": handle,
        "category": category,
        "priority": priority,
        "transcript_files": len(saved),
        "status": "ok" if saved else "no_transcripts",
        "used_fallback": used_fallback,
        "error": err_snippet,
    }


def parse_json3_transcript(filepath):
    try:
        with open(filepath) as f:
            data = json.load(f)
        events = data.get("events", [])
        words = []
        for event in events:
            for seg in event.get("segs", []):
                utf8 = seg.get("utf8", "").strip()
                if utf8 and utf8 != "\n":
                    words.append(utf8)
        text = " ".join(words)
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except:
        return ""


def build_jsonl(out_dir, metadata_log):
    SYSTEM = "You are a viral short-form video creator. Write engaging short-form story scripts with strong hooks, clear obstacles, satisfying twists, and tight payoffs. Every word must earn its place."

    jsonl_path = Path("story_v2_examples.jsonl")
    stats = {"total": 0, "skipped_short": 0, "written": 0}

    with open(jsonl_path, "w") as out_f:
        for json3_file in Path(out_dir).rglob("*.json3"):
            text = parse_json3_transcript(json3_file)
            if len(text) < 80:
                stats["skipped_short"] += 1
                continue

            vid_id = json3_file.stem
            category = json3_file.parent.parent.name
            channel = json3_file.parent.name

            record = {
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Write a short-form video script in the style of @{channel} ({category} category)."},
                    {"role": "assistant", "content": text}
                ],
                "source": f"youtube_transcript_{category}",
                "channel": channel,
                "video_id": vid_id,
                "weight": 4
            }
            out_f.write(json.dumps(record) + "\n")
            stats["written"] += 1
        stats["total"] = stats["written"] + stats["skipped_short"]

    return jsonl_path, stats


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    to_scrape = [(h, c, p) for h, c, p in CHANNELS if p >= MIN_PRIORITY]
    print(f"Scraping {len(to_scrape)} channels (priority >= {MIN_PRIORITY})")
    print(f"Strategy: try /shorts first, fall back to /videos with duration<180s")
    print(f"Max videos per channel: {MAX_VIDEOS_PER_CHANNEL}")
    print()

    metadata_log = []
    failed = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_channel, h, c, p): (h, c, p) for h, c, p in to_scrape}
        for i, future in enumerate(as_completed(futures), 1):
            h, c, p = futures[future]
            try:
                result = future.result(timeout=360)
                metadata_log.append(result)
                count = result['transcript_files']
                fb = " [fallback]" if result.get('used_fallback') else ""
                if count > 0:
                    status = f"✓ {count:4d} transcripts{fb}"
                else:
                    err = result.get('error', '')
                    status = f"✗ 0 transcripts  {err}"
                print(f"[{i:3d}/{len(to_scrape)}] {h:25s} {status}")
            except Exception as e:
                failed.append(h)
                print(f"[{i:3d}/{len(to_scrape)}] {h:25s} ✗ {str(e)[:60]}")

    with open("story_v2_scrape_log.json", "w") as f:
        json.dump(metadata_log, f, indent=2)

    total_transcripts = sum(r["transcript_files"] for r in metadata_log)
    print(f"\n{'='*60}")
    print(f"Total transcripts downloaded: {total_transcripts}")
    print(f"Failed channels: {len(failed)}")
    print(f"\nBuilding training JSONL...")

    jsonl_path, stats = build_jsonl(str(OUT_DIR), metadata_log)
    print(f"Training examples written: {stats['written']}")
    print(f"Skipped (too short): {stats['skipped_short']}")

    print("\nZipping...")
    with zipfile.ZipFile("story-v2-dataset.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path)
        zf.write("story_v2_scrape_log.json")
        for f in Path(OUT_DIR).rglob("*.json3"):
            zf.write(f)

    size_mb = Path("story-v2-dataset.zip").stat().st_size / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"Output: story-v2-dataset.zip ({size_mb:.1f} MB)")
    print(f"Upload this file to Claude for processing.")
    print(f"\nChannel summary by category:")
    from collections import Counter
    cats = Counter(r["category"] for r in metadata_log)
    for cat, count in cats.most_common():
        transcripts = sum(r["transcript_files"] for r in metadata_log if r["category"] == cat)
        print(f"  {cat:25s} {count:3d} channels | {transcripts:5d} transcripts")

    zero = [r["handle"] for r in metadata_log if r["transcript_files"] == 0]
    if zero:
        print(f"\nChannels that returned 0 transcripts (verify handle):")
        for h in zero:
            print(f"  {h}")
