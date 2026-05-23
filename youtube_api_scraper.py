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

import os, json, re, sys, time, subprocess, ssl, urllib3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict, Counter

# SSL bypass — needed in some cloud/proxy environments
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
from dotenv import load_dotenv as _load_dotenv
_load_dotenv(Path(__file__).parent / ".env")

def _load_api_keys() -> list:
    """
    Load API keys from .env. Supports:
      YOUTUBE_API_KEYS=AIza1,AIza2,AIza3    (preferred — comma separated)
      YOUTUBE_API_KEY=AIza1                  (single key, backward compat)
      YOUTUBE_API_KEY_2=AIza2                (numbered fallback)
      YOUTUBE_API_KEY_3=AIza3
    Returns ordered list of unique keys.
    """
    keys = []

    # 1. YOUTUBE_API_KEYS plural — comma separated
    bulk = os.getenv("YOUTUBE_API_KEYS", "")
    if bulk:
        keys.extend(k.strip() for k in bulk.split(",") if k.strip())

    # 2. YOUTUBE_API_KEY (singular) + numbered variants
    for env_name in ["YOUTUBE_API_KEY"] + [f"YOUTUBE_API_KEY_{i}" for i in range(2, 11)]:
        v = os.getenv(env_name, "").strip()
        if v and v not in keys:
            keys.append(v)

    return keys


API_KEYS            = _load_api_keys()
YOUTUBE_API_KEY     = API_KEYS[0] if API_KEYS else ""

MAX_VIDEOS_PER_CH   = 10_000    # effectively unlimited — grab every video
MAX_COMMENTS        = 500       # up to 500 comments per video (5 API pages)
MAX_DURATION_SEC    = 300       # skip videos longer than 5 min
MIN_VIEWS           = 500       # skip near-zero-view videos for comments
MIN_TRANSCRIPT_WORDS= 10        # skip near-empty transcripts
TRANSCRIPT_WORKERS  = 12        # parallel — no quota cost

QUOTA_LIMIT         = 9_800     # stop at 9,800 of 10,000 (200 unit safety buffer)
QUOTA_STATE_FILE    = Path("quota_state.json")
CHECKPOINT_DIR      = Path("checkpoint")
CHANNEL_CACHE_FILE  = Path("channel_cache.json")
OUT_RAW             = Path("everything_raw.jsonl")
OUT_TRAINING        = Path("everything_training.jsonl")

CHECKPOINT_DIR.mkdir(exist_ok=True)
write_lock = Lock()

# ── Quota tracker ─────────────────────────────────────────────────────────────
class QuotaExhausted(Exception):
    pass

class AllKeysExhausted(Exception):
    pass

class QuotaTracker:
    """
    Manages a pool of API keys. When one key's quota runs out, automatically
    rotates to the next. When ALL keys are exhausted, asks for a new one inline.

    Usage state persists in quota_state.json — survives restarts.
    """
    def __init__(self, keys: list):
        self.keys     = list(keys)
        self.idx      = 0                          # which key we're using now
        self.used     = {k[-8:]: 0 for k in self.keys}   # units used per key (by suffix)
        self._load()

    @property
    def current_key(self) -> str:
        return self.keys[self.idx] if self.keys else ""

    @property
    def current_suffix(self) -> str:
        k = self.current_key
        return k[-8:] if k else "none"

    @property
    def current_used(self) -> int:
        return self.used.get(self.current_suffix, 0)

    @property
    def remaining(self) -> int:
        return max(0, QUOTA_LIMIT - self.current_used)

    def _load(self):
        if QUOTA_STATE_FILE.exists():
            try:
                state = json.loads(QUOTA_STATE_FILE.read_text())
                self.used.update(state.get("used", {}))
                # Resume on the key that was active (if still in pool)
                last_suffix = state.get("active", "")
                for i, k in enumerate(self.keys):
                    if k[-8:] == last_suffix:
                        self.idx = i
                        break
                # If active key already used up, advance
                while self.idx < len(self.keys) and self.current_used >= QUOTA_LIMIT:
                    self.idx += 1
            except Exception:
                pass

    def _save(self):
        QUOTA_STATE_FILE.write_text(json.dumps({
            "used":   self.used,
            "active": self.current_suffix,
        }, indent=2))

    def add_key(self, new_key: str):
        """Add a brand new key to the pool (used when all are exhausted)."""
        new_key = new_key.strip()
        if new_key in self.keys:
            print(f"   ⚠️  Key (...{new_key[-8:]}) is already in pool")
            return False
        self.keys.append(new_key)
        self.used[new_key[-8:]] = 0
        self.idx = len(self.keys) - 1
        self._save()
        print(f"   🔑 Added new key (...{new_key[-8:]}) — pool size: {len(self.keys)}")
        return True

    def rotate(self) -> bool:
        """Move to next key in pool. Returns False if no more keys left."""
        # Find next un-exhausted key
        for i in range(self.idx + 1, len(self.keys)):
            if self.used.get(self.keys[i][-8:], 0) < QUOTA_LIMIT:
                self.idx = i
                self._save()
                print(f"\n   🔄 Rotated to key #{self.idx + 1}/{len(self.keys)} (...{self.current_suffix})")
                print(f"      {self.remaining} units available")
                return True
        return False

    def charge(self, units: int = 1):
        suffix = self.current_suffix
        self.used[suffix] = self.used.get(suffix, 0) + units
        self._save()
        if self.used[suffix] >= QUOTA_LIMIT:
            raise QuotaExhausted()

    def status_line(self) -> str:
        parts = []
        for i, k in enumerate(self.keys):
            used = self.used.get(k[-8:], 0)
            marker = "▶" if i == self.idx else " "
            if used >= QUOTA_LIMIT:
                parts.append(f"{marker} #{i+1} ...{k[-8:]} EXHAUSTED")
            else:
                parts.append(f"{marker} #{i+1} ...{k[-8:]} {used}/{QUOTA_LIMIT}")
        return "\n      ".join(parts)

QUOTA = QuotaTracker(API_KEYS)

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

def _build_yt(key: str):
    import httplib2
    http = httplib2.Http(disable_ssl_certificate_validation=True)
    return build("youtube", "v3", developerKey=key, http=http)


def _ask_for_new_key() -> str | None:
    """All keys in pool are exhausted — ask user to paste one more. None = give up."""
    print("\n" + "="*60)
    print("⚠️  ALL API KEYS EXHAUSTED")
    print("="*60)
    print(QUOTA.status_line())
    print("\nAll progress is saved. You can:")
    print("  • Paste another API key to keep going")
    print("  • Press Ctrl+C / Enter to stop (resume later with same .env)")
    while True:
        try:
            new_key = input("\n   Paste new API key (or Enter to quit): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not new_key:
            return None
        if new_key.startswith("AIza") and len(new_key) > 20:
            return new_key
        print("   ❌ Doesn't look right — should start with 'AIza...'")


_last_api_call = [0.0]
_api_lock = Lock()
API_DELAY = 0.1

_yt_client = [None]


def get_youtube():
    if not QUOTA.keys:
        print("\n❌ No API keys found in .env")
        print("   Add one of these:")
        print("     YOUTUBE_API_KEYS=AIza1,AIza2,AIza3")
        print("     OR")
        print("     YOUTUBE_API_KEY=AIza1")
        print("     YOUTUBE_API_KEY_2=AIza2")
        print("     YOUTUBE_API_KEY_3=AIza3")
        sys.exit(1)
    client = _build_yt(QUOTA.current_key)
    _yt_client[0] = client
    return client


def _handle_quota_hit():
    """Quota ran out on current key. Try to rotate. If pool exhausted, ask user."""
    if QUOTA.rotate():
        # Rebuild client with next key
        _yt_client[0] = _build_yt(QUOTA.current_key)
        return
    # All keys in pool exhausted
    new_key = _ask_for_new_key()
    if not new_key:
        raise AllKeysExhausted()
    QUOTA.add_key(new_key)
    _yt_client[0] = _build_yt(QUOTA.current_key)


def _api_call(request_fn, units: int = 1):
    """
    Execute one API request. If quota runs out on the current key, automatically
    rotate to the next key in the pool. If the entire pool is exhausted, prompt
    for one more key. If the user declines, raise AllKeysExhausted.
    """
    while True:
        try:
            QUOTA.charge(units)
        except QuotaExhausted:
            _handle_quota_hit()
            continue   # retry charge with new key

        with _api_lock:
            since = time.time() - _last_api_call[0]
            if since < API_DELAY:
                time.sleep(API_DELAY - since)
            _last_api_call[0] = time.time()

        try:
            return request_fn().execute()
        except HttpError as e:
            if e.resp.status == 403:
                err_reason = ""
                try:
                    err_reason = json.loads(e.content)["error"]["errors"][0]["reason"]
                except Exception:
                    pass
                if "quotaExceeded" in err_reason or "dailyLimitExceeded" in err_reason:
                    print(f"\n  ⚠️  YouTube server-side quota hit on ...{QUOTA.current_suffix}")
                    # Mark this key as fully exhausted in our tracker too
                    QUOTA.used[QUOTA.current_suffix] = QUOTA_LIMIT
                    QUOTA._save()
                    _handle_quota_hit()
                    continue   # retry with next key
                print(f"\n  ⏳ 403 rate limit — waiting 5s...")
                time.sleep(5)
                continue
            elif e.resp.status == 429:
                print(f"\n  ⏳ 429 rate limit — waiting 10s...")
                time.sleep(10)
                continue
            elif e.resp.status in (400, 404):
                return None
            else:
                raise


# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL → VIDEO IDs
# ─────────────────────────────────────────────────────────────────────────────

def _load_channel_cache() -> dict:
    if CHANNEL_CACHE_FILE.exists():
        try:
            return json.loads(CHANNEL_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_channel_cache(cache: dict):
    CHANNEL_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def resolve_channel_id(yt, handle: str, cache: dict) -> tuple[str, str] | None:
    """
    Convert @handle to (channel_id, uploads_playlist_id).
    Caches results so we never spend quota resolving the same handle twice.
    """
    if handle in cache:
        return cache[handle]["channel_id"], cache[handle]["uploads_id"]

    handle_clean = handle.lstrip("@")
    resp = _api_call(lambda: _yt_client[0].channels().list(
        part="id,contentDetails,snippet", forHandle=handle_clean, maxResults=1))
    if not resp or not resp.get("items"):
        resp2 = _api_call(lambda: _yt_client[0].search().list(
            part="snippet", q=handle_clean, type="channel", maxResults=1), units=100)
        if not resp2 or not resp2.get("items"):
            return None
        channel_id = resp2["items"][0]["snippet"]["channelId"]
        resp = _api_call(lambda: _yt_client[0].channels().list(
            part="id,contentDetails", id=channel_id))
        if not resp or not resp.get("items"):
            return None

    item       = resp["items"][0]
    channel_id = item["id"]
    uploads_id = item["contentDetails"]["relatedPlaylists"]["uploads"]
    ch_name    = item.get("snippet", {}).get("title", handle_clean)

    cache[handle] = {"channel_id": channel_id, "uploads_id": uploads_id, "name": ch_name}
    _save_channel_cache(cache)
    return channel_id, uploads_id


def get_video_ids_from_playlist(yt, playlist_id: str) -> list[str]:
    """
    Fetch ALL video IDs from a channel's uploads playlist.
    1 quota unit per request, 50 IDs per request — pages until exhausted.
    """
    video_ids  = []
    page_token = None

    while True:
        params = dict(part="contentDetails", playlistId=playlist_id, maxResults=50)
        if page_token:
            params["pageToken"] = page_token

        resp = _api_call(lambda p=params: _yt_client[0].playlistItems().list(**p))
        if not resp:
            break

        for item in resp.get("items", []):
            vid_id = item["contentDetails"].get("videoId", "")
            if vid_id:
                video_ids.append(vid_id)

        page_token = resp.get("nextPageToken")
        if not page_token:
            break   # no more pages — got every video

    return video_ids


def get_video_metadata_batch(yt, video_ids: list[str]) -> dict[str, dict]:
    """
    Fetch metadata for up to 50 videos in one request (1 quota unit).
    Returns {video_id: metadata_dict}.
    """
    if not video_ids:
        return {}

    ids_str = ",".join(video_ids)
    resp = _api_call(lambda: _yt_client[0].videos().list(
        part="snippet,statistics,contentDetails", id=ids_str, maxResults=50))
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
    Fetch up to max_comments comments sorted by relevance.
    1 quota unit per page of 100 — QuotaExhausted propagates up if limit hit.
    """
    comments   = []
    page_token = None

    while len(comments) < max_comments:
        params = dict(
            part="snippet",
            videoId=video_id,
            order="relevance",
            maxResults=100,   # always request max per page
            textFormat="plainText",
        )
        if page_token:
            params["pageToken"] = page_token

        try:
            resp = _api_call(lambda p=params: _yt_client[0].commentThreads().list(**p))
        except Exception:
            break   # comments disabled, deleted, etc.

        if not resp:
            break

        for item in resp.get("items", []):
            top  = item["snippet"]["topLevelComment"]["snippet"]
            text = top.get("textDisplay", "").strip()
            if text:
                comments.append({
                    "text":    text,
                    "likes":   top.get("likeCount", 0),
                    "replies": item["snippet"].get("totalReplyCount", 0),
                    "author":  top.get("authorDisplayName", ""),
                })

        page_token = resp.get("nextPageToken")
        if not page_token or len(comments) >= max_comments:
            break

    comments.sort(key=lambda x: x["likes"], reverse=True)
    return comments[:max_comments]


# ─────────────────────────────────────────────────────────────────────────────
# TRANSCRIPTS (youtube-transcript-api — zero API quota)
# ─────────────────────────────────────────────────────────────────────────────

def get_transcript(video_id: str) -> str:
    """
    Fetch transcript using youtube-transcript-api v1.x (no YouTube API quota).
    Tries English first, falls back to any available language.
    """
    try:
        api = YouTubeTranscriptApi()
        try:
            result = api.fetch(video_id, languages=["en", "en-US", "en-GB"])
        except Exception:
            # Fallback: list available transcripts and pick first
            transcript_list = api.list(video_id)
            transcript_obj  = next(iter(transcript_list), None)
            if transcript_obj is None:
                return ""
            result = transcript_obj.fetch()

        text = " ".join(s.text if hasattr(s, "text") else s["text"] for s in result)
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text.split()) >= MIN_TRANSCRIPT_WORDS else ""

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

def _flush_outputs():
    """Write everything_raw.jsonl + everything_training.jsonl from checkpoint dir."""
    all_records  = load_all_checkpoints()
    all_examples = []
    for rec in all_records:
        all_examples.extend(make_examples(rec))
    with open(OUT_RAW, "w") as f:
        for rec in all_records:
            f.write(json.dumps(rec) + "\n")
    with open(OUT_TRAINING, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")
    return len(all_records), len(all_examples)


def main():
    print("\n🚀 YouTube API Full Scraper")
    print("=" * 60)
    print(f"   API key pool ({len(QUOTA.keys)} keys):")
    print(f"      {QUOTA.status_line()}")
    print(f"   Total quota:   {len(QUOTA.keys) * QUOTA_LIMIT:,} units")
    print(f"   Max comments:  {MAX_COMMENTS} per video")
    print(f"   Videos/ch:     ALL (no cap)")
    print()

    yt = get_youtube()

    already_done  = {p.stem for p in CHECKPOINT_DIR.glob("*.json")}
    channel_cache = _load_channel_cache()
    print(f"   Checkpointed:  {len(already_done):,} videos already done")
    print(f"   Ch. cache:     {len(channel_cache)} channels already resolved")
    print()

    # ── STEP 1: Resolve channels + collect ALL video IDs + metadata ───────
    print("📋 Step 1/4 — Resolving channels + collecting ALL video IDs...")
    all_videos     = []
    channel_errors = []

    for handle, category, _ in tqdm(CHANNELS, desc="Channels", unit="ch"):
        channel_name = handle.lstrip("@")
        try:
            result = resolve_channel_id(yt, handle, channel_cache)
            if not result:
                channel_errors.append(handle); continue
            _, uploads_id = result

            video_ids = get_video_ids_from_playlist(yt, uploads_id)  # ALL videos
            if not video_ids:
                continue

            # Batch-fetch metadata 50 at a time
            meta_map = {}
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                meta_map.update(get_video_metadata_batch(yt, batch))

            for vid_id in video_ids:
                meta = meta_map.get(vid_id, {})
                dur  = meta.get("duration", 0) or 0
                if dur > MAX_DURATION_SEC and dur != 0:
                    continue
                all_videos.append({
                    "video_id":        vid_id,
                    "channel":         meta.get("channel", channel_name),
                    "category":        category,
                    "title":           meta.get("title", ""),
                    "views":           meta.get("views", 0),
                    "likes":           meta.get("likes", 0),
                    "duration":        dur,
                    "tags":            meta.get("tags", []),
                    "published":       meta.get("published_at", ""),
                    "description":     meta.get("description", ""),
                    "comments_enabled": meta.get("comment_count", -1) != 0,
                })

        except Exception as e:
            channel_errors.append(f"{handle}: {e}")

    # Deduplicate
    seen, unique = set(), []
    for v in all_videos:
        if v["video_id"] not in seen:
            seen.add(v["video_id"]); unique.append(v)

    todo = [v for v in unique if v["video_id"] not in already_done]

    print(f"\n   Found:     {len(unique):,} unique videos")
    print(f"   Done:      {len(already_done):,} already checkpointed")
    print(f"   Remaining: {len(todo):,} to scrape")
    print(f"   Quota:     {QUOTA.used} used / {QUOTA.remaining} remaining")
    if channel_errors:
        print(f"   Errors:    {len(channel_errors)} channels failed")
    print()

    # ── STEP 2: Transcripts (no quota) ───────────────────────────────────
    print("📝 Step 2/4 — Fetching transcripts (no quota cost)...")
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

    found_t = sum(1 for t in transcript_map.values() if t)
    print(f"   Got {found_t:,} / {len(todo):,} transcripts")
    print()

    # ── STEP 3: Comments (quota-tracked, stops gracefully) ────────────────
    print("💬 Step 3/4 — Fetching comments...")
    print(f"   Quota before: {QUOTA.used} used / {QUOTA.remaining} remaining")
    stats = defaultdict(int)

    for v in tqdm(todo, desc="Comments", unit="v"):
        vid_id = v["video_id"]
        try:
            comments = []
            if v.get("comments_enabled", True) and v.get("views", 0) >= MIN_VIEWS:
                comments = get_comments(yt, vid_id, MAX_COMMENTS)

            rec = {**v,
                   "transcript":           transcript_map.get(vid_id, ""),
                   "comments":             comments,
                   "comment_count_fetched": len(comments),
                   "scraped_at":           time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            save_checkpoint(rec)
            stats["ok"] += 1
            if rec["transcript"]: stats["with_transcript"] += 1
            if comments:          stats["with_comments"]   += 1

        except Exception as e:
            stats["error"] += 1
            save_checkpoint({"video_id": vid_id, "channel": v["channel"],
                              "category": v["category"], "error": str(e)[:200],
                              "transcript": "", "comments": []})

    print(f"\n   ✅ Scraped:          {stats['ok']:,}")
    print(f"   📝 With transcript:  {stats['with_transcript']:,}")
    print(f"   💬 With comments:    {stats['with_comments']:,}")
    print(f"   ❌ Errors:           {stats['error']:,}")
    print(f"   📊 Quota used:       {QUOTA.used} / {QUOTA_LIMIT}")
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


if __name__ == "__main__":
    try:
        main()
    except AllKeysExhausted:
        print("\n" + "="*60)
        print("⏸  STOPPED — all keys exhausted, no new key provided")
        print("="*60)
        n_rec, n_ex = _flush_outputs()
        print(f"💾 Flushed {n_rec:,} video records → {n_ex:,} training examples")
        print(f"   {OUT_RAW}")
        print(f"   {OUT_TRAINING}")
        print(f"\nRun again any time — checkpoint/ holds all completed videos.")
        print(f"Add fresh keys to .env (YOUTUBE_API_KEYS=k1,k2,k3) when ready.")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n\n⏸  Interrupted by user")
        n_rec, n_ex = _flush_outputs()
        print(f"💾 Flushed {n_rec:,} records → {n_ex:,} training examples")
        sys.exit(0)
