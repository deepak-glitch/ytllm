"""
youtube_api_scraper.py — YouTube Data API v3 Full Scraper
==========================================================
Uses the official YouTube Data API v3 for:
  - Channel → uploads playlist → video IDs
  - Video metadata (title, views, likes, duration, tags)
  - Comments (top 100 per video, sorted by relevance)

Uses youtube-transcript-api for transcripts (no API quota cost).

Setup (one time):
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "YouTube Data API v3"
  3. Credentials → Create API Key
  4. Add to .env:  YOUTUBE_API_KEY=AIza...

Install:
  pip install google-api-python-client youtube-transcript-api tqdm python-dotenv

Run:
  python youtube_api_scraper.py

Quota usage (free tier = 10,000 units/day):
  channels.list        = 1 unit  (resolve handle → channel ID)
  playlistItems.list   = 1 unit  (get 50 video IDs per request)
  videos.list          = 1 unit  (get metadata for 50 videos)
  commentThreads.list  = 1 unit  (get 100 comments per request)
  youtube-transcript-api = 0 units  (direct YouTube internal API)

Estimated quota for 238 channels × 50 videos:
  Channel resolve:   238 × 1 = 238 units
  Video ID fetch:    238 × 1 = 238 units   (50 videos/channel = 1 req)
  Video metadata:    11,900/50 = 238 units
  Comments:          11,900 × 1 = 11,900 units
  TOTAL:             ~12,614 units ≈ 1.3 days on free tier

Checkpoint/resume: safe to Ctrl+C and rerun.

Outputs:
  checkpoint/          ← one JSON file per video (auto-resume)
  everything_raw.jsonl    ← all video data (transcript + comments)
  everything_training.jsonl ← training-ready JSONL
  training_data_v8.jsonl   ← merged with v7_clean, ready to fine-tune
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
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("Installing google-api-python-client...")
    _pip("google-api-python-client")
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

try:
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
except ImportError:
    print("Installing youtube-transcript-api...")
    _pip("youtube-transcript-api")
    from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

try:
    from tqdm import tqdm
except ImportError:
    _pip("tqdm"); from tqdm import tqdm

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    _pip("python-dotenv")
    from dotenv import load_dotenv
    load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
def _load_api_keys() -> list:
    """Load API keys from env. Supports:
       YOUTUBE_API_KEYS=key1,key2,key3        (preferred)
       YOUTUBE_API_KEY=key1, YOUTUBE_API_KEY_2=key2, ... (also works)
    """
    keys = []
    bulk = os.getenv("YOUTUBE_API_KEYS", "")
    if bulk:
        keys.extend(k.strip() for k in bulk.split(",") if k.strip())
    for env_name in ["YOUTUBE_API_KEY"] + [f"YOUTUBE_API_KEY_{i}" for i in range(2, 11)]:
        v = os.getenv(env_name, "").strip()
        if v and v not in keys:
            keys.append(v)
    return keys

API_KEYS            = _load_api_keys()
YOUTUBE_API_KEY     = API_KEYS[0] if API_KEYS else ""
MAX_VIDEOS_PER_CH   = 10_000     # effectively unlimited — pages until channel is empty
MAX_COMMENTS        = 1_000      # comments per video (1 unit per 100)
MAX_DURATION_SEC    = 180        # skip videos longer than 3 min
MIN_VIEWS           = 500        # skip very low-view videos for comments
MIN_TRANSCRIPT_WORDS= 10         # skip near-empty transcripts
COMMENT_WORKERS     = 8          # parallel comment fetchers
TRANSCRIPT_WORKERS  = 12         # parallel transcript fetchers (no quota)

CHECKPOINT_DIR      = Path("checkpoint")
OUT_RAW             = Path("everything_raw.jsonl")
OUT_TRAINING        = Path("everything_training.jsonl")
CHECKPOINT_DIR.mkdir(exist_ok=True)


def _colab_download(paths: list):
    """If running inside Google Colab, auto-download output files to browser."""
    try:
        from google.colab import files as colab_files
        import zipfile
        print("\n📥 Running in Colab — zipping outputs for download...")
        zip_path = Path("ytllm_outputs.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                p = Path(p)
                if p.exists():
                    zf.write(p, p.name)
                    print(f"   + {p.name}  ({p.stat().st_size / 1_048_576:.1f} MB)")
        print(f"\n⬇️  Downloading {zip_path.name}...")
        colab_files.download(str(zip_path))
    except ImportError:
        pass  # not in Colab — silently skip

write_lock = Lock()

# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL LIST — 238 channels, 15 categories
# Format: ("@handle", "category", priority)
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS = [

    # ── YOUR EXACT NICHE — pixel art / 3D animation storytelling ──────────
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
    ("@pikasprey",              "pixel_story",       4),
    ("@Brackeys",               "pixel_story",       5),
    ("@Acerola0",               "pixel_story",       5),
    ("@GarbageCollector",       "pixel_story",       4),
    ("@TheCherno",              "pixel_story",       4),
    ("@ShyMoss",                "pixel_story",       4),
    ("@LowPolyForest",          "pixel_story",       4),
    ("@GDQuest",                "pixel_story",       4),
    ("@BitBirdy",               "pixel_story",       5),
    ("@Jonas-Tyroller",         "pixel_story",       5),

    # ── STORY ANIMATION (PixelBeef-style narrative structure) ─────────────
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

    # ── DRAMA / STORY SHORTS (Superficial2-style: social drama, twists) ──
    ("@Superficial2",           "drama_story",       5),
    ("@StoryBooth",             "drama_story",       5),
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
    ("@DramaShorts",            "drama_story",       4),
    ("@TheCoolDown",            "drama_story",       4),
    ("@RealStoriesTV",          "drama_story",       4),
    ("@TheActualFacts",         "drama_story",       5),
    ("@DramaAlert",             "drama_story",       3),

    # ── PETTY REVENGE / KARMA / JUSTICE (drive-through story type) ────────
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

    # ── REDDIT STORY FORMAT (AITA, relationships, conflict) ───────────────
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
    ("@AITAAnimate",            "reddit_story",      5),
    ("@RedditReads",            "reddit_story",      4),
    ("@AITAClips",              "reddit_story",      5),
    ("@RedditStoryTime",        "reddit_story",      4),
    ("@RedditJustice",          "reddit_story",      5),
    ("@UnfilteredReddit",       "reddit_story",      4),
    ("@RelationshipAdviceReddit","reddit_story",     4),

    # ── VIRAL STORY SHORTS (hook → twist → payoff masters) ────────────────
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
    ("@ChrisWillx",             "viral_shorts",      5),
    ("@LukeDavidson",           "viral_shorts",      5),
    ("@JakeDavidson",           "viral_shorts",      4),
    ("@SamSulek",               "viral_shorts",      3),
    ("@airrack",                "viral_shorts",      5),

    # ── CREATOR COACHES (storytelling craft, analytics) ───────────────────
    ("@creatorrant",            "creator_coach",     5),
    ("@JohnScottCreator",       "creator_coach",     5),
    ("@CreatorScience",         "creator_coach",     5),
    ("@FilmBooth",              "creator_coach",     5),
    ("@ColinAndSamir",          "creator_coach",     5),
    ("@VidIQ",                  "creator_coach",     4),
    ("@NickNimmin",             "creator_coach",     4),
    ("@DereksYoutube",          "creator_coach",     4),
    ("@MattDAvella",            "creator_coach",     4),
    ("@TheFutur",               "creator_coach",     4),
    ("@ShortsWithJasmine",      "creator_coach",     4),
    ("@PatFlynn",               "creator_coach",     4),
    ("@AliAbdaal",              "creator_coach",     4),
    ("@SahilBloom",             "creator_coach",     4),
    ("@JohnFishYT",             "creator_coach",     4),
    ("@TubeBuddy",              "creator_coach",     3),
    ("@ThinkMediaPodcast",      "creator_coach",     4),

    # ── DOCUMENTARY / HOOK-HEAVY STORYTELLING ─────────────────────────────
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

    # ── HORROR / CREEPYPASTA / DREAD ──────────────────────────────────────
    ("@CreepsMcPasta",          "horror_story",      4),
    ("@NightmindOfficial",      "horror_story",      4),
    ("@ScaryInteresting",       "horror_story",      5),
    ("@MandaloreGaming",        "horror_story",      4),
    ("@WolvenhollowStudios",    "horror_story",      4),
    ("@SomeordinaryGamers",     "horror_story",      4),
    ("@UnsolvedMysteries",      "horror_story",      5),
    ("@ColdCaseDetective",      "horror_story",      4),
    ("@TrueCreepShorts",        "horror_story",      4),
    ("@ScaryStoryTime",         "horror_story",      4),
    ("@HauntedStoryTime",       "horror_story",      3),

    # ── PERSONAL STORY / CONFESSIONAL ─────────────────────────────────────
    ("@AnthonyPadilla",         "personal_story",    5),
    ("@WhistlinDiesel",         "personal_story",    4),
    ("@LazarBeam",              "personal_story",    4),
    ("@MichaelReeves",          "personal_story",    4),
    ("@ContraPoints",           "personal_story",    4),
    ("@Philosophytube",         "personal_story",    4),
    ("@GoodMythicalMorning",    "personal_story",    3),
    ("@EddyBurback",            "personal_story",    4),
    ("@ScottTheWoz",            "personal_story",    4),
    ("@JakeAndNee",             "personal_story",    3),
    ("@DankPods",               "personal_story",    4),
    ("@NikkieTutorials",        "personal_story",    3),
    ("@SomethingElseYT",        "personal_story",    4),

    # ── SUSPENSE / TWIST SHORT FILMS ──────────────────────────────────────
    ("@Omeleto",                "short_film",        5),
    ("@ShortoftheWeek",         "short_film",        5),
    ("@Dust_Sci_Fi",            "short_film",        5),
    ("@CorridorCrew",           "short_film",        5),
    ("@WongFuProductions",      "short_film",        4),
    ("@DanielSchiffer",         "short_film",        4),
    ("@FilmRiot",               "short_film",        4),
    ("@SolarSands",             "short_film",        4),
    ("@D4Dario",                "short_film",        5),
    ("@JonahFilms",             "short_film",        4),
    ("@KhalidMohtaseb",         "short_film",        3),

    # ── SCREENWRITING / NARRATIVE CRAFT ───────────────────────────────────
    ("@StudioBinder",           "screenwriting",     5),
    ("@TaleFoundry",            "screenwriting",     5),
    ("@KM_Weiland",             "screenwriting",     5),
    ("@StoryGrid",              "screenwriting",     5),
    ("@EveryFrameAPainting",    "screenwriting",     5),
    ("@KaptainKristian",        "screenwriting",     5),
    ("@BrianMcDonald",          "screenwriting",     5),
    ("@JimHull",                "screenwriting",     4),
    ("@AbbiePlaut",             "screenwriting",     4),
    ("@WriteAboutDragons",      "screenwriting",     4),
    ("@HelloFutureMeFiction",   "screenwriting",     5),
    ("@HelloFutureMe",          "screenwriting",     5),

    # ── WORLD BUILDING / LORE ─────────────────────────────────────────────
    ("@WorldbuildingNotes",     "worldbuilding",     5),
    ("@BrandonSanderson",       "worldbuilding",     4),
    ("@GeographyNow",           "worldbuilding",     4),
    ("@AlternateHistoryHub",    "worldbuilding",     4),
    ("@WhatiF",                 "worldbuilding",     4),
    ("@MapMenChannel",          "worldbuilding",     4),
    ("@PolyMatter",             "worldbuilding",     4),
    ("@SpookyRice",             "worldbuilding",     4),
    ("@LEMMiNO",                "worldbuilding",     5),

    # ── COMEDY SKETCH (timing + setup/punchline) ──────────────────────────
    ("@TommyInnit",             "comedy",            4),
    ("@WilburSoot",             "comedy",            4),
    ("@SMii7Y",                 "comedy",            4),
    ("@Jacksfilms",             "comedy",            4),
    ("@GeorgeNotFound",         "comedy",            3),
    ("@Jynxzi",                 "comedy",            3),
    ("@KyrSP",                  "comedy",            3),
    ("@DankPods",               "comedy",            4),
    ("@GoodTimesWithScar",      "comedy",            3),

    # ── ENTREPRENEUR / BUSINESS STORY ─────────────────────────────────────
    ("@AlexHormozi",            "entrepreneur",      5),
    ("@MyFirstMillion",         "entrepreneur",      5),
    ("@GrahamStephan",          "entrepreneur",      4),
    ("@PatrickBetDavid",        "entrepreneur",      4),
    ("@SahilBloom",             "entrepreneur",      4),
    ("@JustinWelsh",            "entrepreneur",      4),
]

# ─────────────────────────────────────────────────────────────────────────────
# YOUTUBE API CLIENT
# ─────────────────────────────────────────────────────────────────────────────

class AllKeysExhausted(Exception):
    pass


class QuotaTracker:
    """Rotates through a pool of API keys when one hits its daily quota."""

    SAFETY_LIMIT = 9_800  # leave ~200 unit buffer below 10k daily free tier
    STATE_FILE   = Path("quota_state.json")

    def __init__(self, keys: list):
        self.keys = list(keys)
        self.idx  = 0
        # by-key (last 8 chars) → units used today (UTC)
        self.usage = {}
        self.day   = time.strftime("%Y-%m-%d", time.gmtime())
        self._load()
        # advance past any already-exhausted keys
        for _ in range(len(self.keys)):
            if self._units(self.keys[self.idx]) < self.SAFETY_LIMIT:
                break
            self.idx = (self.idx + 1) % len(self.keys)

    def _short(self, k: str) -> str:
        return k[-8:]

    def _units(self, key: str) -> int:
        return self.usage.get(self._short(key), 0)

    def _load(self):
        if not self.STATE_FILE.exists():
            return
        try:
            data = json.loads(self.STATE_FILE.read_text())
            if data.get("day") == self.day:
                self.usage = data.get("usage", {})
        except Exception:
            pass

    def _save(self):
        try:
            self.STATE_FILE.write_text(json.dumps({
                "day": self.day, "usage": self.usage,
            }))
        except Exception:
            pass

    @property
    def current_key(self) -> str:
        return self.keys[self.idx]

    def charge(self, units: int):
        # New UTC day → reset
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self.day:
            self.day = today
            self.usage = {}
        short = self._short(self.current_key)
        if self.usage.get(short, 0) + units > self.SAFETY_LIMIT:
            raise QuotaExhausted()
        self.usage[short] = self.usage.get(short, 0) + units
        self._save()

    def mark_exhausted(self):
        self.usage[self._short(self.current_key)] = self.SAFETY_LIMIT
        self._save()

    def rotate(self) -> bool:
        """Move to next non-exhausted key. Returns False if all are spent."""
        n = len(self.keys)
        for i in range(1, n + 1):
            cand = (self.idx + i) % n
            if self._units(self.keys[cand]) < self.SAFETY_LIMIT:
                self.idx = cand
                print(f"\n  🔄 Rotated to API key #{self.idx + 1} of {n} "
                      f"(...{self._short(self.current_key)})")
                return True
        return False

    def add_key(self, key: str):
        if key and key not in self.keys:
            self.keys.append(key)
            self.idx = len(self.keys) - 1
            print(f"  ➕ Added new API key — now using #{self.idx + 1}")


class QuotaExhausted(Exception):
    pass


def _ask_for_new_key() -> str:
    print("\n" + "=" * 60)
    print("⚠️  ALL API KEYS HAVE HIT TODAY'S QUOTA (~10k units each)")
    print("=" * 60)
    print("Options:")
    print("  1. Wait until midnight Pacific Time — quotas auto-reset")
    print("  2. Create a new API key:")
    print("     https://console.cloud.google.com/apis/credentials")
    print("     (new project → enable YouTube Data API v3 → create key)")
    print("  3. Paste the new key below and we'll continue immediately.")
    try:
        key = input("\nPaste new API key (or press Enter to abort): ").strip()
    except EOFError:
        key = ""
    return key


# Mutable single-element list so we can swap the client mid-run after rotation.
_yt_client = [None]

def _build_yt(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def get_youtube():
    if not API_KEYS:
        print("\n❌ No YouTube API keys found!")
        print("   1. Go to https://console.cloud.google.com/")
        print("   2. Create project → Enable 'YouTube Data API v3'")
        print("   3. Credentials → Create API Key")
        print("   4. Add to .env:")
        print("        YOUTUBE_API_KEYS=AIza_key1,AIza_key2,AIza_key3")
        sys.exit(1)
    if _yt_client[0] is None:
        _yt_client[0] = _build_yt(QUOTA.current_key)
    return _yt_client[0]


# Global quota tracker (built once keys are loaded)
QUOTA = QuotaTracker(API_KEYS) if API_KEYS else None


def _handle_quota_hit():
    """Try to rotate to the next un-exhausted key; if none left, ask user."""
    if QUOTA.rotate():
        _yt_client[0] = _build_yt(QUOTA.current_key)
        return
    new_key = _ask_for_new_key()
    if not new_key:
        raise AllKeysExhausted()
    QUOTA.add_key(new_key)
    _yt_client[0] = _build_yt(QUOTA.current_key)


# Rate limit: YouTube API allows ~10k units/day free per key. Add small delays.
_last_api_call = [0.0]
_api_lock = Lock()
API_DELAY = 0.05  # 50ms between calls = max ~20 calls/sec

def _api_call(request_fn, units: int = 1):
    """Execute an API request with rate limiting + key rotation on quota errors.

    request_fn must be a zero-arg callable (lambda) that returns a fresh
    request object — this lets us rebuild it against the new client after a
    key rotation."""
    while True:
        try:
            QUOTA.charge(units)
        except QuotaExhausted:
            try:
                _handle_quota_hit()
            except AllKeysExhausted:
                print("\n  ❌ All API keys exhausted and no new key provided.")
                return None
            continue

        with _api_lock:
            now = time.time()
            since = now - _last_api_call[0]
            if since < API_DELAY:
                time.sleep(API_DELAY - since)
            _last_api_call[0] = time.time()

        try:
            return request_fn().execute()
        except HttpError as e:
            status = e.resp.status
            body = str(e).lower()
            is_quota = status == 403 and (
                "quotaexceeded" in body or "dailylimitexceeded" in body
                or "ratelimit" in body
            )
            if is_quota:
                print(f"\n  ⏳ Quota hit on key ...{QUOTA._short(QUOTA.current_key)} — rotating")
                QUOTA.mark_exhausted()
                try:
                    _handle_quota_hit()
                except AllKeysExhausted:
                    print("  ❌ All API keys exhausted.")
                    return None
                continue
            if status == 429:
                print("\n  ⏳ Rate limit — sleeping 10s...")
                time.sleep(10)
                continue
            if status in (400, 404):
                return None  # channel not found / bad request — skip
            raise


# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL → VIDEO IDs
# ─────────────────────────────────────────────────────────────────────────────

def resolve_channel_id(yt, handle: str) -> tuple[str, str] | None:
    """
    Convert @handle to (channel_id, uploads_playlist_id).
    Uses channels.list with forHandle parameter.
    """
    handle_clean = handle.lstrip("@")
    resp = _api_call(
        lambda: _yt_client[0].channels().list(
            part="id,contentDetails",
            forHandle=handle_clean,
            maxResults=1,
        ),
        units=1,
    )
    if not resp or not resp.get("items"):
        # Fallback: try search (costs 100 units)
        resp2 = _api_call(
            lambda: _yt_client[0].search().list(
                part="snippet",
                q=handle_clean,
                type="channel",
                maxResults=1,
            ),
            units=100,
        )
        if not resp2 or not resp2.get("items"):
            return None
        channel_id = resp2["items"][0]["snippet"]["channelId"]
        resp = _api_call(
            lambda: _yt_client[0].channels().list(
                part="id,contentDetails",
                id=channel_id,
            ),
            units=1,
        )
        if not resp or not resp.get("items"):
            return None

    item = resp["items"][0]
    channel_id   = item["id"]
    uploads_id   = item["contentDetails"]["relatedPlaylists"]["uploads"]
    return channel_id, uploads_id


def get_video_ids_from_playlist(yt, playlist_id: str, max_videos: int = MAX_VIDEOS_PER_CH) -> list[str]:
    """
    Page through a channel's uploads playlist to collect ALL video IDs.
    Each request = 1 quota unit, returns up to 50 items per page.
    Pages until the channel is fully exhausted or max_videos is hit.
    """
    video_ids = []
    page_token = None

    while len(video_ids) < max_videos:
        params = dict(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=50,
        )
        if page_token:
            params["pageToken"] = page_token

        # Capture params by value so lambda always uses this iteration's params
        resp = _api_call(lambda p=params: _yt_client[0].playlistItems().list(**p), units=1)
        if not resp:
            break

        for item in resp.get("items", []):
            vid_id = item["contentDetails"].get("videoId", "")
            if vid_id:
                video_ids.append(vid_id)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break  # reached end of channel

    return video_ids


def get_video_metadata_batch(yt, video_ids: list[str]) -> dict[str, dict]:
    """
    Fetch metadata for up to 50 videos in one request (1 quota unit).
    Returns {video_id: metadata_dict}.
    """
    if not video_ids:
        return {}

    resp = _api_call(
        lambda: _yt_client[0].videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
            maxResults=50,
        ),
        units=1,
    )
    if not resp:
        return {}

    result = {}
    for item in resp.get("items", []):
        vid_id = item["id"]
        snippet     = item.get("snippet", {})
        stats       = item.get("statistics", {})
        content     = item.get("contentDetails", {})

        # Parse ISO 8601 duration → seconds
        duration_str = content.get("duration", "PT0S")
        dur_secs = _parse_duration(duration_str)

        result[vid_id] = {
            "video_id":    vid_id,
            "title":       snippet.get("title", ""),
            "description": snippet.get("description", "")[:500],
            "channel":     snippet.get("channelTitle", ""),
            "channel_id":  snippet.get("channelId", ""),
            "published_at":snippet.get("publishedAt", ""),
            "tags":        snippet.get("tags", []),
            "duration":    dur_secs,
            "views":       int(stats.get("viewCount", 0) or 0),
            "likes":       int(stats.get("likeCount", 0) or 0),
            "comment_count": int(stats.get("commentCount", 0) or 0),
        }
    return result


def _parse_duration(iso: str) -> int:
    """Parse ISO 8601 duration string to seconds. e.g. PT1M30S → 90"""
    total = 0
    for value, unit in re.findall(r"(\d+)([HMS])", iso):
        v = int(value)
        if unit == "H": total += v * 3600
        elif unit == "M": total += v * 60
        elif unit == "S": total += v
    return total


# ─────────────────────────────────────────────────────────────────────────────
# COMMENTS
# ─────────────────────────────────────────────────────────────────────────────

def get_comments(yt, video_id: str, max_comments: int = MAX_COMMENTS) -> list[dict]:
    """
    Fetch top comments sorted by relevance.
    1 quota unit per page (up to 100 comments per page).
    """
    comments = []
    page_token = None

    while len(comments) < max_comments:
        batch = min(100, max_comments - len(comments))
        params = dict(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=batch,
            textFormat="plainText",
        )
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = _api_call(lambda: _yt_client[0].commentThreads().list(**params), units=1)
        except Exception:
            break

        if not resp:
            break

        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            text = top.get("textDisplay", "").strip()
            if text:
                comments.append({
                    "text":    text,
                    "likes":   top.get("likeCount", 0),
                    "replies": item["snippet"].get("totalReplyCount", 0),
                    "author":  top.get("authorDisplayName", ""),
                })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    # Sort by likes descending
    comments.sort(key=lambda x: x["likes"], reverse=True)
    return comments


# ─────────────────────────────────────────────────────────────────────────────
# TRANSCRIPTS (youtube-transcript-api — zero API quota)
# ─────────────────────────────────────────────────────────────────────────────

def get_transcript(video_id: str) -> str:
    """
    Fetch transcript using youtube-transcript-api (no YouTube API quota).
    Tries English first, falls back to any available language.
    """
    try:
        try:
            chunks = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        except NoTranscriptFound:
            # Try any available transcript
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            transcript_obj  = transcript_list.find_transcript(["en"])
            chunks = transcript_obj.fetch()

        text = " ".join(c.get("text", "") for c in chunks)
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text.split()) >= MIN_TRANSCRIPT_WORDS else ""

    except (NoTranscriptFound, TranscriptsDisabled):
        return ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

def checkpoint_path(video_id: str) -> Path:
    return CHECKPOINT_DIR / f"{video_id}.json"

def is_done(video_id: str) -> bool:
    return checkpoint_path(video_id).exists()

def save_checkpoint(data: dict):
    checkpoint_path(data["video_id"]).write_text(json.dumps(data))

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
    transcript = (rec.get("transcript") or "").strip()
    comments   = rec.get("comments", [])
    title      = rec.get("title", "")
    channel    = rec.get("channel", "unknown")
    category   = rec.get("category", "")
    views      = rec.get("views", 0) or 0
    video_id   = rec["video_id"]
    tags       = rec.get("tags", [])

    good_cmts = sorted(
        [c for c in comments if c.get("likes", 0) >= 2 and c.get("text","").strip()],
        key=lambda x: x["likes"], reverse=True,
    )
    top_cmts_str = _top_comments_text(comments, 25)
    examples = []

    # ── 1. Transcript → script style ─────────────────────────────────────
    if transcript and len(transcript.split()) >= MIN_TRANSCRIPT_WORDS:
        cat_label = category.replace("_"," ").title()
        examples.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": f"Write a short-form video script in the style of @{channel} ({cat_label} — {views:,} views)."},
                {"role": "assistant", "content": transcript[:2000]},
            ],
            "source": f"transcript_{category}",
            "channel": channel, "video_id": video_id, "views": views, "weight": 3,
        })

    # ── 2. Transcript + comments → reaction analysis ──────────────────────
    if transcript and len(good_cmts) >= 5:
        top1 = good_cmts[0]
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Here's a short-form video transcript from @{channel} "
                    f"({views:,} views, {category.replace('_',' ')} niche):\n\n"
                    f'Title: "{title}"\n\nTRANSCRIPT:\n{transcript[:1200]}\n\n'
                    "What did the audience respond to most?"
                )},
                {"role": "assistant", "content": (
                    f"Looking at the top {len(good_cmts)} comments:\n\n{top_cmts_str}\n\n"
                    f"The audience zeroed in on the payoff moment. "
                    f"The most-liked comment ({top1['likes']} likes): "
                    f'"{top1["text"].strip()[:200]}"\n\n'
                    "That comment is the magic moment the whole video was building toward. "
                    "Write backwards from it next time."
                )},
            ],
            "source": "comment_reaction_analysis",
            "channel": channel, "video_id": video_id, "views": views, "weight": 3,
        })

    # ── 3. Story → predicted comments ────────────────────────────────────
    if transcript and len(good_cmts) >= 3:
        top3 = "\n".join(
            f'- "{c["text"].strip()[:150]}" ({c["likes"]} likes)'
            for c in good_cmts[:3]
        )
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Predict how viewers will react to this story:\n\n{transcript[:1000]}"},
                {"role": "assistant", "content": (
                    f"Based on the story structure, and what actually happened "
                    f"on @{channel} ({views:,} views):\n\n"
                    f"ACTUAL top comments:\n{top3}\n\n"
                    "The audience always homes in on the most concrete, visual payoff. "
                    "When you nail it, they quote it verbatim — that quoting is the algorithm's strongest replay signal."
                )},
            ],
            "source": "comment_prediction",
            "channel": channel, "video_id": video_id, "views": views, "weight": 3,
        })

    # ── 4. Magic moment (100k+ views) ────────────────────────────────────
    if views >= 100_000 and len(good_cmts) >= 5:
        top1 = good_cmts[0]
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Top comments from a {views:,}-view @{channel} video:\n\n"
                    f"{top_cmts_str}\n\nTitle: \"{title}\"\n\nWhat was the magic moment?"
                )},
                {"role": "assistant", "content": (
                    f"The most-liked comment ({top1['likes']:,} likes) reveals everything:\n\n"
                    f'"{top1["text"].strip()}"\n\n'
                    f"That comment got {top1['likes']:,} likes because it articulates exactly "
                    "what every viewer was thinking. That IS the payoff sentence. "
                    "Write your next script so the ending produces exactly that comment."
                )},
            ],
            "source": "magic_moment",
            "channel": channel, "video_id": video_id, "views": views, "weight": 4,
        })

    # ── 5. Comments-only hook (no transcript available) ───────────────────
    if len(good_cmts) >= 10 and not transcript:
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": (
                    f"Comments from a @{channel} video ({views:,} views):\n\n"
                    f"{top_cmts_str}\n\nWhat hook produced these reactions?"
                )},
                {"role": "assistant", "content": (
                    f"These comments reveal the hook pattern. "
                    f'The dominant reaction — "{good_cmts[0]["text"].strip()[:100]}" — '
                    "means the video opened with immediate stakes and an unresolved tension. "
                    "Replicate this: start with the payoff in mind, then build a hook "
                    "that creates maximum curiosity toward that exact ending."
                )},
            ],
            "source": "comments_only_hook",
            "channel": channel, "video_id": video_id, "views": views, "weight": 2,
        })

    # ── 6. Tags → story angle (if tags available) ─────────────────────────
    if tags and transcript and views >= 50_000:
        tag_str = ", ".join(tags[:10])
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"What story angles work for this topic? Tags: {tag_str}"},
                {"role": "assistant", "content": (
                    f"Based on a @{channel} video that hit {views:,} views with these tags:\n\n"
                    f'"{transcript[:600]}"\n\n'
                    f"The story angle that worked: lead with the most emotionally charged moment, "
                    f"not the chronological start. With tags like '{tags[0] if tags else ''}', "
                    "the audience already knows the topic — your hook needs to answer 'but why should I care RIGHT NOW?'"
                )},
            ],
            "source": "tags_story_angle",
            "channel": channel, "video_id": video_id, "views": views, "weight": 2,
        })

    return examples


# ─────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n🚀 YouTube API Full Scraper")
    print("=" * 60)

    yt = get_youtube()  # exits if no API key

    already_done = {p.stem for p in CHECKPOINT_DIR.glob("*.json")}
    print(f"   Channels:      {len(CHANNELS)}")
    print(f"   Already done:  {len(already_done)} videos (checkpoint)")
    print(f"   Videos/channel: ALL (no cap — pages until channel is empty)")
    print(f"   Max comments:  {MAX_COMMENTS} per video")
    print()

    # ─────────────────────────────────────────────────────────────────────
    # STEP 1 — Resolve channel handles → collect all video IDs + metadata
    # ─────────────────────────────────────────────────────────────────────
    print("📋 Step 1/4 — Resolving channels + collecting video IDs...")
    all_videos = []   # [{video_id, channel, category, title, views, duration, ...}]
    channel_errors = []

    for i, (handle, category, priority) in enumerate(
        tqdm(CHANNELS, desc="Channels", unit="ch")
    ):
        channel_name = handle.lstrip("@")
        try:
            result = resolve_channel_id(yt, handle)
            if not result:
                channel_errors.append(handle)
                continue
            _, uploads_id = result

            video_ids = get_video_ids_from_playlist(yt, uploads_id, MAX_VIDEOS_PER_CH)
            if not video_ids:
                continue

            # Batch-fetch metadata (50 at a time, 1 quota unit per batch)
            meta_map = {}
            for batch_start in range(0, len(video_ids), 50):
                batch = video_ids[batch_start:batch_start + 50]
                meta_map.update(get_video_metadata_batch(yt, batch))

            for vid_id in video_ids:
                meta = meta_map.get(vid_id, {})
                dur  = meta.get("duration", 0) or 0
                if dur > MAX_DURATION_SEC and dur != 0:
                    continue  # skip long videos
                all_videos.append({
                    "video_id":  vid_id,
                    "channel":   meta.get("channel", channel_name),
                    "category":  category,
                    "title":     meta.get("title", ""),
                    "views":     meta.get("views", 0),
                    "likes":     meta.get("likes", 0),
                    "duration":  dur,
                    "tags":      meta.get("tags", []),
                    "published": meta.get("published_at", ""),
                    "description": meta.get("description", ""),
                    "comments_enabled": meta.get("comment_count", -1) != 0,
                })

        except Exception as e:
            channel_errors.append(f"{handle}: {e}")

    # Deduplicate
    seen = set()
    unique = []
    for v in all_videos:
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            unique.append(v)

    todo = [v for v in unique if v["video_id"] not in already_done]

    print(f"\n   Found:    {len(unique):,} unique videos across {len(CHANNELS)} channels")
    print(f"   Done:     {len(already_done):,} already in checkpoint")
    print(f"   TODO:     {len(todo):,} to scrape")
    if channel_errors:
        print(f"   Errors:   {len(channel_errors)} channels failed")
    print()

    # ─────────────────────────────────────────────────────────────────────
    # STEP 2 — Fetch transcripts (parallel, no quota)
    # ─────────────────────────────────────────────────────────────────────
    print("📝 Step 2/4 — Fetching transcripts (youtube-transcript-api, no quota)...")
    transcript_map = {}
    with ThreadPoolExecutor(max_workers=TRANSCRIPT_WORKERS) as pool:
        futures = {pool.submit(get_transcript, v["video_id"]): v["video_id"] for v in todo}
        with tqdm(total=len(futures), desc="Transcripts", unit="v") as pbar:
            for future in as_completed(futures):
                vid_id = futures[future]
                try:
                    transcript_map[vid_id] = future.result()
                except Exception:
                    transcript_map[vid_id] = ""
                pbar.update(1)

    transcripts_found = sum(1 for t in transcript_map.values() if t)
    print(f"   Got transcripts for {transcripts_found:,} / {len(todo):,} videos")
    print()

    # ─────────────────────────────────────────────────────────────────────
    # STEP 3 — Fetch comments (YouTube API, 1 unit per 100 comments)
    # ─────────────────────────────────────────────────────────────────────
    print("💬 Step 3/4 — Fetching comments (YouTube Data API v3)...")
    stats = defaultdict(int)

    # Only fetch comments for videos with decent views or with a transcript
    comment_targets = [
        v for v in todo
        if v.get("views", 0) >= MIN_VIEWS or transcript_map.get(v["video_id"], "")
    ]
    print(f"   Fetching comments for {len(comment_targets):,} videos "
          f"(skipping {len(todo)-len(comment_targets):,} low-view with no transcript)")

    for v in tqdm(comment_targets, desc="Comments", unit="v"):
        vid_id = v["video_id"]
        try:
            comments = []
            if v.get("comments_enabled", True):
                comments = get_comments(yt, vid_id, MAX_COMMENTS)

            # Build full record and checkpoint
            rec = {**v}
            rec["transcript"] = transcript_map.get(vid_id, "")
            rec["comments"]   = comments
            rec["comment_count_fetched"] = len(comments)
            rec["scraped_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            save_checkpoint(rec)
            stats["ok"] += 1
            if rec["transcript"]: stats["with_transcript"] += 1
            if comments:          stats["with_comments"] += 1

        except Exception as e:
            stats["error"] += 1
            save_checkpoint({
                "video_id": vid_id, "channel": v["channel"],
                "category": v["category"], "error": str(e)[:200],
                "transcript": "", "comments": [],
            })

    # Also checkpoint transcript-only videos (no comments attempted)
    no_comment_targets = set(v["video_id"] for v in todo) - set(v["video_id"] for v in comment_targets)
    for vid_id in no_comment_targets:
        v = next(x for x in todo if x["video_id"] == vid_id)
        rec = {**v, "transcript": transcript_map.get(vid_id,""), "comments": [], "comment_count_fetched": 0}
        save_checkpoint(rec)

    print(f"\n   ✅ Scraped:          {stats['ok']:,}")
    print(f"   📝 With transcript:  {stats['with_transcript']:,}")
    print(f"   💬 With comments:    {stats['with_comments']:,}")
    print(f"   ❌ Errors:           {stats['error']:,}")
    print()

    # ─────────────────────────────────────────────────────────────────────
    # STEP 4 — Build training data
    # ─────────────────────────────────────────────────────────────────────
    print("🔨 Step 4/4 — Building training JSONL...")
    all_records    = load_all_checkpoints()
    all_examples   = []

    for rec in tqdm(all_records, desc="Building", unit="v"):
        exs = make_examples(rec)
        all_examples.extend(exs)

    # Write raw JSONL
    with open(OUT_RAW, "w") as f:
        for rec in all_records:
            f.write(json.dumps(rec) + "\n")

    # Write training JSONL
    with open(OUT_TRAINING, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")

    # Merge with v7_clean → v8
    v7 = Path("training_data_v7_clean.jsonl")
    v8 = Path("training_data_v8.jsonl")
    merged = 0
    with open(v8, "w") as f:
        if v7.exists():
            for line in v7.read_text().splitlines():
                if line.strip():
                    f.write(line + "\n"); merged += 1
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n"); merged += 1

    # Final report
    type_counts = Counter(ex["source"]  for ex in all_examples)
    cat_counts  = Counter(ex.get("category","?") for ex in all_examples)
    ch_counts   = Counter(ex["channel"] for ex in all_examples)

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
    print()
    print("▶️  Next: python prep_finetune.py")

    # ─────────────────────────────────────────────────────────────────────
    # AUTO-DOWNLOAD (Colab only)
    # ─────────────────────────────────────────────────────────────────────
    _colab_download([v8, OUT_TRAINING, OUT_RAW])


if __name__ == "__main__":
    main()
