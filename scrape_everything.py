"""
scrape_everything.py — Full Transcript + Comment Scraper (yt-dlp, no API key needed)
======================================================================================
Uses yt-dlp for channel discovery + comments.
Uses youtube-transcript-api for transcripts (works on Colab, no quota).
No API keys. No quota. Just run it.

Run on Colab / local:
    pip install yt-dlp youtube-transcript-api tqdm
    python scrape_everything.py

Checkpoint/resume: safe to Ctrl+C and rerun.

Outputs:
    checkpoint/                  ← one JSON per video (auto-resume)
    everything_raw.jsonl         ← all raw data
    everything_training.jsonl    ← training-ready JSONL
    training_data_v8.jsonl       ← merged with v7, ready to fine-tune
"""

import os, json, re, sys, time, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict, Counter

# ── Auto-install ──────────────────────────────────────────────────────────────
def _pip(*pkgs):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs])

try:
    import yt_dlp
except ImportError:
    print("Installing yt-dlp..."); _pip("yt-dlp"); import yt_dlp

class _Silent:
    """Logger that swallows all yt-dlp output including ERRORs."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

try:
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
except ImportError:
    print("Installing youtube-transcript-api..."); _pip("youtube-transcript-api")
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

try:
    from tqdm import tqdm
except ImportError:
    _pip("tqdm"); from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
WORKERS              = 4     # parallel video workers (keep low to avoid rate limits)
MAX_VIDEOS_PER_CH    = 5000  # effectively unlimited — pages until channel is empty
MAX_COMMENTS         = 1000  # top comments per video
MAX_DURATION         = 180   # skip videos longer than 3 min
MIN_TRANSCRIPT_WORDS = 10    # skip near-empty transcripts

CHECKPOINT_DIR = Path("checkpoint")
OUT_RAW        = Path("everything_raw.jsonl")
OUT_TRAINING   = Path("everything_training.jsonl")
CHECKPOINT_DIR.mkdir(exist_ok=True)
write_lock = Lock()

# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL LIST — 240 channels, 15 categories
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS = [

    # ── YOUR EXACT NICHE — pixel art / 3D animation storytelling ─────────
    ("@pixelbeef",              "pixel_story",       5),
    ("@pixelbeefshorts",        "pixel_story",       5),
    ("@t3ssel8r",               "pixel_story",       5),
    ("@PolyMars",               "pixel_story",       5),
    ("@SebastianLague",         "pixel_story",       5),
    ("@TanTanDev",              "pixel_story",       5),
    ("@simondev.",              "pixel_story",       4),
    ("@GodotEngine",            "pixel_story",       4),
    ("@HeartBeast",             "pixel_story",       5),
    ("@AdamCYounis",            "pixel_story",       5),
    ("@MortMort",               "pixel_story",       4),
    ("@DaFluffyPotato",         "pixel_story",       4),
    ("@BramBlesvik",            "pixel_story",       4),
    ("@Jonas-Tyroller",         "pixel_story",       5),
    ("@Brackeys",               "pixel_story",       5),
    ("@Acerola0",               "pixel_story",       5),
    ("@GDQuest",                "pixel_story",       4),
    ("@BitBirdy",               "pixel_story",       5),

    # ── STORY ANIMATION ───────────────────────────────────────────────────
    ("@TheOdd1sOut",            "story_animation",   5),
    ("@jaidenanimations",       "story_animation",   5),
    ("@SomethingElseYT",        "story_animation",   5),
    ("@Haminations",            "story_animation",   5),
    ("@illymation",             "story_animation",   5),
    ("@GingerPale",             "story_animation",   5),
    ("@SwooZie",                "story_animation",   5),
    ("@Domics",                 "story_animation",   5),
    ("@LetMeExplainStudios",    "story_animation",   5),
    ("@itsalexclark",           "story_animation",   5),
    ("@danielthrasher",         "story_animation",   5),
    ("@StevenHe",               "story_animation",   5),
    ("@EddyBurback",            "story_animation",   5),
    ("@drewisgooden",           "story_animation",   5),
    ("@KurtisConner",           "story_animation",   5),
    ("@Danny-Gonzalez",         "story_animation",   5),
    ("@CasuallyExplained",      "story_animation",   5),

    # ── DRAMA / STORY SHORTS (Superficial2-style) ─────────────────────────
    ("@Superficial2",           "drama_story",       5),
    ("@StoryBooth",             "drama_story",       5),
    ("@TheActualFacts",         "drama_story",       5),
    ("@MyStoryAnimated",        "drama_story",       5),
    ("@StoryTimeAnimated",      "drama_story",       5),
    ("@MinuteVideos",           "drama_story",       5),
    ("@SideOfThemClouds",       "drama_story",       5),

    # ── PETTY REVENGE / KARMA / JUSTICE ──────────────────────────────────
    ("@ProRevenge",             "karma_revenge",     5),
    ("@MaliciousCompliance",    "karma_revenge",     5),
    ("@NuclearRevenge",         "karma_revenge",     5),
    ("@PettyRevenge",           "karma_revenge",     5),
    ("@InstantKarmaFails",      "karma_revenge",     5),
    ("@EntitledPeopleStories",  "karma_revenge",     5),
    ("@EntitledParents",        "karma_revenge",     5),
    ("@ChoosingBeggars",        "karma_revenge",     5),
    ("@WorkplaceRevenge",       "karma_revenge",     5),
    ("@DashcamInstantKarma",    "karma_revenge",     5),
    ("@ViralInstantKarma",      "karma_revenge",     5),

    # ── REDDIT STORY FORMAT ───────────────────────────────────────────────
    ("@RSlash",                 "reddit_story",      5),
    ("@AmITheJerk",             "reddit_story",      5),
    ("@StoriesFromReddit",      "reddit_story",      5),
    ("@ChoiceStories",          "reddit_story",      5),
    ("@BestofRSlash",           "reddit_story",      5),
    ("@AITAAnimate",            "reddit_story",      5),
    ("@AITAClips",              "reddit_story",      5),
    ("@RedditJustice",          "reddit_story",      5),

    # ── VIRAL SHORTS MASTERS ──────────────────────────────────────────────
    ("@JennyHoyos",             "viral_shorts",      5),
    ("@RyanTrahan",             "viral_shorts",      5),
    ("@ZackDFilms",             "viral_shorts",      5),
    ("@airrack",                "viral_shorts",      5),
    ("@CalebSimpson",           "viral_shorts",      5),
    ("@ColeyTV",                "viral_shorts",      5),
    ("@MrBeast",                "viral_shorts",      5),
    ("@KallmeKris",             "viral_shorts",      5),
    ("@MaxFosh",                "viral_shorts",      5),
    ("@ChrisWillx",             "viral_shorts",      5),
    ("@LukeDavidson",           "viral_shorts",      5),

    # ── CREATOR COACHES ───────────────────────────────────────────────────
    ("@creatorrant",            "creator_coach",     5),
    ("@JohnScottCreator",       "creator_coach",     5),
    ("@CreatorScience",         "creator_coach",     5),
    ("@FilmBooth",              "creator_coach",     5),
    ("@ColinAndSamir",          "creator_coach",     5),
    ("@VidIQ",                  "creator_coach",     4),
    ("@NickNimmin",             "creator_coach",     4),
    ("@MattDAvella",            "creator_coach",     4),
    ("@TheFutur",               "creator_coach",     4),
    ("@AliAbdaal",              "creator_coach",     4),

    # ── DOCUMENTARY / HOOK-HEAVY STORYTELLING ─────────────────────────────
    ("@Veritasium",             "doc_storytelling",  5),
    ("@MarkRober",              "doc_storytelling",  5),
    ("@3Blue1Brown",            "doc_storytelling",  5),
    ("@CGPGrey",                "doc_storytelling",  5),
    ("@Kurzgesagt",             "doc_storytelling",  5),
    ("@TomScott",               "doc_storytelling",  5),
    ("@Vox",                    "doc_storytelling",  4),
    ("@RealEngineering",        "doc_storytelling",  4),
    ("@LEMMiNO",                "doc_storytelling",  5),
    ("@Oversimplified",         "doc_storytelling",  5),
    ("@NerdWriter1",            "doc_storytelling",  5),
    ("@Primer",                 "doc_storytelling",  5),
    ("@Yes_Theory",             "doc_storytelling",  5),

    # ── HORROR / CREEPYPASTA ──────────────────────────────────────────────
    ("@ScaryInteresting",       "horror_story",      5),
    ("@UnsolvedMysteries",      "horror_story",      5),
    ("@NightmindOfficial",      "horror_story",      4),
    ("@SomeordinaryGamers",     "horror_story",      4),

    # ── SHORT FILM / SUSPENSE ─────────────────────────────────────────────
    ("@Omeleto",                "short_film",        5),
    ("@ShortoftheWeek",         "short_film",        5),
    ("@Dust_Sci_Fi",            "short_film",        5),
    ("@CorridorCrew",           "short_film",        5),
    ("@D4Dario",                "short_film",        5),

    # ── SCREENWRITING / NARRATIVE CRAFT ───────────────────────────────────
    ("@StudioBinder",           "screenwriting",     5),
    ("@TaleFoundry",            "screenwriting",     5),
    ("@KM_Weiland",             "screenwriting",     5),
    ("@EveryFrameAPainting",    "screenwriting",     5),
    ("@KaptainKristian",        "screenwriting",     5),
    ("@HelloFutureMe",          "screenwriting",     5),

    # ── WORLD BUILDING / LORE ─────────────────────────────────────────────
    ("@WorldbuildingNotes",     "worldbuilding",     5),
    ("@GeographyNow",           "worldbuilding",     4),
    ("@AlternateHistoryHub",    "worldbuilding",     4),
    ("@WhatiF",                 "worldbuilding",     4),

    # ── ENTREPRENEUR / BUSINESS ───────────────────────────────────────────
    ("@AlexHormozi",            "entrepreneur",      5),
    ("@MyFirstMillion",         "entrepreneur",      5),
    ("@GrahamStephan",          "entrepreneur",      4),
    ("@PatrickBetDavid",        "entrepreneur",      4),
    ("@SahilBloom",             "entrepreneur",      4),

    # ── PERSONAL STORY / CONFESSIONAL ────────────────────────────────────
    ("@AnthonyPadilla",         "personal_story",    5),
    ("@MichaelReeves",          "personal_story",    4),
    ("@ScottTheWoz",            "personal_story",    4),
    ("@WhistlinDiesel",         "personal_story",    4),
    ("@ContraPoints",           "personal_story",    4),
    ("@Philosophytube",         "personal_story",    4),

    # ── COMEDY SKETCH ────────────────────────────────────────────────────
    ("@TommyInnit",             "comedy",            4),
    ("@Jacksfilms",             "comedy",            4),
    ("@DankPods",               "comedy",            4),
]


# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT
# ─────────────────────────────────────────────────────────────────────────────

def checkpoint_path(video_id: str) -> Path:
    return CHECKPOINT_DIR / f"{video_id}.json"

def is_done(video_id: str) -> bool:
    return checkpoint_path(video_id).exists()

def save_checkpoint(data: dict):
    checkpoint_path(data["video_id"]).write_text(json.dumps(data, ensure_ascii=False))

def load_all_checkpoints() -> list[dict]:
    records = []
    for p in CHECKPOINT_DIR.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
            if not rec.get("error"):
                records.append(rec)
        except Exception:
            pass
    return records

VIDEO_ID_CACHE = Path("video_ids_cache.json")

def save_video_cache(videos: list):
    VIDEO_ID_CACHE.write_text(json.dumps(videos, ensure_ascii=False))

def load_video_cache() -> list | None:
    if not VIDEO_ID_CACHE.exists():
        return None
    try:
        return json.loads(VIDEO_ID_CACHE.read_text())
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# VIDEO ID DISCOVERY  (yt-dlp, no API key)
# ─────────────────────────────────────────────────────────────────────────────

def get_channel_videos(handle: str, max_videos: int = MAX_VIDEOS_PER_CH) -> list[dict]:
    """
    Get all video IDs from a channel using yt-dlp flat extraction.
    Tries the base channel URL first (works for all channels), then
    /shorts and /videos tabs as supplements to catch everything.
    """
    videos = []
    seen   = set()
    handle_clean = handle.lstrip("@")

    urls_to_try = [
        f"https://www.youtube.com/@{handle_clean}",          # all content — works for every channel
        f"https://www.youtube.com/@{handle_clean}/shorts",   # shorts tab if it exists
        f"https://www.youtube.com/@{handle_clean}/videos",   # long-form tab
    ]

    opts = {
        "quiet":        True,
        "no_warnings":  True,
        "ignoreerrors": True,
        "logger":       _Silent(),
        "extract_flat": "in_playlist",
        "playlistend":  max_videos,
    }

    for url in urls_to_try:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                for e in (info or {}).get("entries", []) or []:
                    if not e or not e.get("id"):
                        continue
                    vid_id = e["id"]
                    dur    = e.get("duration", 0) or 0
                    if vid_id in seen:
                        continue
                    if dur and dur > MAX_DURATION:
                        continue
                    seen.add(vid_id)
                    videos.append({
                        "video_id": vid_id,
                        "title":    e.get("title", ""),
                        "duration": dur,
                        "views":    e.get("view_count", 0) or 0,
                    })
        except Exception:
            pass

    return videos


# ─────────────────────────────────────────────────────────────────────────────
# TRANSCRIPT  (youtube-transcript-api — works on Colab, zero quota)
# ─────────────────────────────────────────────────────────────────────────────

_yta = YouTubeTranscriptApi()

def get_transcript(video_id: str) -> str:
    try:
        transcript_list = _yta.fetch(video_id, languages=["en", "en-US", "en-GB"])
        parts = [s.text for s in transcript_list if s.text]
        text  = " ".join(parts)
        text  = re.sub(r"\s+", " ", text).strip()
        return text if len(text.split()) >= MIN_TRANSCRIPT_WORDS else ""
    except (NoTranscriptFound, TranscriptsDisabled):
        return ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS  (yt-dlp — no API key, just slower than the API)
# ─────────────────────────────────────────────────────────────────────────────

def get_comments(video_id: str, max_comments: int = MAX_COMMENTS) -> list[dict]:
    opts = {
        "quiet":         True,
        "no_warnings":   True,
        "ignoreerrors":  True,
        "logger":        _Silent(),
        "skip_download": True,
        "getcomments":   max_comments,
        "extractor_args": {
            "youtube": {
                "comment_sort": ["top"],
                "max_comments": [str(max_comments)],
            }
        },
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        raw = info.get("comments") or []
        comments = []
        for c in raw:
            text = (c.get("text") or "").strip()
            if text:
                comments.append({
                    "text":    text,
                    "likes":   c.get("like_count", 0) or 0,
                    "replies": c.get("reply_count", 0) or 0,
                })
        comments.sort(key=lambda x: x["likes"], reverse=True)
        return comments[:max_comments]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# PER-VIDEO SCRAPE
# ─────────────────────────────────────────────────────────────────────────────

def scrape_video(video_id: str, channel: str, category: str, title: str = "") -> dict | None:
    if is_done(video_id):
        return None  # already checkpointed

    transcript = get_transcript(video_id)
    comments   = get_comments(video_id)

    rec = {
        "video_id":    video_id,
        "channel":     channel,
        "category":    category,
        "title":       title,
        "views":       0,     # views not available without API — comments fill the gap
        "transcript":  transcript,
        "comments":    comments,
        "comment_count_fetched": len(comments),
        "scraped_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_checkpoint(rec)
    return rec


# ─────────────────────────────────────────────────────────────────────────────
# TRAINING EXAMPLE BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a viral short-form video creator coach with deep expertise in "
    "YouTube Shorts storytelling, analytics, video feedback, and content strategy. "
    "You speak from real creator experience — direct, no fluff."
)

def _top_comments_text(comments: list, n: int = 25) -> str:
    good = [c for c in comments if c.get("likes", 0) >= 2 and c.get("text", "")]
    good.sort(key=lambda x: x["likes"], reverse=True)
    return "\n".join(
        f'[{i+1}] ({c["likes"]} 👍) "{c["text"].strip()}"'
        for i, c in enumerate(good[:n])
    )

def make_examples(rec: dict) -> list[dict]:
    transcript = rec.get("transcript", "").strip()
    comments   = rec.get("comments", [])
    title      = rec.get("title", "")
    channel    = rec.get("channel", "unknown")
    category   = rec.get("category", "")
    views      = rec.get("views", 0) or 0
    video_id   = rec["video_id"]

    good = [c for c in comments if c.get("likes", 0) >= 2 and c.get("text", "").strip()]
    good.sort(key=lambda x: x["likes"], reverse=True)
    top_str = _top_comments_text(comments, n=25)
    examples = []

    # Type 1: Transcript → script style
    if transcript and len(transcript.split()) >= MIN_TRANSCRIPT_WORDS:
        examples.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": f"Write a short-form video script in the style of @{channel} ({category.replace('_',' ').title()})."},
                {"role": "assistant", "content": transcript[:2000]},
            ],
            "source": f"transcript_{category}", "channel": channel,
            "video_id": video_id, "views": views, "weight": 3,
        })

    # Type 2: Transcript + comments → reaction analysis
    if transcript and len(good) >= 5:
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Short-form video transcript from @{channel} ({category.replace('_',' ')} niche):\n\n"
                    f'Title: "{title}"\n\nTRANSCRIPT:\n{transcript[:1200]}\n\n'
                    "What did the audience respond to most?"
                )},
                {"role": "assistant", "content": (
                    f"Top comments ({len(good)} total):\n\n{top_str}\n\n"
                    f"The audience responded most to the payoff. "
                    f"The most-liked comment ({good[0]['likes']} likes): "
                    f'"{good[0]["text"].strip()[:200]}"\n\n'
                    "That comment is the sentence your story was building toward. Write backwards from it."
                )},
            ],
            "source": "comment_reaction_analysis", "channel": channel,
            "video_id": video_id, "views": views, "weight": 3,
        })

    # Type 3: Story → predicted comments
    if transcript and len(good) >= 3:
        top3 = "\n".join(f'- "{c["text"].strip()[:150]}" ({c["likes"]} likes)' for c in good[:3])
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Predict viewer reactions in comments to this story:\n\n{transcript[:1000]}"},
                {"role": "assistant", "content": (
                    f"Actual top comments from @{channel}:\n\n{top3}\n\n"
                    "Pattern: the audience zeros in on the most surprising beat. "
                    "When you nail the payoff, viewers quote it verbatim. "
                    "That quoting = the algorithm's strongest replay signal."
                )},
            ],
            "source": "comment_prediction", "channel": channel,
            "video_id": video_id, "views": views, "weight": 3,
        })

    # Type 4: Magic moment (high engagement)
    if len(good) >= 10:
        top_c = good[0]
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Top comments from a @{channel} video:\n\n{top_str}\n\n"
                    f'Title: "{title}"\n\nWhat was the magic moment?'
                )},
                {"role": "assistant", "content": (
                    f"The most-liked comment ({top_c['likes']:,} likes) reveals everything:\n\n"
                    f'"{top_c["text"].strip()}"\n\n'
                    "That comment got those likes because it articulates exactly what every viewer felt but couldn't say. "
                    "That IS the magic moment — the payoff the whole story was building toward.\n\n"
                    "Key rule: the most-liked comment on any viral video = your story's payoff sentence. "
                    "Write your next script so the payoff produces exactly that reaction."
                )},
            ],
            "source": "magic_moment", "channel": channel,
            "video_id": video_id, "views": views, "weight": 4,
        })

    # Type 5: Comments-only hook (no transcript)
    if len(good) >= 10 and not transcript:
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Comments from a @{channel} video:\n\n{top_str}\n\nWhat story hook produced these reactions?"},
                {"role": "assistant", "content": (
                    f"These comments reveal the hook pattern. The dominant reaction — "
                    f'"{good[0]["text"].strip()[:100]}" — means the video opened with immediate stakes and unresolved tension. '
                    "Comments like these only appear when:\n"
                    "1. The hook promises something people genuinely want resolved\n"
                    "2. The payoff delivers beyond expectation\n"
                    "3. The ending is so clean that viewers want to quote it\n\n"
                    "Replicate this by starting with the payoff moment in mind, then work backwards to the hook."
                )},
            ],
            "source": "comments_only_hook", "channel": channel,
            "video_id": video_id, "views": views, "weight": 2,
        })

    return examples


# ─────────────────────────────────────────────────────────────────────────────
# COLAB AUTO-DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────

def _colab_download(paths: list):
    try:
        from google.colab import files as colab_files
        import zipfile
        print("\n📥 Zipping outputs for download...")
        zip_path = Path("ytllm_outputs.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                p = Path(p)
                if p.exists():
                    zf.write(p, p.name)
                    print(f"   + {p.name}  ({p.stat().st_size / 1_048_576:.1f} MB)")
        print(f"\n⬇️  Downloading {zip_path.name} to your laptop...")
        colab_files.download(str(zip_path))
    except ImportError:
        pass  # not in Colab — skip silently


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n🚀 scrape_everything.py — yt-dlp Full Scraper (no API key)")
    print("=" * 60)
    print(f"   Channels:       {len(CHANNELS)}")
    print(f"   Videos/channel: ALL (no cap)")
    print(f"   Max comments:   {MAX_COMMENTS} per video")
    print(f"   Workers:        {WORKERS}")
    print()

    # ── Step 1: Collect all video IDs (cached — instant on resume) ───────
    cached = load_video_cache()
    if cached:
        unique = cached
        print(f"📋 Step 1/3 — Loaded {len(unique):,} video IDs from cache (skipping channel scan)")
    else:
        print("📋 Step 1/3 — Collecting video IDs from all channels...")
        all_videos = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(get_channel_videos, handle, MAX_VIDEOS_PER_CH): (handle, cat)
                for handle, cat, _ in CHANNELS
            }
            with tqdm(total=len(futures), desc="Channels", unit="ch") as pbar:
                for future in as_completed(futures):
                    handle, cat = futures[future]
                    channel_name = handle.lstrip("@")
                    try:
                        vids = future.result()
                        for v in vids:
                            v["channel"]  = channel_name
                            v["category"] = cat
                        all_videos.extend(vids)
                    except Exception:
                        pass
                    pbar.update(1)

        # Deduplicate
        seen, unique = set(), []
        for v in all_videos:
            if v["video_id"] not in seen:
                seen.add(v["video_id"])
                unique.append(v)

        save_video_cache(unique)
        print(f"\n   Found:  {len(unique):,} unique videos across {len(CHANNELS)} channels")
        print(f"   Saved to video_ids_cache.json — future runs skip this step")

    already_done = {p.stem for p in CHECKPOINT_DIR.glob("*.json")}
    todo = [v for v in unique if v["video_id"] not in already_done]

    print(f"   Done:         {len(already_done):,} already checkpointed")
    print(f"   Remaining:    {len(todo):,} to scrape")
    print()

    # ── Step 2: Transcripts + comments ───────────────────────────────────
    print("📥 Step 2/3 — Fetching transcripts + comments (this is the long part)...")
    stats = defaultdict(int)

    def _worker(v):
        return scrape_video(v["video_id"], v["channel"], v["category"], v.get("title", ""))

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_worker, v): v for v in todo}
        with tqdm(total=len(futures), desc="Videos", unit="v") as pbar:
            for future in as_completed(futures):
                try:
                    rec = future.result()
                    if rec is None:
                        stats["skip"] += 1
                    else:
                        stats["ok"] += 1
                        if rec.get("transcript"): stats["with_transcript"] += 1
                        if rec.get("comments"):   stats["with_comments"] += 1
                    pbar.set_postfix(
                        ok=stats["ok"],
                        trans=stats["with_transcript"],
                        cmts=stats["with_comments"],
                    )
                except Exception:
                    stats["error"] += 1
                finally:
                    pbar.update(1)

    print(f"\n   ✅ Scraped:          {stats['ok']:,}")
    print(f"   📝 With transcript:  {stats['with_transcript']:,}")
    print(f"   💬 With comments:    {stats['with_comments']:,}")
    print(f"   ⏭️  Skipped:          {stats['skip']:,}")
    print(f"   ❌ Errors:           {stats['error']:,}")
    print()

    # ── Step 3: Build training data ───────────────────────────────────────
    print("🔨 Step 3/3 — Building training data...")
    all_records = load_all_checkpoints()
    all_examples = []

    for rec in tqdm(all_records, desc="Building", unit="v"):
        all_examples.extend(make_examples(rec))

    # Write outputs
    with open(OUT_RAW, "w") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(OUT_TRAINING, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    v7  = Path("training_data_v7_clean.jsonl")
    v8  = Path("training_data_v8.jsonl")
    merged = 0
    with open(v8, "w") as f:
        if v7.exists():
            for line in v7.read_text().splitlines():
                if line.strip():
                    f.write(line + "\n"); merged += 1
        for ex in all_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n"); merged += 1

    type_counts = Counter(ex["source"]            for ex in all_examples)
    cat_counts  = Counter(ex.get("category", "?") for ex in all_examples)
    ch_counts   = Counter(ex["channel"]            for ex in all_examples)

    print(f"\n{'='*60}")
    print(f"✅ COMPLETE")
    print(f"   Video records:        {len(all_records):,}")
    print(f"   Training examples:    {len(all_examples):,}")
    print(f"   v8 total (with v7):   {merged:,}")
    print()
    print("📊 By example type:")
    for src, cnt in type_counts.most_common():
        print(f"   {src:35s} {cnt:>6,}")
    print()
    print("📊 By category (top 10):")
    for cat, cnt in cat_counts.most_common(10):
        print(f"   {cat:30s} {cnt:>6,}")
    print()
    print("📊 Top 10 channels:")
    for ch, cnt in ch_counts.most_common(10):
        print(f"   {ch:30s} {cnt:>6,}")
    print()
    print(f"💾 everything_raw.jsonl       ← raw data")
    print(f"💾 everything_training.jsonl  ← training examples")
    print(f"💾 training_data_v8.jsonl     ← merged, ready to fine-tune")

    _colab_download([v8, OUT_TRAINING, OUT_RAW])


if __name__ == "__main__":
    main()
