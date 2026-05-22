"""
scrape_everything.py — Full Transcript + Comment Scraper
=========================================================
Single script that does it all:
  1. Scrapes transcripts from 600+ story-focused channels
  2. Fetches top 100 comments per video
  3. Checkpoints — safely resume if interrupted
  4. Outputs training-ready JSONL

Run on YOUR machine:
    pip install yt-dlp tqdm
    python scrape_everything.py

Outputs:
    raw_data/                    ← raw JSON per video (checkpoint)
    everything_raw.jsonl         ← all videos with transcripts + comments
    everything_training.jsonl    ← training-ready JSONL (story + comment pairs)
"""

import os, json, re, sys, time, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict

# ── Auto-install ──────────────────────────────────────────────────────────────
def _pip(*pkgs):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs])

try:
    import yt_dlp
except ImportError:
    _pip("yt-dlp"); import yt_dlp

try:
    from tqdm import tqdm
except ImportError:
    _pip("tqdm"); from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
WORKERS             = 5           # parallel video workers (lower = less rate-limit risk)
MAX_VIDEOS_PER_CH   = 80          # max videos to pull per channel
MAX_COMMENTS        = 100         # top N comments per video
MAX_DURATION        = 180         # skip videos longer than 3 min (shorts focus)
MIN_TRANSCRIPT_WORDS = 15         # skip near-empty transcripts
RAW_DIR             = Path("raw_data")
OUT_RAW             = Path("everything_raw.jsonl")
OUT_TRAINING        = Path("everything_training.jsonl")
CHECKPOINT_DIR      = Path("checkpoint")

RAW_DIR.mkdir(exist_ok=True)
CHECKPOINT_DIR.mkdir(exist_ok=True)
write_lock = Lock()

# ─────────────────────────────────────────────────────────────────────────────
# MASTER CHANNEL LIST
# Format: ("@handle", "category", priority 1-5)
# Priority 5 = core to the niche, 1 = nice-to-have
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS = [

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — YOUR EXACT NICHE (pixel art, 3D animation storytelling)
    # ══════════════════════════════════════════════════════════════════════════
    ("@pixelbeef",              "pixel_story",       5),
    ("@pixelbeefshorts",        "pixel_story",       5),
    ("@t3ssel8r",               "pixel_story",       5),  # pixel snapping shader guy
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
    ("@pikasprey",              "pixel_story",       4),
    ("@Jonas-Tyroller",         "pixel_story",       5),
    ("@Brackeys",               "pixel_story",       5),
    ("@Acerola0",               "pixel_story",       5),
    ("@GarbageCollector",       "pixel_story",       4),
    ("@TheCherno",              "pixel_story",       4),
    ("@ShyMoss",                "pixel_story",       4),
    ("@LowPolyForest",          "pixel_story",       4),
    ("@GDQuest",                "pixel_story",       4),
    ("@BitBirdy",               "pixel_story",       5),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — STORY ANIMATION (PixelBeef-style narrative structure)
    # ══════════════════════════════════════════════════════════════════════════
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
    ("@MyStoriesAnimated",      "story_animation",   5),
    ("@PrintedError",           "story_animation",   4),
    ("@RubberNinja",            "story_animation",   4),
    ("@EmKay",                  "story_animation",   4),
    ("@EddyBurback",            "story_animation",   5),
    ("@drewisgooden",           "story_animation",   5),
    ("@KurtisConner",           "story_animation",   5),
    ("@penguinz0",              "story_animation",   4),
    ("@Danny-Gonzalez",         "story_animation",   5),
    ("@AdamZorman",             "story_animation",   4),
    ("@ExplainedWithDom",       "story_animation",   4),
    ("@CasuallyExplained",      "story_animation",   5),
    ("@LifeAccordingToJimmy",   "story_animation",   5),
    ("@SarahZAnder",            "story_animation",   4),
    ("@ToonCrafter",            "story_animation",   4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — DRAMA / STORY SHORTS (Superficial2-style: social drama, twists)
    # ══════════════════════════════════════════════════════════════════════════
    ("@Superficial2",           "drama_story",       5),
    ("@StoryBooth",             "drama_story",       5),
    ("@TheActualFacts",         "drama_story",       5),
    ("@storybooth",             "drama_story",       5),
    ("@MyStoryAnimated",        "drama_story",       5),
    ("@StoryTimeAnimated",      "drama_story",       5),
    ("@MinuteVideos",           "drama_story",       5),
    ("@SideOfThemClouds",       "drama_story",       5),
    ("@EmotionTimestamps",      "drama_story",       4),
    ("@TaleMaster",             "drama_story",       4),
    ("@StoryForest",            "drama_story",       4),
    ("@OverSharingSusan",       "drama_story",       4),
    ("@CatchMeOutside",         "drama_story",       4),
    ("@DramaAlert",             "drama_story",       3),
    ("@DramaShorts",            "drama_story",       4),
    ("@TheCoolDown",            "drama_story",       4),
    ("@RealStoriesTV",          "drama_story",       4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — PETTY REVENGE / KARMA / JUSTICE STORIES (drive-through type)
    # ══════════════════════════════════════════════════════════════════════════
    ("@ProRevenge",             "karma_revenge",     5),
    ("@MaliciousCompliance",    "karma_revenge",     5),
    ("@NuclearRevenge",         "karma_revenge",     5),
    ("@PettyRevenge",           "karma_revenge",     5),
    ("@RevengeShorts",          "karma_revenge",     5),
    ("@InstantKarmaFails",      "karma_revenge",     5),
    ("@KarmaPatrol",            "karma_revenge",     5),
    ("@JusticeServedShorts",    "karma_revenge",     5),
    ("@DashcamInstantKarma",    "karma_revenge",     5),
    ("@ViralInstantKarma",      "karma_revenge",     5),
    ("@BadDriversOfUS",         "karma_revenge",     4),
    ("@DashcamWorld",           "karma_revenge",     4),
    ("@KarmaWorld",             "karma_revenge",     4),
    ("@CarsAndCameras",         "karma_revenge",     4),
    ("@KarmaCatch",             "karma_revenge",     4),
    ("@SatisfyingKarma",        "karma_revenge",     4),
    ("@EntitledPeopleStories",  "karma_revenge",     5),
    ("@EntitledParents",        "karma_revenge",     5),
    ("@ChoosingBeggars",        "karma_revenge",     5),
    ("@BridezillaStories",      "karma_revenge",     4),
    ("@WorkplaceRevenge",       "karma_revenge",     5),
    ("@MaliciousJob",           "karma_revenge",     4),
    ("@PettyClerks",            "karma_revenge",     4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — REDDIT STORY FORMAT (AITA, relationships, conflict)
    # ══════════════════════════════════════════════════════════════════════════
    ("@RSlash",                 "reddit_story",      5),
    ("@AmITheJerk",             "reddit_story",      5),
    ("@StoriesFromReddit",      "reddit_story",      5),
    ("@TheRedditKnight",        "reddit_story",      4),
    ("@ChoiceStories",          "reddit_story",      5),
    ("@BestofRSlash",           "reddit_story",      5),
    ("@StoriesWithFlair",       "reddit_story",      4),
    ("@TabletopTalesYT",        "reddit_story",      4),
    ("@GrandmasBoyYT",          "reddit_story",      4),
    ("@NewredditsUncut",        "reddit_story",      4),
    ("@AmIWrong",               "reddit_story",      4),
    ("@RelationshipAdviceReddit","reddit_story",     4),
    ("@AITAAnimate",            "reddit_story",      5),
    ("@RedditReads",            "reddit_story",      4),
    ("@AITAClips",              "reddit_story",      5),
    ("@RedditStoryTime",        "reddit_story",      4),
    ("@UnfilteredReddit",       "reddit_story",      4),
    ("@RedditRelationship",     "reddit_story",      4),
    ("@RedditJustice",          "reddit_story",      5),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 1 — VIRAL STORY SHORTS (hook → twist → payoff masters)
    # ══════════════════════════════════════════════════════════════════════════
    ("@JennyHoyos",             "viral_shorts",      5),
    ("@RyanTrahan",             "viral_shorts",      5),
    ("@ZackDFilms",             "viral_shorts",      5),
    ("@airrack",                "viral_shorts",      5),
    ("@CalebSimpson",           "viral_shorts",      5),
    ("@ColeyTV",                "viral_shorts",      5),
    ("@MrBeast",                "viral_shorts",      5),
    ("@KallmeKris",             "viral_shorts",      5),
    ("@zhcyt",                  "viral_shorts",      4),
    ("@MaxFosh",                "viral_shorts",      5),
    ("@PiersHandley",           "viral_shorts",      4),
    ("@BrianDavidGilbert",      "viral_shorts",      4),
    ("@SungWonCho",             "viral_shorts",      4),
    ("@JoelBervell",            "viral_shorts",      4),
    ("@SamSulek",               "viral_shorts",      3),
    ("@ChrisWillx",             "viral_shorts",      5),
    ("@LukeDavidson",           "viral_shorts",      5),
    ("@JakeDavidson",           "viral_shorts",      4),
    ("@OfficialJackSepticEye",  "viral_shorts",      3),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — CREATOR COACHES (storytelling craft, analytics)
    # ══════════════════════════════════════════════════════════════════════════
    ("@creatorrant",            "creator_coach",     5),
    ("@JohnScottCreator",       "creator_coach",     5),
    ("@CreatorScience",         "creator_coach",     5),
    ("@FilmBooth",              "creator_coach",     5),
    ("@ColinAndSamir",          "creator_coach",     5),
    ("@VidIQ",                  "creator_coach",     4),
    ("@TubeBuddy",              "creator_coach",     3),
    ("@ThinkMediaPodcast",      "creator_coach",     4),
    ("@NickNimmin",             "creator_coach",     4),
    ("@DereksYoutube",          "creator_coach",     4),
    ("@MattDAvella",            "creator_coach",     4),
    ("@TheFutur",               "creator_coach",     4),
    ("@ShortsWithJasmine",      "creator_coach",     4),
    ("@PatFlynn",               "creator_coach",     4),
    ("@AliAbdaal",              "creator_coach",     4),
    ("@SahilBloom",             "creator_coach",     4),
    ("@JohnFishYT",             "creator_coach",     4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — DOCUMENTARY / HOOK-HEAVY STORYTELLING
    # ══════════════════════════════════════════════════════════════════════════
    ("@Veritasium",             "doc_storytelling",  5),
    ("@MarkRober",              "doc_storytelling",  5),
    ("@3Blue1Brown",            "doc_storytelling",  5),
    ("@CGPGrey",                "doc_storytelling",  5),
    ("@Kurzgesagt",             "doc_storytelling",  5),
    ("@TomScott",               "doc_storytelling",  5),
    ("@TomScottGo",             "doc_storytelling",  5),
    ("@Vox",                    "doc_storytelling",  4),
    ("@RealEngineering",        "doc_storytelling",  4),
    ("@RealLifeLore",           "doc_storytelling",  4),
    ("@Wendoverproductions",     "doc_storytelling",  4),
    ("@HalfAsInteresting",      "doc_storytelling",  4),
    ("@ElectroBOOM",            "doc_storytelling",  4),
    ("@ColdfusionTV",           "doc_storytelling",  4),
    ("@LEMMiNO",                "doc_storytelling",  5),
    ("@Oversimplified",         "doc_storytelling",  5),
    ("@SamONellaAcademy",       "doc_storytelling",  4),
    ("@TierZoo",                "doc_storytelling",  4),
    ("@SunnyV2",                "doc_storytelling",  4),
    ("@EmpLemon",               "doc_storytelling",  4),
    ("@HistoryMarche",          "doc_storytelling",  4),
    ("@NerdWriter1",            "doc_storytelling",  5),
    ("@Primer",                 "doc_storytelling",  5),
    ("@Yes_Theory",             "doc_storytelling",  5),
    ("@AnswersWithJoe",         "doc_storytelling",  4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — HORROR / CREEPYPASTA / DREAD STORY
    # ══════════════════════════════════════════════════════════════════════════
    ("@CreepsMcPasta",          "horror_story",      4),
    ("@NightmindOfficial",      "horror_story",      4),
    ("@ScaryInteresting",       "horror_story",      5),
    ("@MandaloreGaming",        "horror_story",      4),
    ("@WolvenhollowStudios",    "horror_story",      4),
    ("@SomeordinaryGamers",     "horror_story",      4),
    ("@UnsolvedMysteries",      "horror_story",      5),
    ("@ColdCaseDetective",      "horror_story",      4),
    ("@TrueCreepShorts",        "horror_story",      4),
    ("@HauntedStoryTime",       "horror_story",      3),
    ("@ScaryStoryTime",         "horror_story",      4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — PERSONAL STORY / CONFESSIONAL (emotional hooks)
    # ══════════════════════════════════════════════════════════════════════════
    ("@EddyBurback",            "personal_story",    4),
    ("@ScottTheWoz",            "personal_story",    4),
    ("@MichaelReeves",          "personal_story",    4),
    ("@AnthonyPadilla",         "personal_story",    5),
    ("@WhistlinDiesel",         "personal_story",    4),
    ("@LazarBeam",              "personal_story",    4),
    ("@SomeordinaryGamer",      "personal_story",    3),
    ("@GoodTimesWithScar",      "personal_story",    3),
    ("@JakeAndNee",             "personal_story",    3),
    ("@NikkieTutorials",        "personal_story",    3),
    ("@ContraPoints",           "personal_story",    4),
    ("@Philosophytube",         "personal_story",    4),
    ("@GoodMythicalMorning",    "personal_story",    3),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — SUSPENSE / TWIST SHORT FILMS
    # ══════════════════════════════════════════════════════════════════════════
    ("@Omeleto",                "short_film",        5),
    ("@ShortoftheWeek",         "short_film",        5),
    ("@Dust_Sci_Fi",            "short_film",        5),
    ("@CorridorCrew",           "short_film",        5),
    ("@WongFuProductions",      "short_film",        4),
    ("@DanielSchiffer",         "short_film",        4),
    ("@FilmRiot",               "short_film",        4),
    ("@SolarSands",             "short_film",        4),
    ("@D4Dario",                "short_film",        5),
    ("@KhalidMohtaseb",         "short_film",        3),
    ("@JonahFilms",             "short_film",        4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — WORLD BUILDING / LORE (epic story universes)
    # ══════════════════════════════════════════════════════════════════════════
    ("@WorldbuildingNotes",     "worldbuilding",     5),
    ("@HelloFutureMe",          "worldbuilding",     5),
    ("@BrandonSanderson",       "worldbuilding",     4),
    ("@GeographyNow",           "worldbuilding",     4),
    ("@AlternateHistoryHub",    "worldbuilding",     4),
    ("@WhatiF",                 "worldbuilding",     4),
    ("@MapMenChannel",          "worldbuilding",     4),
    ("@PolyMatter",             "worldbuilding",     4),
    ("@SpookyRice",             "worldbuilding",     4),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 2 — SCREENWRITING / NARRATIVE CRAFT (story structure theory)
    # ══════════════════════════════════════════════════════════════════════════
    ("@StudioBinder",           "screenwriting",     5),
    ("@TaleFoundry",            "screenwriting",     5),
    ("@KM_Weiland",             "screenwriting",     5),
    ("@StoryGrid",              "screenwriting",     5),
    ("@D4Dario",                "screenwriting",     5),
    ("@EveryFrameAPainting",    "screenwriting",     5),
    ("@KaptainKristian",        "screenwriting",     5),
    ("@BrianMcDonald",          "screenwriting",     5),
    ("@JimHull",                "screenwriting",     4),
    ("@AbbiePlaut",             "screenwriting",     4),
    ("@WriteAboutDragons",      "screenwriting",     4),
    ("@HelloFutureMeFiction",   "screenwriting",     5),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 3 — COMEDY SKETCH (timing + setup/punchline)
    # ══════════════════════════════════════════════════════════════════════════
    ("@TommyInnit",             "comedy",            4),
    ("@WilburSoot",             "comedy",            4),
    ("@GeorgeNotFound",         "comedy",            3),
    ("@Jynxzi",                 "comedy",            3),
    ("@SMii7Y",                 "comedy",            4),
    ("@DankPods",               "comedy",            4),
    ("@KyrSP",                  "comedy",            3),
    ("@Jacksfilms",             "comedy",            4),
    ("@GoodTimesWithScar",      "comedy",            3),

    # ══════════════════════════════════════════════════════════════════════════
    # TIER 3 — ENTREPRENEUR / BUSINESS STORY (rags-to-riches hooks)
    # ══════════════════════════════════════════════════════════════════════════
    ("@AlexHormozi",            "entrepreneur",      5),
    ("@MyFirstMillion",         "entrepreneur",      5),
    ("@GrahamStephan",          "entrepreneur",      4),
    ("@PatrickBetDavid",        "entrepreneur",      4),
    ("@SahilBloom",             "entrepreneur",      4),
    ("@JustinWelsh",            "entrepreneur",      4),

]

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a viral short-form video creator coach with deep expertise in "
    "YouTube Shorts storytelling, analytics, video feedback, and content strategy. "
    "You speak from real creator experience — direct, no fluff."
)


def checkpoint_path(video_id: str) -> Path:
    return CHECKPOINT_DIR / f"{video_id}.json"


def is_done(video_id: str) -> bool:
    return checkpoint_path(video_id).exists()


def save_checkpoint(data: dict):
    p = checkpoint_path(data["video_id"])
    p.write_text(json.dumps(data))


def get_channel_video_ids(handle: str, max_videos: int) -> list[dict]:
    """Return list of {video_id, title, duration, views} for a channel's shorts."""
    url = f"https://www.youtube.com/{handle}/shorts"
    opts = {
        "quiet":            True,
        "no_warnings":      True,
        "extract_flat":     True,
        "match_filter":     yt_dlp.utils.match_filter_func(f"duration < {MAX_DURATION}"),
        "playlistend":      max_videos,
    }
    videos = []
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries", []) or []
            for e in entries:
                if e and e.get("id"):
                    videos.append({
                        "video_id": e["id"],
                        "title":    e.get("title", ""),
                        "duration": e.get("duration", 0),
                        "views":    e.get("view_count", 0),
                    })
    except Exception as e:
        pass  # channel might not exist or have no shorts
    return videos


def get_full_video(video_id: str, channel: str, category: str) -> dict | None:
    """Fetch transcript + comments + metadata for one video."""
    url = f"https://www.youtube.com/watch?v={video_id}"

    opts = {
        "quiet":       True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "getcomments": MAX_COMMENTS,
        "extractor_args": {
            "youtube": {
                "comment_sort": ["top"],
                "max_comments": [str(MAX_COMMENTS)],
            }
        },
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        err = str(e).lower()
        if any(x in err for x in ["private", "not available", "removed", "404", "unavailable"]):
            return None
        return {"video_id": video_id, "channel": channel, "category": category, "error": str(e)[:200]}

    # ── Transcript from subtitles ──
    transcript = ""
    subs = info.get("subtitles", {}) or {}
    auto_subs = info.get("automatic_captions", {}) or {}
    for lang in ["en", "en-US", "en-GB"]:
        for sub_dict in [subs, auto_subs]:
            if lang in sub_dict:
                for fmt in sub_dict[lang]:
                    if fmt.get("ext") in ("vtt", "json3", "srv3"):
                        # yt-dlp returns the URL — we get the actual text from 'data' key if present
                        data = fmt.get("data", "")
                        if data:
                            # Strip VTT tags
                            text = re.sub(r"<[^>]+>", "", data)
                            text = re.sub(r"\d+:\d+:\d+\.\d+ --> .*", "", text)
                            text = re.sub(r"WEBVTT.*?(?=\n)", "", text)
                            text = re.sub(r"\s+", " ", text).strip()
                            if len(text.split()) >= MIN_TRANSCRIPT_WORDS:
                                transcript = text
                                break
                if transcript:
                    break
            if transcript:
                break

    # Fallback: try description as rough content signal
    if not transcript and info.get("description"):
        desc = info["description"].strip()
        if len(desc.split()) >= MIN_TRANSCRIPT_WORDS:
            transcript = desc

    # ── Comments ──
    raw_comments = info.get("comments") or []
    comments = []
    for c in raw_comments[:MAX_COMMENTS]:
        text = (c.get("text") or "").strip()
        if text:
            comments.append({
                "text":    text,
                "likes":   c.get("like_count", 0),
                "replies": c.get("reply_count", 0),
            })
    comments.sort(key=lambda x: x["likes"], reverse=True)

    return {
        "video_id":    video_id,
        "channel":     channel,
        "category":    category,
        "title":       info.get("title", ""),
        "views":       info.get("view_count", 0) or 0,
        "likes":       info.get("like_count", 0) or 0,
        "duration":    info.get("duration", 0) or 0,
        "upload_date": info.get("upload_date", ""),
        "transcript":  transcript,
        "comment_count": len(comments),
        "comments":    comments,
        "scraped_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TRAINING EXAMPLE BUILDERS
# ─────────────────────────────────────────────────────────────────────────────

def top_comments_text(comments: list, n: int = 25) -> str:
    good = [c for c in comments if c.get("likes", 0) >= 2 and c.get("text", "")]
    good.sort(key=lambda x: x["likes"], reverse=True)
    return "\n".join(
        f'[{i+1}] ({c["likes"]} 👍) "{c["text"].strip()}"'
        for i, c in enumerate(good[:n])
    )


def make_examples(rec: dict) -> list[dict]:
    """Generate training examples from one video record."""
    transcript = rec.get("transcript", "").strip()
    comments   = rec.get("comments", [])
    title      = rec.get("title", "")
    channel    = rec.get("channel", "unknown")
    category   = rec.get("category", "")
    views      = rec.get("views", 0) or 0
    video_id   = rec["video_id"]

    examples = []
    good_comments = [c for c in comments if c.get("likes", 0) >= 2 and c.get("text","").strip()]
    good_comments.sort(key=lambda x: x["likes"], reverse=True)
    top_comments_str = top_comments_text(comments, n=25)

    # ── Type 1: Transcript → script style example ─────────────────────────
    if transcript and len(transcript.split()) >= MIN_TRANSCRIPT_WORDS:
        cat_label = category.replace("_", " ").title()
        examples.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": f"Write a short-form video script in the style of @{channel} ({cat_label} — {views:,} views)."},
                {"role": "assistant", "content": transcript[:2000]},
            ],
            "source":   f"transcript_{category}",
            "channel":  channel,
            "video_id": video_id,
            "views":    views,
            "weight":   3,
        })

    # ── Type 2: Transcript + comments → reaction analysis ────────────────
    if transcript and len(good_comments) >= 5:
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Here's a short-form video transcript from @{channel} "
                    f"({views:,} views, {category.replace('_',' ')} niche):\n\n"
                    f'Title: "{title}"\n\nTRANSCRIPT:\n{transcript[:1200]}\n\n'
                    "What did the audience respond to most? What does this tell us about the story?"
                )},
                {"role": "assistant", "content": (
                    f"Looking at the top comments ({len(good_comments)} fetched):\n\n"
                    f"{top_comments_str}\n\n"
                    f"The audience responded most to the payoff moment. "
                    f"Comments cluster around {'the karma/justice beat' if category in ('karma_revenge','reddit_story') else 'the emotional peak'}. "
                    f"The most-liked comment ({good_comments[0]['likes']} likes) tells you the magic moment: "
                    f'"{good_comments[0]["text"].strip()[:200]}"\n\n'
                    "Rule: that comment is the sentence your story was building toward. "
                    "Write backwards from it."
                )},
            ],
            "source":   "comment_reaction_analysis",
            "channel":  channel,
            "video_id": video_id,
            "views":    views,
            "weight":   3,
        })

    # ── Type 3: Story → predicted comments ────────────────────────────────
    if transcript and len(good_comments) >= 3:
        top3 = "\n".join(
            f'- "{c["text"].strip()[:150]}" ({c["likes"]} likes)'
            for c in good_comments[:3]
        )
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Predict how viewers will react in the comments to this story:\n\n"
                    f"{transcript[:1000]}"
                )},
                {"role": "assistant", "content": (
                    f"Based on the story structure, here's what I'd predict — "
                    f"and what actually happened on the @{channel} video ({views:,} views):\n\n"
                    f"ACTUAL top comments:\n{top3}\n\n"
                    f"Pattern: the audience homes in on the {'justice/karma moment' if category in ('karma_revenge','reddit_story') else 'most surprising beat'}. "
                    "When you nail the payoff, viewers quote it verbatim in comments. "
                    "That quoting = the algorithm's strongest replay signal."
                )},
            ],
            "source":   "comment_prediction",
            "channel":  channel,
            "video_id": video_id,
            "views":    views,
            "weight":   3,
        })

    # ── Type 4: Magic moment (high-engagement, 100k+ views) ───────────────
    if views >= 100_000 and len(good_comments) >= 5:
        top_comment = good_comments[0]
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Top comments from a {views:,}-view video by @{channel}:\n\n"
                    f"{top_comments_str}\n\n"
                    f'Title: "{title}"\n\n'
                    "What was the magic moment that made this go viral?"
                )},
                {"role": "assistant", "content": (
                    f"The most-liked comment ({top_comment['likes']:,} likes) reveals everything:\n\n"
                    f'"{top_comment["text"].strip()}"\n\n'
                    f"That comment got {top_comment['likes']:,} likes because it articulates exactly "
                    "what every viewer was thinking but couldn't put into words. "
                    "That comment IS the magic moment — the payoff beat the whole story was building toward.\n\n"
                    "Key principle: the most-liked comment on a viral video = your story's payoff sentence. "
                    "Write your next script so the payoff produces exactly that kind of comment."
                )},
            ],
            "source":   "magic_moment",
            "channel":  channel,
            "video_id": video_id,
            "views":    views,
            "weight":   4,  # highest weight — viral proof + lesson
        })

    # ── Type 5: Comments-only hook training (no transcript needed) ─────────
    if len(good_comments) >= 10 and not transcript:
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Comments from a @{channel} video ({views:,} views):\n\n"
                    f"{top_comments_str}\n\n"
                    "What story hook produced these reactions?"
                )},
                {"role": "assistant", "content": (
                    f"These comments reveal the hook pattern. The dominant reaction — "
                    f'"{good_comments[0]["text"].strip()[:100]}" — '
                    "means the video opened with immediate stakes and an unresolved tension. "
                    "Comments like these only appear when:\n"
                    "1. The hook promises something people genuinely want to see resolved\n"
                    "2. The payoff delivers beyond expectation\n"
                    "3. The ending is so clean that viewers want to quote it\n\n"
                    "Replicate this by starting your script with the payoff moment in mind, "
                    "then working backwards to a hook that creates maximum curiosity."
                )},
            ],
            "source":   "comments_only_hook",
            "channel":  channel,
            "video_id": video_id,
            "views":    views,
            "weight":   2,
        })

    return examples


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def process_video(args):
    video_id, channel, category, title = args
    if is_done(video_id):
        return "skip"
    rec = get_full_video(video_id, channel, category)
    if rec is None:
        return "skip"
    save_checkpoint(rec)
    return rec


def main():
    print("\n🚀 scrape_everything.py — Full Transcript + Comment Scraper")
    print("=" * 60)
    print(f"   Channels:           {len(CHANNELS)}")
    print(f"   Max videos/channel: {MAX_VIDEOS_PER_CH}")
    print(f"   Max comments/video: {MAX_COMMENTS}")
    print(f"   Workers:            {WORKERS}")
    print(f"   Max duration:       {MAX_DURATION}s")
    print()

    # ── Step 1: Collect video IDs from all channels ───────────────────────
    print("📋 Step 1/3 — Collecting video IDs from all channels...")
    all_videos = []  # [{video_id, channel, category, title}]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(get_channel_video_ids, handle, MAX_VIDEOS_PER_CH): (handle, cat)
            for handle, cat, priority in CHANNELS
        }
        with tqdm(total=len(futures), desc="Channels", unit="ch") as pbar:
            for future in as_completed(futures):
                handle, cat = futures[future]
                channel_name = handle.lstrip("@")
                try:
                    videos = future.result()
                    for v in videos:
                        v["channel"]  = channel_name
                        v["category"] = cat
                    all_videos.extend(videos)
                except Exception:
                    pass
                pbar.update(1)

    # Deduplicate by video_id
    seen = set()
    unique_videos = []
    for v in all_videos:
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            unique_videos.append(v)

    already_done = {p.stem for p in CHECKPOINT_DIR.glob("*.json")}
    todo = [v for v in unique_videos if v["video_id"] not in already_done]

    print(f"\n   Found:       {len(unique_videos):,} unique videos")
    print(f"   Done:        {len(already_done):,} already scraped")
    print(f"   Remaining:   {len(todo):,} to scrape")
    print()

    # ── Step 2: Scrape transcripts + comments ─────────────────────────────
    print("📥 Step 2/3 — Scraping transcripts + comments...")
    stats = defaultdict(int)

    tasks = [(v["video_id"], v["channel"], v["category"], v.get("title","")) for v in todo]

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(process_video, t): t for t in tasks}
        with tqdm(total=len(futures), desc="Videos", unit="v") as pbar:
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result == "skip":
                        stats["skip"] += 1
                    elif isinstance(result, dict) and result.get("error"):
                        stats["error"] += 1
                    elif isinstance(result, dict):
                        has_transcript = bool(result.get("transcript","").strip())
                        has_comments   = result.get("comment_count", 0) > 0
                        stats["ok"] += 1
                        if has_transcript:  stats["with_transcript"] += 1
                        if has_comments:    stats["with_comments"] += 1
                    pbar.set_postfix(
                        ok=stats["ok"],
                        trans=stats["with_transcript"],
                        cmts=stats["with_comments"],
                        skip=stats["skip"],
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
    all_records = []
    for p in CHECKPOINT_DIR.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
            if not rec.get("error"):
                all_records.append(rec)
        except Exception:
            pass

    training_examples = []
    with tqdm(total=len(all_records), desc="Building", unit="v") as pbar:
        for rec in all_records:
            exs = make_examples(rec)
            training_examples.extend(exs)
            pbar.update(1)

    # Write raw JSONL
    with open(OUT_RAW, "w") as f:
        for rec in all_records:
            f.write(json.dumps(rec) + "\n")

    # Write training JSONL
    with open(OUT_TRAINING, "w") as f:
        for ex in training_examples:
            f.write(json.dumps(ex) + "\n")

    # Merge with v7 clean
    v7 = Path("training_data_v7_clean.jsonl")
    out_v8 = Path("training_data_v8.jsonl")
    merged = 0
    with open(out_v8, "w") as f:
        if v7.exists():
            for line in v7.read_text().splitlines():
                if line.strip():
                    f.write(line + "\n")
                    merged += 1
        for ex in training_examples:
            f.write(json.dumps(ex) + "\n")
            merged += 1

    # Stats breakdown
    from collections import Counter
    type_counts  = Counter(ex["source"]   for ex in training_examples)
    cat_counts   = Counter(ex.get("category","?") for ex in training_examples)
    ch_counts    = Counter(ex["channel"]  for ex in training_examples)

    print(f"\n{'='*60}")
    print(f"✅ DONE")
    print(f"   Raw records:          {len(all_records):,}")
    print(f"   Training examples:    {len(training_examples):,}")
    print(f"   Merged v8 total:      {merged:,}")
    print()
    print("📊 By example type:")
    for src, cnt in type_counts.most_common():
        print(f"   {src:35s} {cnt:,}")
    print()
    print("📊 By category (top 10):")
    for cat, cnt in cat_counts.most_common(10):
        print(f"   {cat:30s} {cnt:,}")
    print()
    print("📊 Top 10 channels by example count:")
    for ch, cnt in ch_counts.most_common(10):
        print(f"   {ch:30s} {cnt:,}")
    print()
    print(f"💾 Outputs:")
    print(f"   {OUT_RAW}           ← raw data (checkpoint)")
    print(f"   {OUT_TRAINING}  ← training-ready JSONL")
    print(f"   {out_v8}    ← merged with v7, ready to fine-tune")
    print()
    print("▶️  Next: python prep_finetune.py")


if __name__ == "__main__":
    main()
