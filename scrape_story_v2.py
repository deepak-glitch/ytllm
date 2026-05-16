"""
Story Director LLM — YouTube Channel Transcript Scraper v2
Narration-focused curated channel list (long-form storytellers).

Run on YOUR machine: python3 scrape_story_v2.py
Then upload the output zip here for processing.

Requirements: pip install yt-dlp
"""

import os, json, re, glob, subprocess, sys, shutil, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# CURATED CHANNEL LIST — narration-heavy storytellers
# Format: ("@handle", "category", priority 1-5)
# ─────────────────────────────────────────────
CHANNELS = [

    # ── ANIMATED NARRATION STORY ──
    ("@inanutshell",         "animated_story",   5),   # Kurzgesagt
    ("@TED-Ed",              "animated_story",   5),
    ("@itsalexclark",        "animated_story",   5),   # Alex Clark
    ("@Haminations",         "animated_story",   5),
    ("@jaidenanimations",    "animated_story",   5),
    ("@TheOdd1sOut",         "animated_story",   5),
    ("@danielthrasher",      "animated_story",   4),
    ("@SomethingElseYT",     "animated_story",   4),
    ("@GingerPale",          "animated_story",   4),
    ("@Domics",              "animated_story",   4),
    ("@LetMeExplainStudios", "animated_story",   4),
    ("@SwooZie",             "animated_story",   4),
    ("@illymation",          "animated_story",   4),

    # ── DOCUMENTARY NARRATION ──
    ("@MarkRober",           "doc_short",        5),
    ("@Veritasium",          "doc_short",        5),
    ("@CGPGrey",             "doc_short",        5),
    ("@3blue1brown",         "doc_short",        5),
    ("@TomScottGo",          "doc_short",        5),
    ("@Wendoverproductions", "doc_short",        4),
    ("@RealEngineering",     "doc_short",        4),
    ("@PracticalEngineering","doc_short",        4),
    ("@ColdFusion",          "doc_short",        4),
    ("@ElectroBOOM",         "doc_short",        4),
    ("@Vox",                 "doc_short",        4),
    ("@ContraPoints",        "doc_short",        4),
    ("@PhilosophyTube",      "doc_short",        4),

    # ── WORLDBUILDING / LORE NARRATION ──
    ("@Oversimplified",      "worldbuild_story", 5),
    ("@SamONellaAcademy",    "worldbuild_story", 5),
    ("@TierZoo",             "worldbuild_story", 5),
    ("@Nerdwriter1",         "worldbuild_story", 5),
    ("@LEMMiNO",             "worldbuild_story", 5),
    ("@HelloFutureMe",       "worldbuild_story", 5),
    ("@halfasinteresting",   "worldbuild_story", 4),
    ("@MapMen",              "worldbuild_story", 4),
    ("@AlternateHistoryHub", "worldbuild_story", 4),
    ("@HistoryMarche",       "worldbuild_story", 4),
    ("@RealLifeLore",        "worldbuild_story", 4),

    # ── STORY-DRIVEN COMMENTARY ──
    ("@drewisgooden",        "commentary_story", 5),
    ("@Danny-Gonzalez",      "commentary_story", 5),
    ("@EddyBurback",         "commentary_story", 5),
    ("@KurtisConner",        "commentary_story", 4),
    ("@penguinz0",           "commentary_story", 4),
    ("@JarvisJohnson",       "commentary_story", 4),
    ("@ScottTheWoz",         "commentary_story", 4),
    ("@SunnyV2",             "commentary_story", 4),
    ("@EmpLemon",            "commentary_story", 5),

    # ── STORY CRAFT / SCREENWRITING ──
    ("@StudioBinder",        "story_craft",      5),
    ("@TaleFoundry",         "story_craft",      5),
    ("@BrandonSanderson",    "story_craft",      5),
    ("@FilmRiot",            "story_craft",      4),

    # ── EMOTIONAL / STORY NARRATION ──
    ("@MyStoryAnimated",     "emotional_story",  5),
    ("@AnthonyPadilla",      "emotional_story",  5),
    ("@yestheory",           "emotional_story",  5),
    ("@Struthless",          "emotional_story",  5),
    ("@WongFuProductions",   "emotional_story",  4),

    # ── REDDIT / KARMA STORY NARRATION ──
    ("@rSlash",              "reddit_story",     5),
    ("@DnDShorts",           "reddit_story",     4),

    # ── TRUE CRIME / SUSPENSE NARRATION ──
    ("@Nightmind",           "true_crime_story", 4),
    ("@CreepsMcPasta",       "true_crime_story", 4),
    ("@ScaryInteresting",    "true_crime_story", 4),
    ("@Charismaoncommand",   "true_crime_story", 4),

    # ── NARRATION-HEAVY VIRAL SHORTS ──
    ("@NasDaily",            "zackd_style",      5),
    ("@CasuallyExplained",   "zackd_style",      4),
]

# ─────────────────────────────────────────────
# SCRAPER CONFIG
# ─────────────────────────────────────────────
MAX_VIDEOS_PER_CHANNEL = 150       # Cap per channel
MIN_PRIORITY = 3                   # Skip priority < 3
SHORTS_ONLY = False                # v2 channels are mostly long-form
MAX_DURATION_SEC = 600             # Cap individual video length when not shorts
MAX_WORKERS = 4                    # Parallel channel downloads
OUT_DIR = Path("story_v2_transcripts")
OUT_DIR.mkdir(exist_ok=True)

def get_channel_url(handle):
    if SHORTS_ONLY:
        return f"https://www.youtube.com/{handle}/shorts"
    return f"https://www.youtube.com/{handle}/videos"

def scrape_channel(handle, category, priority):
    out = OUT_DIR / category / handle.lstrip("@")
    out.mkdir(parents=True, exist_ok=True)

    cmd = [
        "yt-dlp",
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "json3",
        "--skip-download",
        "--ignore-errors",
        "--no-warnings",
        "--match-filter", f"duration < {65 if SHORTS_ONLY else MAX_DURATION_SEC}",
        "--max-downloads", str(MAX_VIDEOS_PER_CHANNEL),
        "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s",
        "-o", str(out / "%(id)s.%(ext)s"),
        get_channel_url(handle)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    saved = list(out.glob("*.json3"))

    videos = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) >= 3:
            videos.append({
                "id": parts[0],
                "title": parts[1] if len(parts) > 1 else "",
                "duration": parts[2] if len(parts) > 2 else "",
                "views": parts[3] if len(parts) > 3 else "",
                "likes": parts[4] if len(parts) > 4 else "",
            })

    return {
        "handle": handle,
        "category": category,
        "priority": priority,
        "transcript_files": len(saved),
        "video_metadata": videos[:10],
        "status": "ok" if saved else "no_transcripts"
    }

def parse_json3_transcript(filepath):
    """Convert yt-dlp json3 subtitle format to clean text"""
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        words = []
        for event in events:
            for seg in event.get("segs", []):
                utf8 = seg.get("utf8", "").strip()
                if utf8 and utf8 != "\n":
                    words.append(utf8)
        text = " ".join(words)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""

def build_jsonl(out_dir):
    SYSTEM = (
        "You are a viral short-form video creator. Write engaging short-form story "
        "scripts with strong hooks, clear obstacles, satisfying twists, and tight "
        "payoffs. Every word must earn its place."
    )

    jsonl_path = Path("story_v2_examples.jsonl")
    stats = {"total": 0, "skipped_short": 0, "written": 0}

    with open(jsonl_path, "w", encoding="utf-8") as out_f:
        for json3_file in Path(out_dir).rglob("*.json3"):
            text = parse_json3_transcript(json3_file)
            if len(text) < 80:
                stats["skipped_short"] += 1
                continue

            vid_id = json3_file.stem.removesuffix(".en")
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
    print(f"Shorts only: {SHORTS_ONLY} | Max videos/channel: {MAX_VIDEOS_PER_CHANNEL}")
    print()

    metadata_log = []
    failed = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_channel, h, c, p): (h, c, p) for h, c, p in to_scrape}
        for i, future in enumerate(as_completed(futures), 1):
            h, c, p = futures[future]
            try:
                result = future.result(timeout=700)
                metadata_log.append(result)
                status = f"{result['transcript_files']} transcripts"
                print(f"[{i}/{len(to_scrape)}] {h:30s} OK {status}")
            except Exception as e:
                failed.append(h)
                print(f"[{i}/{len(to_scrape)}] {h:30s} FAIL {str(e)[:60]}")

    with open("story_v2_scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(metadata_log, f, indent=2)

    total_transcripts = sum(r["transcript_files"] for r in metadata_log)
    print(f"\n{'='*50}")
    print(f"Total transcripts downloaded: {total_transcripts}")
    print(f"Failed channels: {len(failed)}")
    print(f"\nBuilding training JSONL...")

    jsonl_path, stats = build_jsonl(str(OUT_DIR))
    print(f"Training examples written: {stats['written']}")
    print(f"Skipped (too short): {stats['skipped_short']}")

    print("\nZipping...")
    with zipfile.ZipFile("story-v2-dataset.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path)
        zf.write("story_v2_scrape_log.json")
        for f in Path(OUT_DIR).rglob("*.json3"):
            zf.write(f)

    size_mb = Path("story-v2-dataset.zip").stat().st_size / 1024 / 1024
    print(f"\n{'='*50}")
    print(f"Output: story-v2-dataset.zip ({size_mb:.1f} MB)")
    print(f"Upload this file to Claude for processing.")
    print(f"\nChannel summary by category:")
    from collections import Counter
    cats = Counter(r["category"] for r in metadata_log)
    for cat, count in cats.most_common():
        transcripts = sum(r["transcript_files"] for r in metadata_log if r["category"] == cat)
        print(f"  {cat:25s} {count:3d} channels | {transcripts:5d} transcripts")
