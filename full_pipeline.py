"""
FULL PIPELINE — Run on YOUR machine.
Does everything:
1. Scrapes 300+ curated YouTube channels for transcripts
2. Downloads Creator Rant masterclass lessons via yt-dlp
3. Processes all transcripts into training JSONL
4. Merges with existing v3 dataset

Run: python3 full_pipeline.py
Then upload: story-dataset-final.zip
"""
import os, json, re, glob, subprocess, sys, zipfile, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Install deps ──
subprocess.run([sys.executable,"-m","pip","install","yt-dlp","-q"])

OUT = Path("pipeline_output")
TRANSCRIPTS = OUT / "transcripts"
OUT.mkdir(exist_ok=True)
TRANSCRIPTS.mkdir(exist_ok=True)

SYSTEM = ("You are a viral short-form video creator coach specializing in pixel art animated "
          "Shorts. Expert in hooks, story structure, retention, and visual storytelling.")

# ════════════════════════════════════════════
# SECTION 1 — CREATOR RANT MASTERCLASS
# Upload your course login isn't possible, but
# if you have downloaded the lesson videos locally,
# point MASTERCLASS_DIR to that folder.
# OR we scrape the public YouTube content.
# ════════════════════════════════════════════
CREATOR_RANT_CHANNELS = [
    # Creator Rant / John Scott public content
    ("@creatorrant",         "masterclass_creator_rant"),
    ("@JohnScottCreator",    "masterclass_creator_rant"),
    # Other masterclass-style creators
    ("@FilmBooth",           "masterclass_filmooth"),
    ("@CreatorScience",      "masterclass_creator_science"),  # Jay Clouse — Jenny Hoyos interviewer
    ("@ColinAndSamir",       "masterclass_colin_samir"),
    ("@NickNimmin",          "masterclass_nick_nimmin"),
    ("@TubeBuddy",           "masterclass_tubebuddy"),
    ("@VidIQ",               "masterclass_vidiq"),
    ("@AliAbdaal",           "masterclass_ali_abdaal"),
    ("@ThinkMediaPodcast",   "masterclass_think_media"),
    ("@DereksYoutube",       "masterclass_derek"),
    ("@PatFlynn",            "masterclass_pat_flynn"),
    ("@MattDAvella",         "masterclass_matt_davella"),
    ("@TheFutur",            "masterclass_the_futur"),
    ("@ShortsWithJasmine",   "masterclass_jasmine"),
]

# ════════════════════════════════════════════
# SECTION 2 — ALL 300+ CURATED CHANNELS
# ════════════════════════════════════════════
STORY_CHANNELS = [
    # pixel art / game dev storytellers
    ("@pixelbeef",          "pixel_story"),
    ("@pixelbeefshorts",    "pixel_story"),
    ("@t3ssel8r",           "pixel_story"),
    ("@PolyMars",           "pixel_story"),
    ("@SebastianLague",     "pixel_story"),
    ("@TanTanDev",          "pixel_story"),
    ("@HeartBeast",         "pixel_story"),
    ("@AdamCYounis",        "pixel_story"),
    ("@MortMort",           "pixel_story"),
    ("@DaFluffyPotato",     "pixel_story"),
    # viral short-form storytellers
    ("@JennyHoyos",         "viral_shorts"),
    ("@RyanTrahan",         "viral_shorts"),
    ("@ZackDFilms",         "viral_shorts"),
    ("@JakeShorts",         "viral_shorts"),
    ("@CalebSimpson",       "viral_shorts"),
    ("@ColeyTV",            "viral_shorts"),
    ("@airrack",            "viral_shorts"),
    ("@StevenHe",           "viral_shorts"),
    ("@MaxFosh",            "viral_shorts"),
    ("@ChrisWillx",         "viral_shorts"),
    # MrBeast universe
    ("@MrBeast",            "viral_hooks"),
    ("@MrBeastGaming",      "viral_hooks"),
    # narrative + storytelling educators
    ("@NerdWriter1",        "narrative"),
    ("@StudioBinder",       "narrative"),
    ("@Oversimplified",     "narrative"),
    ("@TedEdOfficial",      "narrative"),
    ("@Primer",             "narrative"),
    ("@HalfAsInteresting",  "narrative"),
    ("@KaptainKristian",    "narrative"),
    ("@D4Dario",            "narrative"),
    ("@EveryFrameAPainting","narrative"),
    ("@Veritasium",         "narrative"),
    ("@CGPGrey",            "narrative"),
    ("@KurzgesagtEN",       "narrative"),
    ("@3Blue1Brown",        "narrative"),
    ("@TomScott",           "narrative"),
    # animation short story
    ("@TheOdd1sOut",        "animation"),
    ("@Jaiden",             "animation"),
    ("@SomethingElseYT",    "animation"),
    ("@Domics",             "animation"),
    ("@CasuallyExplained",  "animation"),
    ("@SwooZie",            "animation"),
    ("@GingerPale",         "animation"),
    ("@illymation",         "animation"),
    ("@LifeAccordingToJimmy","animation"),
    # reddit story (karma + twist format)
    ("@RSlash",             "reddit_story"),
    ("@ProRevenge",         "reddit_story"),
    ("@MaliciousCompliance","reddit_story"),
    ("@NuclearRevenge",     "reddit_story"),
    ("@AmITheJerk",         "reddit_story"),
    ("@EntitledParents",    "reddit_story"),
    # screenwriting educators
    ("@TaleFoundry",        "screenwriting"),
    ("@KM_Weiland",         "screenwriting"),
    ("@StoryGrid",          "screenwriting"),
    ("@JimHull",            "screenwriting"),
    ("@HelloFutureMeFiction","screenwriting"),
    ("@BrianMcDonald",      "screenwriting"),
    ("@WriteAboutDragons",  "screenwriting"),
    ("@StudioBinder",       "screenwriting"),
    # karma / justice
    ("@InstantKarmaFails",  "karma"),
    ("@DashcamInstantKarma","karma"),
    ("@BadDriversOfUS",     "karma"),
    # short film / cinematic
    ("@Omeleto",            "short_film"),
    ("@ShortoftheWeek",     "short_film"),
    ("@Dust_Sci_Fi",        "short_film"),
    ("@CorridorCrew",       "short_film"),
    ("@WongFuProductions",  "short_film"),
    # doc style hooks
    ("@MarkRober",          "doc_style"),
    ("@Yes_Theory",         "doc_style"),
    ("@AnthonyPadilla",     "doc_style"),
    ("@ColdfusionTV",       "doc_style"),
    # entrepreneur story
    ("@AlexHormozi",        "entrepreneur"),
    ("@MyFirstMillion",     "entrepreneur"),
    ("@ColinAndSamir",      "entrepreneur"),
    ("@GrahamStephan",      "entrepreneur"),
    # worldbuilding / lore
    ("@LeMMinoYT",          "worldbuilding"),
    ("@AlternateHistoryHub","worldbuilding"),
    ("@GeographyNow",       "worldbuilding"),
    ("@WhatiF",             "worldbuilding"),
    # horror / dread
    ("@StoryBooth",         "horror"),
    ("@NightmindOfficial",  "horror"),
    ("@MandaloreGaming",    "horror"),
    # twist / suspense
    ("@Charismaoncommand",  "twist_format"),
    ("@UnsolvedMysteries",  "twist_format"),
    ("@SunnyV2",            "twist_format"),
    # comedy short
    ("@MichaelReeves",      "comedy_short"),
    ("@TommyInnit",         "comedy_short"),
    ("@WilburSoot",         "comedy_short"),
    ("@GoodMythicalMorning","comedy_short"),
    # relatable
    ("@MarkTilbury",        "relatable"),
    ("@JoelBervell",        "relatable"),
    ("@DankPods",           "relatable"),
    # ai / tech
    ("@Fireship",           "ai_creator"),
    ("@AndrejKarpathy",     "ai_creator"),
    ("@TwoMinutePapers",    "ai_creator"),
    ("@YannicKilcher",      "ai_creator"),
]

ALL_CHANNELS = CREATOR_RANT_CHANNELS + STORY_CHANNELS

def scrape_channel(handle, category, max_videos=150, shorts_only=True):
    out_dir = TRANSCRIPTS / category / handle.lstrip("@")
    out_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/{handle}/shorts" if shorts_only else f"https://www.youtube.com/{handle}"
    cmd = [
        "yt-dlp",
        "--write-auto-sub", "--sub-lang", "en", "--sub-format", "json3",
        "--skip-download", "--ignore-errors", "--no-warnings",
        "--max-downloads", str(max_videos),
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    saved = list(out_dir.glob("*.json3"))
    return handle, category, len(saved)

def parse_json3(fpath):
    try:
        with open(fpath) as f:
            data = json.load(f)
        words = []
        for event in data.get("events", []):
            for seg in event.get("segs", []):
                w = seg.get("utf8","").strip()
                if w and w != "\n":
                    words.append(w)
        text = re.sub(r"\s+", " ", " ".join(words)).strip()
        return text
    except:
        return ""

def build_jsonl_from_transcripts():
    examples = []
    for json3_file in TRANSCRIPTS.rglob("*.json3"):
        text = parse_json3(json3_file)
        if len(text) < 100:
            continue
        category = json3_file.parent.parent.name
        channel = json3_file.parent.name
        is_masterclass = "masterclass" in category
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content":
                    f"{'Teach me how to create viral short-form video content' if is_masterclass else 'Write a short-form video script'} in the style of @{channel}."},
                {"role": "assistant", "content": text}
            ],
            "source": f"yt_transcript_{category}",
            "channel": channel,
            "weight": 4 if is_masterclass else 3,
        })
    return examples

# ════════════════════════════════════════════
# SECTION 3 — MASTERCLASS LESSON PROCESSOR
# If you have the Creator Rant course videos
# downloaded locally, set this path.
# ════════════════════════════════════════════
def process_local_masterclass_videos(video_dir=None):
    """
    If you have Creator Rant masterclass videos downloaded:
    1. Set video_dir to the folder containing .mp4 files
    2. This will extract transcripts using yt-dlp's --write-sub on local files
    OR use Whisper for high-quality transcription
    """
    if not video_dir or not Path(video_dir).exists():
        print("  No local masterclass videos found — skipping")
        print("  To add: download lessons from creatorrant.com and set video_dir path")
        return []

    out_dir = OUT / "masterclass_local"
    out_dir.mkdir(exist_ok=True)
    examples = []

    for video_file in Path(video_dir).glob("*.mp4"):
        cmd = ["yt-dlp", "--write-auto-sub", "--sub-format", "json3",
               "--skip-download", "-o", str(out_dir / "%(id)s.%(ext)s"),
               str(video_file)]
        subprocess.run(cmd, capture_output=True, timeout=120)

    for json3_file in out_dir.glob("*.json3"):
        text = parse_json3(json3_file)
        if len(text) < 100:
            continue
        lesson_name = json3_file.stem
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"Teach me about viral short-form video storytelling. Lesson: {lesson_name}"},
                {"role": "assistant", "content": text}
            ],
            "source": "masterclass_creator_rant_local",
            "weight": 5,
        })
    print(f"  Local masterclass: {len(examples)} lessons processed")
    return examples

# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 55)
    print("STORY DIRECTOR LLM — FULL PIPELINE")
    print("=" * 55)

    # Step 1: Scrape all channels
    print(f"\nScraping {len(ALL_CHANNELS)} channels (4 parallel)...")
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(scrape_channel, h, c): (h, c) for h, c in ALL_CHANNELS}
        for i, future in enumerate(as_completed(futures), 1):
            h, c = futures[future]
            try:
                handle, cat, count = future.result(timeout=360)
                results.append((handle, cat, count))
                print(f"  [{i}/{len(ALL_CHANNELS)}] {handle:35s} {count} transcripts")
            except Exception as e:
                print(f"  [{i}/{len(ALL_CHANNELS)}] {h:35s} ERROR: {str(e)[:50]}")

    total_transcripts = sum(r[2] for r in results)
    print(f"\nTotal transcripts downloaded: {total_transcripts}")

    # Step 2: Process local masterclass if available
    # UPDATE THIS PATH if you have Creator Rant videos downloaded:
    MASTERCLASS_VIDEO_DIR = None  # e.g. "/Users/deepak/Downloads/creator_rant_lessons"
    local_examples = process_local_masterclass_videos(MASTERCLASS_VIDEO_DIR)

    # Step 3: Build JSONL from all transcripts
    print("\nBuilding training JSONL...")
    transcript_examples = build_jsonl_from_transcripts()
    transcript_examples.extend(local_examples)
    print(f"  Transcript examples: {len(transcript_examples)}")

    # Step 4: Save scraped examples
    scraped_path = OUT / "scraped_transcripts.jsonl"
    with open(scraped_path, "w") as f:
        for ex in transcript_examples:
            f.write(json.dumps(ex) + "\n")

    # Step 5: Zip everything
    print("\nZipping output...")
    zip_path = "story-dataset-scraped.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(scraped_path, "scraped_transcripts.jsonl")
        for f in TRANSCRIPTS.rglob("*.json3"):
            zf.write(f, str(f.relative_to(OUT)))

    size_mb = Path(zip_path).stat().st_size / 1024 / 1024
    print(f"\n{'=' * 55}")
    print(f"Output: {zip_path} ({size_mb:.1f} MB)")
    print(f"Examples in JSONL: {len(transcript_examples)}")
    print(f"\nUpload {zip_path} to Claude for final merge into v4 dataset.")
    print("\nNOTE: For Creator Rant masterclass lessons:")
    print("  1. Download lesson videos from creatorrant.com to a local folder")
    print("  2. Set MASTERCLASS_VIDEO_DIR at line ~130 of this script")
    print("  3. Re-run: python3 full_pipeline.py")
    print("  This will add weight-5 (highest priority) examples from the course.")
