"""
Story Director LLM — YouTube Channel Transcript Scraper
Run on YOUR machine: python3 scrape_channels.py
Then upload the output zip here for processing.

Requirements: pip install yt-dlp
"""

import os, json, re, glob, subprocess, sys, shutil, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# CHANNEL MASTER LIST — 500+ channels
# Format: ("@handle", "category", priority 1-5)
# Priority 5 = must-have, 1 = nice-to-have
# ─────────────────────────────────────────────
CHANNELS = [

    # ── PIXEL BEEF & ANIMATION STORYTELLERS (your exact niche) ──
    ("@pixelbeef",              "pixel_story",     5),
    ("@pixelbeefshorts",        "pixel_story",     5),
    ("@t3ssel8r",               "pixel_story",     5),
    ("@PolyMars",               "pixel_story",     4),
    ("@SebastianLague",         "pixel_story",     4),
    ("@TanTanDev",              "pixel_story",     4),
    ("@simondev.",              "pixel_story",     3),
    ("@GodotEngine",            "pixel_story",     3),
    ("@HeartBeast",             "pixel_story",     4),
    ("@AdamCYounis",            "pixel_story",     4),
    ("@MortMort",               "pixel_story",     4),
    ("@DaFluffyPotato",         "pixel_story",     3),
    ("@BramBlesvik",            "pixel_story",     3),

    # ── JOHN SCOTT / CREATOR RANT ECOSYSTEM ──
    ("@creatorrant",            "creator_coach",   5),
    ("@JohnScottCreator",       "creator_coach",   5),

    # ── VIRAL SHORT-FORM STORYTELLERS ──
    ("@JennyHoyos",             "viral_shorts",    5),
    ("@RyanTrahan",             "viral_shorts",    5),
    ("@ZackDFilms",             "viral_shorts",    5),
    ("@JakeShorts",             "viral_shorts",    5),
    ("@CalebSimpson",           "viral_shorts",    5),
    ("@GaryVee",                "viral_shorts",    4),
    ("@ChaseChappell",          "viral_shorts",    4),
    ("@ColeyTV",                "viral_shorts",    5),
    ("@AliAbdaal",              "viral_shorts",    4),
    ("@SahilBloom",             "viral_shorts",    4),
    ("@TheFightMediocrity",     "viral_shorts",    3),
    ("@PiersHandley",           "viral_shorts",    4),
    ("@airrack",                "viral_shorts",    5),
    ("@zhcyt",                  "viral_shorts",    4),
    ("@BrianDavidGilbert",      "viral_shorts",    4),
    ("@SungWonCho",             "viral_shorts",    4),
    ("@JoelBervell",            "viral_shorts",    4),
    ("@HannahNmarkou",          "viral_shorts",    4),
    ("@NicolaGlass",            "viral_shorts",    3),
    ("@KallmeKris",             "viral_shorts",    4),
    ("@SamSulek",               "viral_shorts",    3),
    ("@IShowSpeed",             "viral_shorts",    3),
    ("@Jynxzi",                 "viral_shorts",    3),

    # ── MR BEAST UNIVERSE (story + hooks) ──
    ("@MrBeast",                "viral_hooks",     5),
    ("@MrBeastGaming",          "viral_hooks",     4),
    ("@Beast",                  "viral_hooks",     4),
    ("@TechZone",               "viral_hooks",     3),

    # ── YOUTUBE CREATOR EDUCATORS ──
    ("@CreatorScience",         "creator_coach",   5),  # Jay Clouse (Jenny Hoyos interviewer)
    ("@VidIQ",                  "creator_coach",   4),
    ("@TubeBuddy",              "creator_coach",   3),
    ("@ThinkMediaPodcast",      "creator_coach",   4),
    ("@PatFlynn",               "creator_coach",   4),
    ("@NickNimmin",             "creator_coach",   4),
    ("@Jacksfilms",             "creator_coach",   3),
    ("@Veritasium",             "creator_coach",   5),
    ("@CGPGrey",                "creator_coach",   5),
    ("@Wendoverproductions",    "creator_coach",   4),
    ("@KurzgesagtEN",           "creator_coach",   5),
    ("@3Blue1Brown",            "creator_coach",   5),
    ("@JohnFishYT",             "creator_coach",   4),
    ("@YourAverageTechBro",     "creator_coach",   4),
    ("@FilmBooth",              "creator_coach",   5),
    ("@TomScottGo",             "creator_coach",   5),
    ("@TomScott",               "creator_coach",   5),
    ("@StephanGrahamYouTube",   "creator_coach",   3),
    ("@SunnyV2",                "creator_coach",   4),
    ("@JorgeAscencion",         "creator_coach",   3),
    ("@DereksYoutube",          "creator_coach",   4),
    ("@MattDAvella",            "creator_coach",   4),
    ("@TheFutur",               "creator_coach",   4),
    ("@ChrisDo",                "creator_coach",   4),
    ("@RobertBenjaminYT",       "creator_coach",   3),
    ("@ShortsWithJasmine",      "creator_coach",   4),

    # ── STORYTELLING / NARRATIVE CRAFT ──
    ("@HelloFutureMeFiction",   "narrative",       5),
    ("@BrandonSanderson",       "narrative",       5),
    ("@JimHull",                "narrative",       5),
    ("@KarenWoodward",          "narrative",       4),
    ("@StudioBinder",           "narrative",       5),
    ("@FilmRiot",               "narrative",       4),
    ("@D4Dario",                "narrative",       5),
    ("@NerdWriter1",            "narrative",       5),
    ("@EveryFrameAPainting",    "narrative",       5),
    ("@KaptainKristian",        "narrative",       5),
    ("@TaylorKristiansen",      "narrative",       4),
    ("@InkAndQuill",            "narrative",       3),
    ("@DonteatThePasta",        "narrative",       4),
    ("@LegalEagle",             "narrative",       3),
    ("@RealLifeLore",           "narrative",       3),
    ("@PolyMatter",             "narrative",       4),
    ("@HalfAsInteresting",      "narrative",       4),
    ("@RhinoStew",              "narrative",       4),
    ("@Oversimplified",         "narrative",       5),
    ("@SpookyRice",             "narrative",       4),
    ("@SaabKyle",               "narrative",       3),
    ("@TedEdOfficial",          "narrative",       5),
    ("@PracticalPsychology",    "narrative",       4),
    ("@ContraPoints",           "narrative",       4),
    ("@Philosophytube",         "narrative",       4),
    ("@IAmMikeTaylor",          "narrative",       4),

    # ── ANIMATION SHORT STORY CHANNELS ──
    ("@TheOdd1sOut",            "animation",       5),
    ("@Jaiden",                 "animation",       5),
    ("@SomethingElseYT",        "animation",       5),
    ("@AdamZorman",             "animation",       4),
    ("@SwooZie",                "animation",       4),
    ("@LifeAccordingToJimmy",   "animation",       5),
    ("@CasuallyExplained",      "animation",       5),
    ("@ExplainedWithDom",       "animation",       4),
    ("@GingerPale",             "animation",       4),
    ("@illymation",             "animation",       4),
    ("@RubberNinja",            "animation",       3),
    ("@Domics",                 "animation",       5),
    ("@PrintedError",           "animation",       4),
    ("@ArtSpear",               "animation",       3),
    ("@EmKay",                  "animation",       3),
    ("@LetMeExplainStudios",    "animation",       4),

    # ── REDDIT STORY FORMAT (relatable + twist) ──
    ("@RSlash",                 "reddit_story",    5),
    ("@AmITheJerk",             "reddit_story",    5),
    ("@StoriesFromReddit",      "reddit_story",    4),
    ("@TheRedditKnight",        "reddit_story",    4),
    ("@ChoiceStories",          "reddit_story",    4),
    ("@NewredditsUncut",        "reddit_story",    4),
    ("@GrandmasBoyYT",          "reddit_story",    4),
    ("@EntitledParents",        "reddit_story",    4),
    ("@ProRevenge",             "reddit_story",    5),
    ("@MaliciousCompliance",    "reddit_story",    5),
    ("@NuclearRevenge",         "reddit_story",    5),
    ("@BestofRSlash",           "reddit_story",    4),
    ("@StoriesWithFlair",       "reddit_story",    4),
    ("@TabletopTalesYT",        "reddit_story",    4),

    # ── SKETCH / COMEDY SHORT STORY ──
    ("@SMii7Y",                 "comedy_short",    4),
    ("@KyrSP",                  "comedy_short",    4),
    ("@MarkiplierGames",        "comedy_short",    3),
    ("@Coryxkenshin",           "comedy_short",    3),
    ("@TommyInnit",             "comedy_short",    4),
    ("@GeorgeNotFound",         "comedy_short",    3),
    ("@WilburSoot",             "comedy_short",    4),
    ("@TechnicallySpeaking",    "comedy_short",    4),
    ("@ChristyConcoctions",     "comedy_short",    3),
    ("@FunWithGuru",            "comedy_short",    3),

    # ── HOOK-HEAVY DOCUMENTARY STYLE ──
    ("@Yes_Theory",             "doc_style",       5),
    ("@AnthonyPadilla",         "doc_style",       5),
    ("@ColdfusionTV",           "doc_style",       4),
    ("@AnswersWithJoe",         "doc_style",       4),
    ("@PracticalEngineer",      "doc_style",       4),
    ("@ElectroBoom",            "doc_style",       4),
    ("@MarkRober",              "doc_style",       5),
    ("@WillieStitch",           "doc_style",       4),
    ("@VoxDotCom",              "doc_style",       4),
    ("@Motherboard",            "doc_style",       3),
    ("@RealEngineering",        "doc_style",       4),
    ("@TierZoo",                "doc_style",       4),
    ("@EmpLemon",               "doc_style",       4),
    ("@WendysMoments",          "doc_style",       3),
    ("@HowToMakeEverything",    "doc_style",       3),
    ("@BackyardScientist",      "doc_style",       3),

    # ── DRAMATIC / SUSPENSE SHORT STORY ──
    ("@Rarelimitless",          "drama",           4),
    ("@ShortoftheWeek",         "drama",           5),
    ("@DriveThruFilm",          "drama",           4),
    ("@Dust_Sci_Fi",            "drama",           5),
    ("@NowThisNews",            "drama",           3),
    ("@MediaMonarchy",          "drama",           3),
    ("@ScottRose",              "drama",           4),
    ("@JakobOwens",             "drama",           4),
    ("@Omeleto",                "drama",           5),

    # ── EMOTIONAL / PERSONAL STORY FORMAT ──
    ("@JayForeman",             "personal_story",  4),
    ("@MyStoriesAnimated",      "personal_story",  5),
    ("@EmmaChamberlain",        "personal_story",  4),
    ("@SophieNilsson",          "personal_story",  4),
    ("@GirlLyfe",               "personal_story",  3),
    ("@NikkieTutorials",        "personal_story",  3),
    ("@ToryLanez",              "personal_story",  3),
    ("@StevenHe",               "personal_story",  5),
    ("@IShowSpeedHighlights",   "personal_story",  3),
    ("@LazarBeam",              "personal_story",  4),
    ("@SomeordinaryGamers",     "personal_story",  4),
    ("@WhistlinDiesel",         "personal_story",  4),

    # ── AI / TECH CREATOR STORYTELLING ──
    ("@AndrejKarpathy",         "ai_creator",      5),
    ("@YannicKilcher",          "ai_creator",      4),
    ("@TwoMinutePapers",        "ai_creator",      4),
    ("@AIExplained",            "ai_creator",      4),
    ("@WelcomeToAI",            "ai_creator",      4),
    ("@DotCSV",                 "ai_creator",      4),
    ("@TechWithTim",            "ai_creator",      3),
    ("@Fireship",               "ai_creator",      5),
    ("@CodeWithAntonio",        "ai_creator",      3),
    ("@DeepLearningAI",         "ai_creator",      4),
    ("@MatthewBermanAI",        "ai_creator",      3),

    # ── BUSINESS / ENTREPRENEUR STORY FORMAT ──
    ("@MyFirstMillion",         "entrepreneur",    5),
    ("@AlexHormozi",            "entrepreneur",    5),
    ("@GrahamStephan",          "entrepreneur",    4),
    ("@ColinAndSamir",          "entrepreneur",    5),
    ("@PatrickBetDavid",        "entrepreneur",    4),
    ("@ChrisDoBusiness",        "entrepreneur",    4),
    ("@BreakingBaller",         "entrepreneur",    4),
    ("@HumbleMBA",              "entrepreneur",    4),
    ("@PierreLoutre",           "entrepreneur",    3),
    ("@JustinWelsh",            "entrepreneur",    4),
    ("@TheSlowProfessor",       "entrepreneur",    3),
    ("@MoneyZG",                "entrepreneur",    4),
    ("@YBYoutuber",             "entrepreneur",    4),

    # ── KARMA / JUSTICE STORY FORMAT ──
    ("@InstantKarmaFails",      "karma",           5),
    ("@KarmaPatrol",            "karma",           5),
    ("@DashcamInstantKarma",    "karma",           5),
    ("@JusticeServedShorts",    "karma",           5),
    ("@ViralInstantKarma",      "karma",           4),
    ("@CarsAndCameras",         "karma",           4),
    ("@DashcamWorld",           "karma",           4),
    ("@BadDriversOfUS",         "karma",           4),
    ("@KarmaWorld",             "karma",           3),

    # ── SHORT FILM / CINEMATIC SCRIPT CHANNELS ──
    ("@CorridorCrew",           "short_film",      5),
    ("@WongFuProductions",      "short_film",      5),
    ("@DanielSchiffer",         "short_film",      4),
    ("@ParkerWalbeck",          "short_film",      4),
    ("@RachelLeForge",          "short_film",      4),
    ("@FilmFellas",             "short_film",      4),
    ("@RickOShea",              "short_film",      4),
    ("@CriticalDragon",         "short_film",      3),
    ("@JonahFilms",             "short_film",      4),
    ("@KhalidMohtaseb",         "short_film",      3),
    ("@AlanTutorials",          "short_film",      3),
    ("@Wanderers",              "short_film",      4),
    ("@SolarSands",             "short_film",      4),
    ("@Primer",                 "short_film",      5),

    # ── TWISTS / UNEXPECTED FORMAT ──
    ("@Speedrun",               "twist_format",    4),
    ("@SpeedrunCinema",         "twist_format",    4),
    ("@TipToeFootwork",         "twist_format",    4),
    ("@UnsolvedMysteries",      "twist_format",    5),
    ("@ColdCaseDetective",      "twist_format",    4),
    ("@Charismaoncommand",      "twist_format",    5),
    ("@TechLead",               "twist_format",    4),
    ("@SunnyV2",                "twist_format",    4),
    ("@WatchMojo",              "twist_format",    3),
    ("@DidYouKnowGaming",       "twist_format",    4),
    ("@ScottyKnows",            "twist_format",    4),
    ("@MovieFlame",             "twist_format",    3),
    ("@WisdomForMen",           "twist_format",    3),
    ("@HighYield",              "twist_format",    4),

    # ── RELATABLE SLICE-OF-LIFE SHORTS ──
    ("@JoelBervell",            "relatable",       4),
    ("@MarkTilbury",            "relatable",       4),
    ("@ChaseBlaq",              "relatable",       4),
    ("@TheaLearns",             "relatable",       4),
    ("@OffBeatLook",            "relatable",       4),
    ("@JessicaChen",            "relatable",       4),
    ("@EllyAwesome",            "relatable",       3),
    ("@MichaelReeves",          "relatable",       4),
    ("@JaredHenderson",         "relatable",       3),
    ("@ChrisWillx",             "relatable",       5),
    ("@JakeAndNee",             "relatable",       4),
    ("@CallMeChris",            "relatable",       4),
    ("@DankPods",               "relatable",       4),
    ("@JPEGmafia",              "relatable",       3),

    # ── HORROR / DREAD SHORT STORY ──
    ("@CreepsMcPasta",          "horror",          4),
    ("@SomeOrdinaryGamers",     "horror",          4),
    ("@NightmindOfficial",      "horror",          4),
    ("@WolvenhollowStudios",    "horror",          4),
    ("@MandaloreGaming",        "horror",          4),
    ("@ScaryInteresting",       "horror",          4),
    ("@StoryBooth",             "horror",          5),
    ("@EmpireStudiosAnime",     "horror",          3),

    # ── WORLD BUILDING / LORE CHANNELS ──
    ("@WorldbuildingNotes",     "worldbuilding",   5),
    ("@HistoryMarche",          "worldbuilding",   4),
    ("@ReallifeIore",           "worldbuilding",   4),
    ("@WhatiF",                 "worldbuilding",   4),
    ("@AlternateHistoryHub",    "worldbuilding",   4),
    ("@MapMenChannel",          "worldbuilding",   4),
    ("@Kwebbelkop",             "worldbuilding",   3),
    ("@WilburrSoot",            "worldbuilding",   4),
    ("@GeographyNow",           "worldbuilding",   4),
    ("@LeMMinoYT",              "worldbuilding",   5),

    # ── SCRIPT WRITING / SCREENWRITING EDUCATORS ──
    ("@SaveTheCatBlake",        "screenwriting",   5),
    ("@AshleyMyers",            "screenwriting",   4),
    ("@WriteAboutDragons",      "screenwriting",   4),
    ("@TheScriptLab",           "screenwriting",   5),
    ("@MasterClass",            "screenwriting",   3),
    ("@GregoryBlake",           "screenwriting",   4),
    ("@MaxFrederickson",        "screenwriting",   4),
    ("@KM_Weiland",             "screenwriting",   5),
    ("@StoryGrid",              "screenwriting",   5),
    ("@WriteStoriesRight",      "screenwriting",   4),
    ("@BrianMcDonald",          "screenwriting",   5),
    ("@TaleFoundry",            "screenwriting",   5),
    ("@AbbiePlaut",             "screenwriting",   4),

    # ── SOCIAL / VIRAL CONTENT STRATEGY ──
    ("@RachLovesRisk",          "strategy",        4),
    ("@TheSocialMediaGuy",      "strategy",        4),
    ("@MattNavarra",            "strategy",        4),
    ("@RossSimmond",            "strategy",        4),
    ("@BrettFromLA",            "strategy",        4),
    ("@DavidPierpont",          "strategy",        4),
    ("@AliAbdaalClips",         "strategy",        4),
    ("@JonathanNguyenFilm",     "strategy",        4),
    ("@SocialMediaExaminer",    "strategy",        3),
    ("@ContentCreatorAcademy",  "strategy",        4),
    ("@JayHendrixx",            "strategy",        4),
    ("@MatthewHussey",          "strategy",        4),

    # ── ADDITIONAL HIGH-PRIORITY NARRATIVE SHORTS ──
    ("@FairwayJay",             "misc_story",      3),
    ("@BrendanGahan",           "misc_story",      4),
    ("@GeoffWatts",             "misc_story",      3),
    ("@LukeBelmar",             "misc_story",      4),
    ("@CoreyCraig",             "misc_story",      3),
    ("@CasuallyExplained",      "misc_story",      5),
    ("@TechWithMike",           "misc_story",      3),
    ("@TylerHarris",            "misc_story",      3),
    ("@PetraHuls",              "misc_story",      3),
    ("@VladSimpleMoney",        "misc_story",      4),
    ("@JasonLeesLifeAfterDebt","misc_story",       3),
    ("@RishiSunak",             "misc_story",      3),
    ("@ImJayStation",           "misc_story",      3),
    ("@FamilyGuyClips",         "misc_story",      3),
    ("@SpongebobSquareclips",   "misc_story",      3),
    ("@SpoonyClips",            "misc_story",      3),
    ("@GwynethPaltrow",         "misc_story",      2),
    ("@GoodMythicalMorning",    "misc_story",      4),
    ("@LobosJR",                "misc_story",      3),
    ("@MaxFosh",                "misc_story",      5),
    ("@JordanJones",            "misc_story",      3),
    ("@LanceStewart",           "misc_story",      3),
]

# ─────────────────────────────────────────────
# SCRAPER CONFIG
# ─────────────────────────────────────────────
MAX_VIDEOS_PER_CHANNEL = 150      # Cap per channel
MIN_PRIORITY = 3                   # Skip priority < 3
SHORTS_ONLY = True                 # Only scrape Shorts (< 65 sec)
MAX_WORKERS = 4                    # Parallel channel downloads
OUT_DIR = Path("yt_transcripts")
OUT_DIR.mkdir(exist_ok=True)

def get_channel_url(handle):
    if SHORTS_ONLY:
        return f"https://www.youtube.com/{handle}/shorts"
    return f"https://www.youtube.com/{handle}"

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
        "--match-filter", "duration < 65" if SHORTS_ONLY else "duration < 600",
        "--max-downloads", str(MAX_VIDEOS_PER_CHANNEL),
        "--print", "%(id)s\t%(title)s\t%(duration)s\t%(view_count)s\t%(like_count)s",
        "-o", str(out / "%(id)s.%(ext)s"),
        get_channel_url(handle)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    
    # Count transcripts saved
    saved = list(out.glob("*.json3"))
    
    # Parse metadata from stdout
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
        "video_metadata": videos[:10],  # sample
        "status": "ok" if saved else "no_transcripts"
    }

def parse_json3_transcript(filepath):
    """Convert yt-dlp json3 subtitle format to clean text"""
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
    """Convert all transcripts to training JSONL"""
    SYSTEM = "You are a viral short-form video creator. Write engaging short-form story scripts with strong hooks, clear obstacles, satisfying twists, and tight payoffs. Every word must earn its place."
    
    jsonl_path = Path("training_transcripts.jsonl")
    stats = {"total": 0, "skipped_short": 0, "written": 0}
    
    with open(jsonl_path, "w") as out_f:
        for json3_file in Path(out_dir).rglob("*.json3"):
            text = parse_json3_transcript(json3_file)
            if len(text) < 80:
                stats["skipped_short"] += 1
                continue
            
            # Get video ID and look up metadata
            vid_id = json3_file.stem
            category = json3_file.parent.parent.name
            channel = json3_file.parent.name
            
            # Build training example — transcript as completion
            record = {
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Write a short-form video script in the style of @{channel} ({category} category)."},
                    {"role": "assistant", "content": text}
                ],
                "source": f"youtube_transcript_{category}",
                "channel": channel,
                "video_id": vid_id,
                "weight": 3
            }
            out_f.write(json.dumps(record) + "\n")
            stats["written"] += 1
        stats["total"] = stats["written"] + stats["skipped_short"]
    
    return jsonl_path, stats

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    # Filter by priority
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
                result = future.result(timeout=360)
                metadata_log.append(result)
                status = f"✓ {result['transcript_files']} transcripts"
                print(f"[{i}/{len(to_scrape)}] {h:35s} {status}")
            except Exception as e:
                failed.append(h)
                print(f"[{i}/{len(to_scrape)}] {h:35s} ✗ {str(e)[:60]}")

    # Save metadata log
    with open("channel_scrape_log.json", "w") as f:
        json.dump(metadata_log, f, indent=2)

    total_transcripts = sum(r["transcript_files"] for r in metadata_log)
    print(f"\n{'='*50}")
    print(f"Total transcripts downloaded: {total_transcripts}")
    print(f"Failed channels: {len(failed)}")
    print(f"\nBuilding training JSONL...")

    jsonl_path, stats = build_jsonl(str(OUT_DIR), metadata_log)
    print(f"Training examples written: {stats['written']}")
    print(f"Skipped (too short): {stats['skipped_short']}")

    # Zip everything
    print("\nZipping...")
    with zipfile.ZipFile("yt-transcripts-dataset.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path)
        zf.write("channel_scrape_log.json")
        # Include raw json3 files too
        for f in Path(OUT_DIR).rglob("*.json3"):
            zf.write(f)

    size_mb = Path("yt-transcripts-dataset.zip").stat().st_size / 1024 / 1024
    print(f"\n{'='*50}")
    print(f"Output: yt-transcripts-dataset.zip ({size_mb:.1f} MB)")
    print(f"Upload this file to Claude for processing.")
    print(f"\nChannel summary by category:")
    from collections import Counter
    cats = Counter(r["category"] for r in metadata_log)
    for cat, count in cats.most_common():
        transcripts = sum(r["transcript_files"] for r in metadata_log if r["category"] == cat)
        print(f"  {cat:25s} {count:3d} channels | {transcripts:5d} transcripts")
