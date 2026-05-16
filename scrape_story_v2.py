"""
Story-Focused Channel Scraper v2
─────────────────────────────────────────────────────────────────────────────
Same scraping code as scrape_channels.py — new curated channel list focused
on ZackDFilms-quality storytelling and Superficial2-style 3D/animated shorts.

Channels already in dataset / run_extra_channels.py are excluded to avoid
duplicates in training_data_v7+.

Run on YOUR machine:
  pip install yt-dlp
  python3 scrape_story_v2.py

Output: story-v2-dataset.zip — upload to Claude for merging into training_data_v7.
─────────────────────────────────────────────────────────────────────────────
"""

import os, json, re, glob, subprocess, sys, shutil, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# CHANNEL LIST
# Format: ("@handle", "category", priority 1-5)
# Priority 5 = must-have, 1 = nice-to-have
# ─────────────────────────────────────────────
CHANNELS = [

    # ══════════════════════════════════════════════════════════════════
    # ZACKDFILMS-STYLE — live-action, cinematic, tight narrative arc
    # Same story DNA: quick setup → obstacle → twist → payoff in <60s
    # ══════════════════════════════════════════════════════════════════
    ("@RyanTrahan",          "zackd_style",      5),
    ("@NasDailyVideos",      "zackd_style",      5),
    ("@JakeShorts",          "zackd_style",      5),
    ("@ColeyTV",             "zackd_style",      5),
    ("@airrack",             "zackd_style",      5),
    ("@CalebSimpson",        "zackd_style",      5),
    ("@JordanMatter",        "zackd_style",      5),
    ("@BenAzelart",          "zackd_style",      4),
    ("@BrentRivera",         "zackd_style",      4),
    ("@zhcyt",               "zackd_style",      4),
    ("@MichaelReeves",       "zackd_style",      4),
    ("@JoshuaWeissman",      "zackd_style",      4),
    ("@WhistlinDiesel",      "zackd_style",      4),
    ("@HaileySek",           "zackd_style",      4),
    ("@ThatGuyNate",         "zackd_style",      4),
    ("@PatrickCC",           "zackd_style",      4),
    ("@JoeHattab",           "zackd_style",      4),
    ("@KallmePat",           "zackd_style",      4),
    ("@PrestonPlayz",        "zackd_style",      4),
    ("@IShowSpeed",          "zackd_style",      3),
    ("@Jynxzi",              "zackd_style",      3),
    ("@LazarBeam",           "zackd_style",      3),
    ("@TommyInnit",          "zackd_style",      3),
    ("@GeorgeNotFound",      "zackd_style",      3),
    ("@WilburSoot",          "zackd_style",      3),

    # ══════════════════════════════════════════════════════════════════
    # SUPERFICIAL2-STYLE — 3D / animated / pixel art story shorts
    # Tell stories through animation with the same tight structure
    # ══════════════════════════════════════════════════════════════════
    ("@CasVanDePol",         "animated_story",   5),
    ("@AlexClark",           "animated_story",   5),
    ("@Haminations",         "animated_story",   5),
    ("@CircleToonsHD",       "animated_story",   5),
    ("@Jaiden",              "animated_story",   5),
    ("@TheOdd1sOut",         "animated_story",   5),
    ("@AlanBecker",          "animated_story",   5),
    ("@KevinParry",          "animated_story",   5),
    ("@KurzgesagtEN",        "animated_story",   5),
    ("@TedEdOfficial",       "animated_story",   5),
    ("@illymation",          "animated_story",   4),
    ("@DanielThrasher",      "animated_story",   4),
    ("@Saberspark",          "animated_story",   4),
    ("@mashed",              "animated_story",   4),
    ("@HiTopFilms",          "animated_story",   4),
    ("@SomethingElseYT",     "animated_story",   4),
    ("@GingerPale",          "animated_story",   4),
    ("@Andymation",          "animated_story",   4),
    ("@Domics",              "animated_story",   4),
    ("@LetMeExplainStudios", "animated_story",   4),
    ("@SwooZie",             "animated_story",   4),

    # ── 3D / low-poly / pixel art game-adjacent ──
    ("@TanTanDev",           "pixel_3d_story",   5),
    ("@SebastianLague",      "pixel_3d_story",   5),
    ("@PolyMars",            "pixel_3d_story",   5),
    ("@t3ssel8r",            "pixel_3d_story",   5),
    ("@HeartBeast",          "pixel_3d_story",   4),
    ("@AdamCYounis",         "pixel_3d_story",   4),
    ("@MortMort",            "pixel_3d_story",   4),
    ("@simondev.",           "pixel_3d_story",   4),
    ("@GodotEngine",         "pixel_3d_story",   3),
    ("@DaFluffyPotato",      "pixel_3d_story",   4),
    ("@BisonCourt",          "pixel_3d_story",   4),
    ("@PilotRedSun",         "pixel_3d_story",   4),
    ("@HappyToast",          "pixel_3d_story",   4),

    # ══════════════════════════════════════════════════════════════════
    # HOOK-FIRST COMMENTARY — story-driven opinion, strong hook structure
    # ══════════════════════════════════════════════════════════════════
    ("@DrewGooden",          "commentary_story", 5),
    ("@DannyGonzalez",       "commentary_story", 5),
    ("@EddyBurback",         "commentary_story", 5),
    ("@KurtisConner",        "commentary_story", 4),
    ("@Pyrocynical",         "commentary_story", 4),
    ("@MoistCr1TiKaL",      "commentary_story", 4),
    ("@JarvisJohnson",       "commentary_story", 4),
    ("@ScottTheWoz",         "commentary_story", 4),
    ("@SunnyV2",             "commentary_story", 4),
    ("@EmpLemon",            "commentary_story", 5),
    ("@Slimecicle",          "commentary_story", 4),
    ("@Optimus",             "commentary_story", 4),

    # ══════════════════════════════════════════════════════════════════
    # EMOTIONAL / DRAMATIC ARC — character-driven, tearjerker or triumph
    # ══════════════════════════════════════════════════════════════════
    ("@Struthless",          "emotional_story",  5),
    ("@AnthonyPadilla",      "emotional_story",  5),
    ("@Yes_Theory",          "emotional_story",  5),
    ("@MyStoriesAnimated",   "emotional_story",  5),
    ("@Omeleto",             "emotional_story",  5),
    ("@ShortoftheWeek",      "emotional_story",  5),
    ("@Dust_Sci_Fi",         "emotional_story",  5),
    ("@Primer",              "emotional_story",  5),
    ("@WongFuProductions",   "emotional_story",  5),
    ("@JayForeman",          "emotional_story",  4),
    ("@JonahFilms",          "emotional_story",  4),
    ("@StoriesWithFlair",    "emotional_story",  4),

    # ══════════════════════════════════════════════════════════════════
    # TRUE CRIME / SUSPENSE — hook → investigation → twist → reveal
    # ══════════════════════════════════════════════════════════════════
    ("@NightmindOfficial",   "true_crime_story", 4),
    ("@CreepsMcPasta",       "true_crime_story", 4),
    ("@WolvenhollowStudios", "true_crime_story", 4),
    ("@ScaryInteresting",    "true_crime_story", 4),
    ("@UnsolvedMysteries",   "true_crime_story", 5),
    ("@ColdCaseDetective",   "true_crime_story", 4),
    ("@Charismaoncommand",   "true_crime_story", 4),

    # ══════════════════════════════════════════════════════════════════
    # REDDIT / KARMA FORMAT — relatable setup + judgment + twist ending
    # ══════════════════════════════════════════════════════════════════
    ("@ProRevenge",          "reddit_story",     5),
    ("@MaliciousCompliance", "reddit_story",     5),
    ("@NuclearRevenge",      "reddit_story",     5),
    ("@RSlash",              "reddit_story",     5),
    ("@InstantKarmaFails",   "reddit_story",     4),
    ("@ChoiceStories",       "reddit_story",     4),
    ("@EntitledParents",     "reddit_story",     4),
    ("@BestofRSlash",        "reddit_story",     4),
    ("@TabletopTalesYT",     "reddit_story",     4),
    ("@GrandmasBoyYT",       "reddit_story",     4),

    # ══════════════════════════════════════════════════════════════════
    # WORLD BUILDING / LORE — exposition delivered as story
    # ══════════════════════════════════════════════════════════════════
    ("@Oversimplified",      "worldbuild_story", 5),
    ("@SamONellaAcademy",   "worldbuild_story", 5),
    ("@TierZoo",             "worldbuild_story", 5),
    ("@NerdWriter1",         "worldbuild_story", 5),
    ("@EveryFrameAPainting", "worldbuild_story", 5),
    ("@LeMMinoYT",           "worldbuild_story", 5),
    ("@HalfAsInteresting",   "worldbuild_story", 4),
    ("@MapMenChannel",       "worldbuild_story", 4),
    ("@AlternateHistoryHub", "worldbuild_story", 4),
    ("@WhatiF",              "worldbuild_story", 4),
    ("@HistoryMarche",       "worldbuild_story", 4),
    ("@RealLifeLore",        "worldbuild_story", 4),
    ("@HelloFutureMeFiction","worldbuild_story", 5),

    # ══════════════════════════════════════════════════════════════════
    # SCREENWRITING / STORY CRAFT — direct narrative structure education
    # ══════════════════════════════════════════════════════════════════
    ("@StudioBinder",        "story_craft",      5),
    ("@D4Dario",             "story_craft",      5),
    ("@JimHull",             "story_craft",      5),
    ("@TaleFoundry",         "story_craft",      5),
    ("@KM_Weiland",          "story_craft",      5),
    ("@BrianMcDonald",       "story_craft",      5),
    ("@SaveTheCatBlake",     "story_craft",      5),
    ("@BrandonSanderson",    "story_craft",      5),
    ("@WriteAboutDragons",   "story_craft",      4),
    ("@FilmRiot",            "story_craft",      4),
    ("@FilmBooth",           "story_craft",      5),
    ("@CreatorScience",      "story_craft",      5),
    ("@Veritasium",          "story_craft",      5),

    # ══════════════════════════════════════════════════════════════════
    # DOCUMENTARY SHORTS — real-world story, strong hook pacing
    # ══════════════════════════════════════════════════════════════════
    ("@MarkRober",           "doc_short",        5),
    ("@ColdfusionTV",        "doc_short",        4),
    ("@RealEngineering",     "doc_short",        4),
    ("@PracticalEngineer",   "doc_short",        4),
    ("@Wendoverproductions", "doc_short",        4),
    ("@CGPGrey",             "doc_short",        5),
    ("@3Blue1Brown",         "doc_short",        5),
    ("@TomScott",            "doc_short",        5),
    ("@VoxDotCom",           "doc_short",        4),
    ("@ElectroBoom",         "doc_short",        4),
    ("@ContraPoints",        "doc_short",        4),
    ("@Philosophytube",      "doc_short",        4),

    # ══════════════════════════════════════════════════════════════════
    # COMEDY STORY — setup → escalation → punchline payoff
    # ══════════════════════════════════════════════════════════════════
    ("@CasuallyExplained",   "comedy_story",     5),
    ("@JacksFilms",          "comedy_story",     4),
    ("@SMii7Y",              "comedy_story",     4),
    ("@KyrSP",               "comedy_story",     4),
    ("@TechLead",            "comedy_story",     4),
    ("@DidYouKnowGaming",    "comedy_story",     4),

]

# ─────────────────────────────────────────────
# SCRAPER CONFIG  (matches run_extra_channels.py which is proven to work)
# ─────────────────────────────────────────────
MIN_PRIORITY = 4                   # Skip priority < 4 (set to 3 for more data)
MAX_WORKERS = 3                    # Parallel channel downloads
OUT_DIR = Path("story_v2_transcripts")
ARCHIVES_DIR = Path("story_v2_archives")
OUT_DIR.mkdir(exist_ok=True)
ARCHIVES_DIR.mkdir(exist_ok=True)


def seed_archive(handle, out_dir, archive_path):
    """Pre-populate archive from already-downloaded files so resumed runs skip them."""
    existing = {p.name.removesuffix(".en.json3") for p in out_dir.glob("*.en.json3")}
    archived = set()
    if archive_path.exists():
        for line in open(archive_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("youtube "):
                archived.add(line.split(" ", 1)[1])
    new_ids = existing - archived
    if new_ids:
        with open(archive_path, "a", encoding="utf-8") as f:
            for vid in sorted(new_ids):
                f.write(f"youtube {vid}\n")
    if archived or new_ids:
        print(f"  [{handle}] {len(archived | new_ids)} already downloaded, skipping")


def scrape_channel(handle, category, priority):
    out_dir = OUT_DIR / category / handle.lstrip("@")
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVES_DIR / f"{handle.lstrip('@')}.txt"
    seed_archive(handle, out_dir, archive_path)

    # Exact command from run_extra_channels.py — proven to work
    cmd = [
        "yt-dlp",
        "--write-auto-sub", "--sub-lang", "en", "--sub-format", "json3",
        "--skip-download", "--ignore-errors", "--no-warnings",
        "--download-archive", str(archive_path),
        "--sleep-requests", "3",
        "--sleep-interval", "3",
        "--max-sleep-interval", "8",
        "--sleep-subtitles", "2",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        f"https://www.youtube.com/{handle}/shorts",
    ]

    # No capture_output — print directly to terminal like run_extra_channels.py
    subprocess.run(cmd, timeout=600)

    saved = list(out_dir.glob("*.json3"))
    return {
        "handle": handle,
        "category": category,
        "priority": priority,
        "transcript_files": len(saved),
        "status": "ok" if saved else "no_transcripts"
    }


def parse_json3_transcript(filepath):
    """Convert yt-dlp json3 subtitle format to clean text."""
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


def build_jsonl(out_dir: Path):
    """Convert all transcripts to training JSONL with per-category weights."""
    SYSTEM = (
        "You are a viral short-form video creator. Write engaging short-form story scripts "
        "with strong hooks, clear obstacles, satisfying twists, and tight payoffs. "
        "Every word must earn its place."
    )

    # Weight by category — story-reference channels get higher weight
    CATEGORY_WEIGHTS = {
        "zackd_style":      5,
        "animated_story":   5,
        "pixel_3d_story":   5,
        "emotional_story":  5,
        "commentary_story": 4,
        "true_crime_story": 4,
        "reddit_story":     4,
        "worldbuild_story": 4,
        "story_craft":      4,
        "doc_short":        4,
        "comedy_story":     3,
    }

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
            weight = CATEGORY_WEIGHTS.get(category, 3)

            record = {
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": f"Write a short-form video script in the style of @{channel} ({category} category)."},
                    {"role": "assistant", "content": text}
                ],
                "source": f"yt_transcript_{category}",
                "channel": channel,
                "video_id": vid_id,
                "weight": weight
            }
            out_f.write(json.dumps(record) + "\n")
            stats["written"] += 1

    stats["total"] = stats["written"] + stats["skipped_short"]
    return jsonl_path, stats


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # De-duplicate handles (same channel can appear in multiple categories)
    seen = {}
    deduped = []
    for handle, cat, pri in CHANNELS:
        key = handle.lower()
        if key not in seen:
            seen[key] = True
            deduped.append((handle, cat, pri))

    to_scrape = [(h, c, p) for h, c, p in deduped if p >= MIN_PRIORITY]
    print(f"Story Scraper v2")
    print(f"Channels to scrape: {len(to_scrape)} (priority >= {MIN_PRIORITY})")
    print(f"Shorts only: {SHORTS_ONLY} | Max videos/channel: {MAX_VIDEOS_PER_CHANNEL}")
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
                status = f"✓ {result['transcript_files']:4d} transcripts"
                print(f"[{i:3d}/{len(to_scrape)}] {h:35s} [{c:20s}] p={p}  {status}")
            except Exception as e:
                failed.append(h)
                print(f"[{i:3d}/{len(to_scrape)}] {h:35s} ✗ {str(e)[:60]}")

    with open("story_v2_scrape_log.json", "w") as f:
        json.dump(metadata_log, f, indent=2)

    total_transcripts = sum(r["transcript_files"] for r in metadata_log)
    print(f"\n{'='*60}")
    print(f"Total transcripts downloaded: {total_transcripts}")
    print(f"Failed channels: {len(failed)}")
    print(f"\nBuilding training JSONL...")

    jsonl_path, stats = build_jsonl(OUT_DIR)
    print(f"Training examples written: {stats['written']}")
    print(f"Skipped (too short):       {stats['skipped_short']}")

    print("\nZipping...")
    with zipfile.ZipFile("story-v2-dataset.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path)
        zf.write("story_v2_scrape_log.json")
        for f in OUT_DIR.rglob("*.json3"):
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

    if failed:
        print(f"\nChannels with 0 transcripts (check handle spelling):")
        zero = [r["handle"] for r in metadata_log if r["transcript_files"] == 0]
        for h in zero:
            print(f"  {h}")
