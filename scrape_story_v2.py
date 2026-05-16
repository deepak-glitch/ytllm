"""
Story-Focused Channel Scraper v2
─────────────────────────────────────────────────────────────────────────────
Curated list of channels with ZackDFilms-quality storytelling OR
Superficial2-quality 3D/animated story shorts — the two reference vibes
for this project.

Channels already scraped in v1/extra-channels are intentionally excluded
to avoid duplicates in training_data_v7+.

Already in dataset / run_extra_channels.py (DO NOT re-add):
  @ZackDFilms, @JennyHoyos, @Superficial2, @pixelbeefshorts, @rennrat78,
  @Christify777, @HisYTStory, @Ripped-x, @NotableNet, @Bobbie-26,
  @Christs_Echo, @eng_universelabz, @LowPolyShorts, @lifeinpoly,
  @Cutiepaw-3D, @ithinkitsgeorge, @HeyJohnScott, @MrBeast, @AlexHormozi,
  @GrahamStephan, @AliAbdaal, @ColinAndSamir, @CorridorCrew, @StevenHe,
  @StoryBooth, @MaxFosh, @ChrisWillx, @TubeBuddy, @VidIQ, @TheFutur,
  @GoodMythicalMorning, @GeographyNow, @ThinkMediaPodcast, @StoryGrid,
  @JoelBervell, @AmITheJerk, @MarkTilbury

Run on YOUR machine:
  pip install yt-dlp
  python3 scrape_story_v2.py

Output: story-v2-dataset.zip — upload to Claude for merging into training_data_v7.

Weight guide:
  5 = elite storytelling, must-have, highest training signal
  4 = solid story structure, high value
  3 = supplementary, good but not essential
─────────────────────────────────────────────────────────────────────────────
"""

import json, re, subprocess, sys, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp", "-q"])

# ─────────────────────────────────────────────────────────────────────────────
# CHANNEL LIST
# Format: ("@handle", "category", weight 3-5)
# ─────────────────────────────────────────────────────────────────────────────
CHANNELS = [

    # ══════════════════════════════════════════════════════════════════
    # ZACKDFILMS-STYLE  ── live-action, tight narrative arc, great hook
    # These are the channels most structurally similar to ZackD:
    # quick setup → obstacle → twist → satisfying payoff, all in <60s
    # ══════════════════════════════════════════════════════════════════

    # ── Tier 1: ZackD-level story pacing (weight 5) ──
    ("@RyanTrahan",          "zackd_style",    5),   # challenge + story, cinematic shorts
    ("@NasDailyVideos",      "zackd_style",    5),   # 1-min world story — perfect structure
    ("@JakeShorts",          "zackd_style",    5),   # punchy narrative format
    ("@ColeyTV",             "zackd_style",    5),   # viral story format
    ("@airrack",             "zackd_style",    5),   # challenge + narrative arc
    ("@CalebSimpson",        "zackd_style",    5),   # day-in-life with clear story spine
    ("@JordanMatter",        "zackd_style",    5),   # challenge → payoff, great pacing
    ("@PrestonPlayz",        "zackd_style",    4),   # challenge stories, consistent structure
    ("@BenAzelart",          "zackd_style",    4),   # challenge + emotional story beat
    ("@BrentRivera",         "zackd_style",    4),   # relatable story shorts

    # ── Tier 2: Strong storytelling w/ good hooks (weight 4) ──
    ("@zhcyt",               "zackd_style",    4),   # art challenge + emotional narrative
    ("@MichaelReeves",       "zackd_style",    4),   # chaotic engineering story arc
    ("@JoshuaWeissman",      "zackd_style",    4),   # personal story + culinary
    ("@WhistlinDiesel",      "zackd_style",    4),   # tension + destruction + payoff
    ("@CaseNap",             "zackd_style",    4),   # story shorts
    ("@SamSulek",            "zackd_style",    3),   # training story, strong hook habit
    ("@HaileySek",           "zackd_style",    4),   # viral story format
    ("@ThatGuyNate",         "zackd_style",    4),   # engaging narrative shorts
    ("@PatrickCC",           "zackd_style",    4),   # story shorts
    ("@VisaVerse",           "zackd_style",    4),   # travel + story
    ("@JoeHattab",           "zackd_style",    4),   # travel narrative, great pacing
    ("@ChrisKamsler",        "zackd_style",    4),   # short story challenge format
    ("@KallmePat",           "zackd_style",    4),   # viral storytelling
    ("@EvanErmey",           "zackd_style",    4),   # story shorts
    ("@SeanMcNamara",        "zackd_style",    4),   # cinematic story shorts

    # ── Tier 3: Solid but supplementary (weight 3) ──
    ("@IShowSpeed",          "zackd_style",    3),   # chaotic hook energy
    ("@Jynxzi",              "zackd_style",    3),   # gaming + story format
    ("@LazarBeam",           "zackd_style",    3),   # gaming story arc
    ("@TommyInnit",          "zackd_style",    3),   # chaos story structure
    ("@GeorgeNotFound",      "zackd_style",    3),   # narrative comedy
    ("@WilburSoot",          "zackd_style",    3),   # story + music narrative


    # ══════════════════════════════════════════════════════════════════
    # SUPERFICIAL2-STYLE  ── 3D/animated/pixel story shorts
    # These channels tell stories through animation or 3D art with the
    # same tight structure: hook → character → twist → payoff
    # ══════════════════════════════════════════════════════════════════

    # ── Tier 1: Must-have animated story channels (weight 5) ──
    ("@CasVanDePol",         "animated_story", 5),   # viral animated comedy shorts, huge hooks
    ("@AlexClark",           "animated_story", 5),   # animated personal stories, excellent pacing
    ("@Haminations",         "animated_story", 5),   # relatable animated stories, warm tone
    ("@CircleToonsHD",       "animated_story", 5),   # animated sports + story (tight structure)
    ("@illymation",          "animated_story", 4),   # personal animated stories
    ("@KurzgesagtEN",        "animated_story", 5),   # animated explainer with story arc (gold standard)
    ("@TedEdOfficial",       "animated_story", 5),   # animated story-lessons, perfect hook structure
    ("@AlanBecker",          "animated_story", 5),   # animation vs animator — pure visual story
    ("@KevinParry",          "animated_story", 5),   # magic/illusion shorts — incredible hook:payoff ratio

    # ── Tier 2: Strong animated storytellers (weight 4) ──
    ("@DanielThrasher",      "animated_story", 4),   # animated piano comedy, great story beats
    ("@Saberspark",          "animated_story", 4),   # animated commentary, good structure
    ("@mashed",              "animated_story", 4),   # animated parody with story
    ("@HiTopFilms",          "animated_story", 4),   # animated movie analysis story
    ("@SomethingElseYT",     "animated_story", 4),   # animated personal story (same as SomethingElse)
    ("@GingerPale",          "animated_story", 4),   # surreal animated stories
    ("@Andymation",          "animated_story", 4),   # animated story shorts
    ("@Jaiden",              "animated_story", 5),   # animated personal story — top tier structure
    ("@TheOdd1sOut",         "animated_story", 5),   # animated personal story — gold standard
    ("@Domics",              "animated_story", 4),   # animated life story
    ("@LetMeExplainStudios", "animated_story", 4),   # animated story
    ("@SwooZie",             "animated_story", 4),   # animated relatable stories, great hooks
    ("@SomethingElseYT",     "animated_story", 4),   # animated personal

    # ── Tier 3: 3D / low-poly / game-adjacent animation (weight 4-5) ──
    ("@TanTanDev",           "pixel_3d_story", 5),   # 3D game dev narrative shorts
    ("@SebastianLague",      "pixel_3d_story", 5),   # 3D procedural story, beautiful pacing
    ("@PolyMars",            "pixel_3d_story", 5),   # low-poly game dev story format
    ("@HeartBeast",          "pixel_3d_story", 4),   # pixel art game dev story
    ("@AdamCYounis",         "pixel_3d_story", 4),   # pixel art tutorial + story
    ("@MortMort",            "pixel_3d_story", 4),   # pixel art story
    ("@simondev.",           "pixel_3d_story", 4),   # 3D game dev narrative
    ("@GodotEngine",         "pixel_3d_story", 3),   # Godot tutorials with story
    ("@t3ssel8r",            "pixel_3d_story", 5),   # pixel shader art story — KEY reference
    ("@DaFluffyPotato",      "pixel_3d_story", 4),   # game dev story shorts
    ("@BisonCourt",          "pixel_3d_story", 4),   # 3D animation short stories
    ("@PilotRedSun",         "pixel_3d_story", 4),   # sci-fi 3D animation shorts
    ("@HappyToast",          "pixel_3d_story", 4),   # pixel art animation


    # ══════════════════════════════════════════════════════════════════
    # HOOK-FIRST COMMENTARY  ── strong hook structure, story-driven opinion
    # Great for training: these creators ALWAYS open with a hook, build
    # tension through story, then pay off with a reveal or punchline
    # ══════════════════════════════════════════════════════════════════

    ("@DrewGooden",          "commentary_story", 5), # story-driven commentary, extremely tight
    ("@DannyGonzalez",       "commentary_story", 5), # hook + story + twist structure
    ("@EddyBurback",         "commentary_story", 5), # narrative comedy, great pacing
    ("@KurtisConner",        "commentary_story", 4), # commentary story arc
    ("@Pyrocynical",         "commentary_story", 4), # story commentary
    ("@MoistCr1TiKaL",      "commentary_story", 4), # hook-heavy with story
    ("@JarvisJohnson",       "commentary_story", 4), # story-driven commentary
    ("@CallMeCarson",        "commentary_story", 4), # narrative storytelling
    ("@ScottTheWoz",         "commentary_story", 4), # gaming + narrative (excellent structure)
    ("@NukesTop5",           "commentary_story", 3), # suspense story countdown
    ("@SunnyV2",             "commentary_story", 4), # story commentary, great hooks
    ("@EmpLemon",            "commentary_story", 5), # long-form but exceptional structure signal
    ("@Optimus",             "commentary_story", 4), # YouTube drama stories
    ("@Slimecicle",          "commentary_story", 4), # comedy story format


    # ══════════════════════════════════════════════════════════════════
    # EMOTIONAL / DRAMATIC ARC  ── character-driven, tearjerker or triumph
    # Important for teaching the LLM emotion_intensity and payoff weight
    # ══════════════════════════════════════════════════════════════════

    ("@Struthless",          "emotional_story", 5),  # self-improvement story, excellent structure
    ("@JayForeman",          "emotional_story", 4),  # personal story + music
    ("@SophieNilsson",       "emotional_story", 4),  # emotional personal story
    ("@JoelBervell",         "emotional_story", 4),  # relatable emotional story shorts
    ("@AnthonyPadilla",      "emotional_story", 5),  # "I spent a day with" — story interview
    ("@Yes_Theory",          "emotional_story", 5),  # fear → growth story arc (perfect structure)
    ("@MyStoriesAnimated",   "emotional_story", 5),  # animated real-life emotional stories
    ("@StoriesByThalia",     "emotional_story", 4),  # emotional short stories
    ("@GabrielleRose",       "emotional_story", 4),  # emotional story content
    ("@JonahFilms",          "emotional_story", 4),  # emotional cinematic shorts
    ("@Omeleto",             "emotional_story", 5),  # indie short films — GOLD for story structure
    ("@ShortoftheWeek",      "emotional_story", 5),  # curated short films — pure story signal
    ("@Dust_Sci_Fi",         "emotional_story", 5),  # sci-fi short stories (excellent arc structure)
    ("@Primer",              "emotional_story", 5),  # animated logic + story, very tight
    ("@WongFuProductions",   "emotional_story", 5),  # Asian-American short films, emotional beats


    # ══════════════════════════════════════════════════════════════════
    # TRUE CRIME / SUSPENSE  ── hook → investigation → twist → reveal
    # Teaches the LLM suspense building, foreshadowing, obstacle layering
    # ══════════════════════════════════════════════════════════════════

    ("@CrimeByTheMint",      "true_crime_story", 4), # true crime with story structure
    ("@ColdMKE",             "true_crime_story", 4), # suspense story format
    ("@NightmindOfficial",   "true_crime_story", 4), # horror lore + story
    ("@CreepsMcPasta",       "true_crime_story", 4), # horror story reading
    ("@WolvenhollowStudios", "true_crime_story", 4), # horror animated story
    ("@ScaryInteresting",    "true_crime_story", 4), # suspense story shorts
    ("@UnsolvedMysteries",   "true_crime_story", 5), # mystery story structure
    ("@ColdCaseDetective",   "true_crime_story", 4), # investigation arc
    ("@Charismaoncommand",   "true_crime_story", 4), # behavior story analysis (great structure)


    # ══════════════════════════════════════════════════════════════════
    # REDDIT / KARMA FORMAT  ── relatable setup + judgment + twist ending
    # Key for training: but/therefore logic, obstacle escalation
    # ══════════════════════════════════════════════════════════════════

    ("@ProRevenge",          "reddit_story",   5),   # revenge setup → obstacle → payoff
    ("@MaliciousCompliance", "reddit_story",   5),   # clever rule-twist stories
    ("@NuclearRevenge",      "reddit_story",   5),   # extreme revenge arc
    ("@RSlash",              "reddit_story",   5),   # reading + reaction story format
    ("@InstantKarmaFails",   "reddit_story",   4),   # karma twist format
    ("@ChoiceStories",       "reddit_story",   4),   # branching story format
    ("@EntitledParents",     "reddit_story",   4),   # villain → karma story
    ("@BestofRSlash",        "reddit_story",   4),   # curated reddit stories
    ("@TabletopTalesYT",     "reddit_story",   4),   # DnD story arc (excellent escalation)
    ("@StoriesWithFlair",    "reddit_story",   4),   # story reading format
    ("@GrandmasBoyYT",       "reddit_story",   4),   # relatable generational story
    ("@DnDShorts",           "reddit_story",   4),   # tabletop story shorts


    # ══════════════════════════════════════════════════════════════════
    # WORLD BUILDING / LORE SHORTS  ── exposition as story
    # Great for training scene descriptions and environment narration
    # ══════════════════════════════════════════════════════════════════

    ("@HelloFutureMeFiction","worldbuild_story", 5), # story structure theory + examples
    ("@Oversimplified",      "worldbuild_story", 5), # history as story — incredible pacing
    ("@SamONellaAcademy",   "worldbuild_story", 5), # dark humor history — perfect story structure
    ("@TierZoo",             "worldbuild_story", 5), # nature as video game story (unique hook)
    ("@RealLifeLore",        "worldbuild_story", 4), # geography story
    ("@HalfAsInteresting",   "worldbuild_story", 4), # interesting facts as stories
    ("@MapMenChannel",       "worldbuild_story", 4), # geography story format
    ("@AlternateHistoryHub", "worldbuild_story", 4), # speculative world story
    ("@GeographyNow",        "worldbuild_story", 4), # country lore + story (already scraped but more content)
    ("@WhatiF",              "worldbuild_story", 4), # speculative story format
    ("@HistoryMarche",       "worldbuild_story", 4), # history story
    ("@LeMMinoYT",           "worldbuild_story", 5), # animated history/lore story
    ("@NerdWriter1",         "worldbuild_story", 5), # ideas as narrative, excellent structure
    ("@EveryFrameAPainting", "worldbuild_story", 5), # film story analysis (archived but transcripts exist)
    ("@KaptainKristin",      "worldbuild_story", 4), # pop culture story


    # ══════════════════════════════════════════════════════════════════
    # SCREENWRITING / STORY CRAFT  ── teaching narrative structure directly
    # Most directly useful for the Story Director: these creators EXPLAIN
    # the exact same frameworks the LLM needs to internalize
    # ══════════════════════════════════════════════════════════════════

    ("@StudioBinder",        "story_craft",    5),   # film technique + story structure
    ("@D4Dario",             "story_craft",    5),   # storytelling craft, tight lessons
    ("@JimHull",             "story_craft",    5),   # narrative theory, excellent breakdown
    ("@TaleFoundry",         "story_craft",    5),   # story theory + examples (underrated gem)
    ("@KM_Weiland",          "story_craft",    5),   # story structure deep-dives
    ("@BrianMcDonald",       "story_craft",    5),   # screenwriting craft
    ("@SaveTheCatBlake",     "story_craft",    5),   # Save the Cat story beats
    ("@WriteAboutDragons",   "story_craft",    4),   # Brandon Sanderson's creative writing lectures
    ("@BrandonSanderson",    "story_craft",    5),   # master storyteller, explicit craft lessons
    ("@HelloFutureMeFiction","story_craft",    5),   # story theory
    ("@FilmRiot",            "story_craft",    4),   # film making + story
    ("@FilmBooth",           "story_craft",    5),   # YouTube story strategy
    ("@CreatorScience",      "story_craft",    5),   # creator story strategy (Jenny Hoyos interview source)
    ("@Veritasium",          "story_craft",    5),   # science + story — perfect hook:payoff ratio


    # ══════════════════════════════════════════════════════════════════
    # DOCUMENTARY SHORTS  ── real-world story, strong hook structure
    # ══════════════════════════════════════════════════════════════════

    ("@MarkRober",           "doc_short",      5),   # engineering challenge story — incredible pacing
    ("@Yes_Theory",          "doc_short",      5),   # already in emotional_story, double weight
    ("@ColdfusionTV",        "doc_short",      4),   # tech story documentary
    ("@RealEngineering",     "doc_short",      4),   # engineering story
    ("@PracticalEngineer",   "doc_short",      4),   # engineering story shorts
    ("@Wendoverproductions", "doc_short",      4),   # logistics story
    ("@CGPGrey",             "doc_short",      5),   # idea as story — perfect pacing
    ("@3Blue1Brown",         "doc_short",      5),   # math as story (unbeatable structure)
    ("@TomScott",            "doc_short",      5),   # place story — "This is a video about X"
    ("@VoxDotCom",           "doc_short",      4),   # news as story
    ("@ElectroBoom",         "doc_short",      4),   # electrical engineering story (comedic arc)
    ("@BackyardScientist",   "doc_short",      3),   # experiment story
    ("@HowToMakeEverything", "doc_short",      3),   # process as story
    ("@ContraPoints",        "doc_short",      4),   # philosophy story
    ("@Philosophytube",      "doc_short",      4),   # philosophy narrative


    # ══════════════════════════════════════════════════════════════════
    # COMEDY STORY (tight arc)  ── setup → escalation → punchline payoff
    # Teaches the LLM comedic beat timing and subverted expectations
    # ══════════════════════════════════════════════════════════════════

    ("@CasuallyExplained",   "comedy_story",   5),   # dark humor + story, excellent timing
    ("@JacksFilms",          "comedy_story",   4),   # format subversion + story
    ("@SMii7Y",              "comedy_story",   4),   # gaming comedy story
    ("@KyrSP",               "comedy_story",   4),   # gaming comedy with story arc
    ("@TommyInnit",          "comedy_story",   3),   # chaos story (already in zackd)
    ("@TechLead",            "comedy_story",   4),   # satirical story format, great hooks
    ("@Slimecicle",          "comedy_story",   4),   # absurdist story (already in commentary)
    ("@Charismaoncommand",   "comedy_story",   4),   # charisma story analysis
    ("@DidYouKnowGaming",    "comedy_story",   4),   # game lore story
    ("@MatthewBrownson",     "comedy_story",   3),   # comedy shorts

]

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────
MIN_WEIGHT = 4          # Skip weight < 4 by default (change to 3 for more data)
MAX_WORKERS = 3         # Parallel channel scrapes (lower = safer on rate limits)
SHORTS_ONLY = True      # Only grab Shorts (< 65 sec) — most relevant for project
OUT_DIR = Path("story_v2_output")
TRANSCRIPTS_DIR = OUT_DIR / "transcripts"
ARCHIVES_DIR = OUT_DIR / "archives"

SYSTEM = (
    "You are a viral short-form video creator specializing in story-driven Shorts. "
    "You understand hook structure, emotional pacing, obstacle → twist → payoff beats, "
    "5th-grade reading level narration, and the but/therefore storytelling rule. "
    "Your scripts work in 30-60 seconds with 90%+ retention."
)

# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────
for d in [OUT_DIR, TRANSCRIPTS_DIR, ARCHIVES_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def seed_archive(handle, out_dir, archive_path):
    """Pre-populate archive file from already-downloaded json3s to skip re-fetching."""
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
        print(f"  [{handle}] archive: {len(archived | new_ids)} videos already done")


def scrape_channel(handle, category, weight):
    out_dir = TRANSCRIPTS_DIR / category / handle.lstrip("@")
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVES_DIR / f"{handle.lstrip('@')}.txt"
    seed_archive(handle, out_dir, archive_path)

    url = f"https://www.youtube.com/{handle}/shorts" if SHORTS_ONLY else f"https://www.youtube.com/{handle}"

    cmd = [
        "yt-dlp",
        "--write-auto-sub", "--sub-lang", "en", "--sub-format", "json3",
        "--skip-download", "--ignore-errors", "--no-warnings",
        "--download-archive", str(archive_path),
        # Rate limiting — critical to avoid YouTube blocking
        "--sleep-requests", "2",
        "--sleep-interval", "3",
        "--max-sleep-interval", "8",
        "--sleep-subtitles", "2",
        "-o", str(out_dir / "%(id)s.%(ext)s"),
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    saved = list(out_dir.glob("*.json3"))
    return {
        "handle": handle,
        "category": category,
        "weight": weight,
        "transcript_count": len(saved),
        "ok": len(saved) > 0,
    }


def parse_json3_timed(fpath):
    """Convert yt-dlp json3 to timestamped text — gives the LLM pacing signal."""
    try:
        data = json.load(open(fpath, encoding="utf-8"))
    except Exception:
        return ""
    lines = []
    for ev in data.get("events", []):
        t = ev.get("tStartMs", 0) / 1000.0
        words = []
        for seg in ev.get("segs", []):
            w = seg.get("utf8", "").strip()
            if w and w != "\n":
                words.append(w)
        text = re.sub(r"\s+", " ", " ".join(words)).strip()
        if text:
            lines.append(f"[{t:.1f}s] {text}")
    return "\n".join(lines)


def build_training_jsonl():
    examples = []
    skipped = 0

    for json3_file in TRANSCRIPTS_DIR.rglob("*.json3"):
        text = parse_json3_timed(json3_file)
        if len(text) < 120:
            skipped += 1
            continue

        category = json3_file.parent.parent.name
        channel = json3_file.parent.name
        vid_id = json3_file.stem.removesuffix(".en")

        # Match weight from channel list
        weight = next(
            (w for h, c, w in CHANNELS if h.lstrip("@").lower() == channel.lower()),
            3
        )

        # Category-specific system prompts for richer training signal
        if category in ("zackd_style",):
            user_prompt = (
                f"Write a punchy, cinematic short-form story script in the style of @{channel}. "
                "Strong hook in the first 2 seconds. Clear obstacle. Satisfying twist or payoff at the end."
            )
        elif category in ("animated_story", "pixel_3d_story"):
            user_prompt = (
                f"Write a short-form animated story script in the style of @{channel}. "
                "The narration should carry the story. Include natural pacing with timestamps. "
                "Hook → character moment → obstacle → payoff."
            )
        elif category in ("reddit_story",):
            user_prompt = (
                f"Write a short Reddit-style story script in the style of @{channel}. "
                "Setup the situation → introduce the jerk or obstacle → satisfying twist or karma ending."
            )
        elif category in ("true_crime_story",):
            user_prompt = (
                f"Write a suspenseful true crime short-form script in the style of @{channel}. "
                "Open with a shocking hook. Build dread. Deliver a reveal or twist."
            )
        elif category in ("emotional_story",):
            user_prompt = (
                f"Write an emotionally resonant short-form story script in the style of @{channel}. "
                "Make the viewer feel something. Hook → vulnerability → obstacle → heartfelt payoff."
            )
        elif category in ("story_craft", "commentary_story"):
            user_prompt = (
                f"Write an engaging short-form commentary script in the style of @{channel}. "
                "Open with a strong hook claim or question. Build with evidence or story. Land a clear point."
            )
        else:
            user_prompt = (
                f"Write a compelling short-form video script in the style of @{channel} "
                f"({category} format). Strong hook. Clear story arc. Tight payoff."
            )

        examples.append({
            "messages": [
                {"role": "system",    "content": SYSTEM},
                {"role": "user",      "content": user_prompt},
                {"role": "assistant", "content": text},
            ],
            "source": f"yt_transcript_{category}",
            "channel": channel,
            "channel_handle": f"@{channel}",
            "video_id": vid_id,
            "weight": weight,
            "format": "timed_transcript",
        })

    return examples, skipped


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # De-duplicate (same handle may appear in multiple categories)
    seen = {}
    deduped = []
    for handle, cat, weight in CHANNELS:
        key = handle.lower()
        if key not in seen:
            seen[key] = True
            deduped.append((handle, cat, weight))

    to_scrape = [(h, c, w) for h, c, w in deduped if w >= MIN_WEIGHT]
    print(f"Story Scraper v2")
    print(f"Channels to scrape: {len(to_scrape)} (weight >= {MIN_WEIGHT}, Shorts only: {SHORTS_ONLY})")
    print()

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scrape_channel, h, c, w): (h, c, w) for h, c, w in to_scrape}
        for i, future in enumerate(as_completed(futures), 1):
            h, c, w = futures[future]
            try:
                r = future.result(timeout=660)
                results.append(r)
                status = f"✓ {r['transcript_count']:4d} transcripts" if r["ok"] else "✗ 0 transcripts"
                print(f"[{i:3d}/{len(to_scrape)}] {h:35s} [{c:20s}] w={w}  {status}")
            except Exception as e:
                print(f"[{i:3d}/{len(to_scrape)}] {h:35s} ✗ ERROR: {str(e)[:80]}")

    # Save scrape log
    log_path = OUT_DIR / "scrape_log.json"
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2)

    # Build training JSONL
    print(f"\nBuilding training JSONL...")
    examples, skipped = build_training_jsonl()

    jsonl_path = Path("story_v2_examples.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    total_transcripts = sum(r.get("transcript_count", 0) for r in results)
    print(f"Total transcripts downloaded: {total_transcripts}")
    print(f"Training examples built:      {len(examples)}")
    print(f"Skipped (too short):          {skipped}")

    # Category breakdown
    from collections import Counter
    cats = Counter(ex["source"].replace("yt_transcript_", "") for ex in examples)
    print(f"\nBreakdown by category:")
    for cat, count in cats.most_common():
        print(f"  {cat:25s} {count:5d} examples")

    # Zip output
    zip_path = "story-v2-dataset.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path)
        zf.write(log_path)
        for jf in TRANSCRIPTS_DIR.rglob("*.json3"):
            zf.write(jf, str(jf.relative_to(OUT_DIR)))

    size_mb = Path(zip_path).stat().st_size / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"Output file: {zip_path} ({size_mb:.1f} MB)")
    print(f"Upload story-v2-dataset.zip to Claude for merging into training_data_v7.")
    print()
    print("Channels that yielded 0 transcripts (may need handle fix):")
    zero = [r["handle"] for r in results if not r.get("ok")]
    for h in zero:
        print(f"  {h}")
