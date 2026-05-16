"""
Story Director LLM — YouTube Channel Transcript Scraper v2
─────────────────────────────────────────────────────────────────────────────
Narration-focused curated channel list with full pipeline:
  1. Try /shorts URL with browser cookies (bypasses age/bot blocks)
  2. Fall back to /videos URL with duration filter
  3. If no auto-subs available, use Whisper to transcribe (optional)

Run on YOUR machine:
  pip install yt-dlp
  pip install openai-whisper       # only if USE_WHISPER_FALLBACK = True
  python3 scrape_story_v2.py

Output: story-v2-dataset.zip → upload back to Claude.
─────────────────────────────────────────────────────────────────────────────
"""

import os, json, re, glob, subprocess, sys, shutil, zipfile, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# AUTO-INSTALL DEPENDENCIES
# ─────────────────────────────────────────────
def _pip_install(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"],
                   check=False)

# yt-dlp (required)
try:
    import yt_dlp  # noqa
except ImportError:
    print("Installing yt-dlp...")
    _pip_install("yt-dlp")

# openai-whisper (for fallback transcription)
_WHISPER_AVAILABLE = False
try:
    import whisper  # noqa
    _WHISPER_AVAILABLE = True
except ImportError:
    print("Installing openai-whisper (one-time, ~1 GB download)...")
    _pip_install("openai-whisper")
    try:
        import whisper  # noqa
        _WHISPER_AVAILABLE = True
    except ImportError:
        print("WARNING: Whisper install failed. Whisper fallback will be skipped.")
        _WHISPER_AVAILABLE = False

# torch — needed for CUDA GPU detection.
# If your NVIDIA GPU is not detected, install the CUDA-enabled build:
#   pip install torch --index-url https://download.pytorch.org/whl/cu121
try:
    import torch as _torch
    _TORCH_AVAILABLE = True
except ImportError:
    _pip_install("torch")
    try:
        import torch as _torch
        _TORCH_AVAILABLE = True
    except ImportError:
        _TORCH_AVAILABLE = False

# ffmpeg (Whisper needs this on PATH). On Windows install manually if missing.
if shutil.which("ffmpeg") is None:
    print("WARNING: ffmpeg not found on PATH. Whisper transcription will fail.")
    print("         Windows: download from https://ffmpeg.org/download.html and add to PATH")
    print("         Linux:   sudo apt install ffmpeg")
    print("         macOS:   brew install ffmpeg")

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG — edit these to taste
# ═════════════════════════════════════════════════════════════════════════════

# Browser to pull cookies from (bypasses age-gates + YouTube bot detection)
# Options: "firefox", "chrome", "edge", "safari", "brave", "opera"
# Set to None to disable cookies (some channels will fail)
COOKIES_BROWSER = "chrome"

# Whisper transcription fallback for channels without auto-subs
# Auto-runs when a channel returns 0 transcripts from /shorts AND /videos.
# - Requires ffmpeg on PATH (script will warn if missing)
# - GPU recommended; "tiny" model = fastest, "base" = balanced, "small"+ = best
# - WHISPER_MAX_VIDEOS_PER_CHANNEL caps audio downloads per failing channel
USE_WHISPER_FALLBACK = True
WHISPER_MODEL_SIZE = "base"        # tiny, base, small, medium, large
WHISPER_MAX_VIDEOS_PER_CHANNEL = 30

# GPU selection for Whisper.
# "auto"   → prefer cuda:1 (NVIDIA dedicated) when 2+ GPUs detected,
#             else cuda:0, else cpu.
# "cuda:1" → force NVIDIA RTX (GPU 1 on most laptops with iGPU + dGPU)
# "cuda:0" → force GPU 0
# "cpu"    → force CPU
WHISPER_DEVICE = "auto"

MAX_VIDEOS_PER_CHANNEL = 150
MIN_PRIORITY = 3
MAX_WORKERS = 3                    # yt-dlp parallel channel downloads
OUT_DIR = Path("story_v2_transcripts")
OUT_DIR.mkdir(exist_ok=True)


# ═════════════════════════════════════════════════════════════════════════════
# CURATED CHANNEL LIST — narration-heavy storytellers
# These channels almost always have auto-generated subtitles because
# they speak throughout (narration, voiceover, or talking head).
# Verified handles via web search.
# ═════════════════════════════════════════════════════════════════════════════
CHANNELS = [

    # ── ANIMATED NARRATION STORY (Superficial2-vibe, but with narration) ──
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

    # ── DOCUMENTARY NARRATION SHORTS ──
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
    ("@SamONellaAcademy",   "worldbuild_story", 5),
    ("@TierZoo",             "worldbuild_story", 5),
    ("@Nerdwriter1",         "worldbuild_story", 5),
    ("@LEMMiNO",             "worldbuild_story", 5),
    ("@HelloFutureMe",       "worldbuild_story", 5),
    ("@halfasinteresting",   "worldbuild_story", 4),
    ("@MapMen",              "worldbuild_story", 4),
    ("@AlternateHistoryHub", "worldbuild_story", 4),
    ("@HistoryMarche",       "worldbuild_story", 4),
    ("@RealLifeLore",        "worldbuild_story", 4),

    # ── STORY-DRIVEN COMMENTARY (talking head, always has subs) ──
    ("@drewisgooden",        "commentary_story", 5),
    ("@Danny-Gonzalez",      "commentary_story", 5),
    ("@EddyBurback",         "commentary_story", 5),
    ("@KurtisConner",        "commentary_story", 4),
    ("@penguinz0",           "commentary_story", 4),   # MoistCr1TiKaL
    ("@JarvisJohnson",       "commentary_story", 4),
    ("@ScottTheWoz",         "commentary_story", 4),
    ("@SunnyV2",             "commentary_story", 4),
    ("@EmpLemon",            "commentary_story", 5),

    # ── STORY CRAFT / SCREENWRITING (talking head, always has subs) ──
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


# ═════════════════════════════════════════════════════════════════════════════
# WHISPER MODEL LOADING (lazy)
# ═════════════════════════════════════════════════════════════════════════════
_whisper_model = None
_resolved_device = None   # cached result of _resolve_whisper_device()


def _resolve_whisper_device():
    """Pick the best available device for Whisper.

    Priority (when WHISPER_DEVICE="auto"):
      1. cuda:1  — NVIDIA RTX (dedicated GPU on dual-GPU laptops)
      2. cuda:0  — any CUDA GPU if only one is present
      3. cpu     — fallback when CUDA unavailable or torch not installed
    """
    global _resolved_device
    if _resolved_device is not None:
        return _resolved_device

    if WHISPER_DEVICE != "auto":
        _resolved_device = WHISPER_DEVICE
        return _resolved_device

    if _TORCH_AVAILABLE and _torch.cuda.is_available():
        n = _torch.cuda.device_count()
        if n >= 2:
            # GPU 0 is typically the Intel iGPU on laptops; GPU 1 is the NVIDIA dGPU
            _resolved_device = "cuda:1"
            gpu_name = _torch.cuda.get_device_name(1)
        else:
            _resolved_device = "cuda:0"
            gpu_name = _torch.cuda.get_device_name(0)
        print(f"Whisper GPU: {_resolved_device} ({gpu_name})")
    else:
        _resolved_device = "cpu"
        print("Whisper GPU: cpu (no CUDA detected — install torch+cu121 for GPU speed)")

    return _resolved_device


def get_whisper_model():
    """Lazy-load Whisper on the selected device. Returns None if unavailable."""
    global _whisper_model
    if _whisper_model is None:
        if not _WHISPER_AVAILABLE:
            return None
        import whisper
        device = _resolve_whisper_device()
        print(f"Loading Whisper model '{WHISPER_MODEL_SIZE}' on {device} (first time only)...")
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
        print(f"Whisper model loaded.")
    return _whisper_model


# ═════════════════════════════════════════════════════════════════════════════
# yt-dlp HELPERS
# ═════════════════════════════════════════════════════════════════════════════
# Auto-disabled if the browser is locking its cookie DB (e.g. Chrome is open).
_COOKIES_DISABLED = False

def _cookies_args():
    if COOKIES_BROWSER and not _COOKIES_DISABLED:
        return ["--cookies-from-browser", COOKIES_BROWSER]
    return []


def _maybe_disable_cookies(stderr_text):
    """If yt-dlp couldn't read the browser cookie DB, disable cookies for all
    future calls so the run can keep going."""
    global _COOKIES_DISABLED
    if _COOKIES_DISABLED or not stderr_text:
        return False
    s = stderr_text.lower()
    cookie_errors = [
        ("could not copy" in s and "cookie database" in s),  # Chrome DB locked
        "could not find a cookie" in s,                        # No browser cookie DB
        "failed to decrypt with dpapi" in s,                   # Chrome v127+ app-bound encryption
        "failed to decrypt cookie" in s,                       # generic decrypt failure
        "no such browser" in s,
    ]
    if any(cookie_errors):
        _COOKIES_DISABLED = True
        print(f"  ⚠ Browser cookie access failed ({COOKIES_BROWSER}). "
              f"Continuing WITHOUT cookies for the rest of the run.")
        return True
    return False


def _build_subs_cmd(handle, tab, out_dir, max_duration):
    url = f"https://www.youtube.com/{handle}{tab}"
    cmd = [
        "yt-dlp",
        *_cookies_args(),
        "--write-auto-sub",
        "--sub-lang", "en",
        "--sub-format", "json3",
        "--skip-download",
        "--ignore-errors",
        "--no-warnings",
        "--max-downloads", str(MAX_VIDEOS_PER_CHANNEL),
        "-o", str(out_dir / "%(id)s.%(ext)s"),
    ]
    if max_duration is not None:
        cmd.extend(["--match-filter", f"duration < {max_duration} | !duration"])
    cmd.append(url)
    return cmd


def run_ytdlp_subs(handle, tab, out_dir, max_duration=None):
    """Try to download auto-subs. If cookie DB is locked, retry without cookies."""
    try:
        result = subprocess.run(
            _build_subs_cmd(handle, tab, out_dir, max_duration),
            capture_output=True, text=True, timeout=500,
        )
        if _maybe_disable_cookies(result.stderr):
            result = subprocess.run(
                _build_subs_cmd(handle, tab, out_dir, max_duration),
                capture_output=True, text=True, timeout=500,
            )
        return result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT after 500s"


def list_channel_video_ids(handle, tab, max_count):
    """Get video IDs from a channel tab. Retries without cookies on cookie lock."""
    url = f"https://www.youtube.com/{handle}{tab}"

    def _build():
        return [
            "yt-dlp",
            *_cookies_args(),
            "--flat-playlist",
            "--print", "%(id)s",
            "--playlist-end", str(max_count),
            "--ignore-errors",
            "--no-warnings",
            url,
        ]

    try:
        result = subprocess.run(_build(), capture_output=True, text=True, timeout=120)
        if _maybe_disable_cookies(result.stderr):
            result = subprocess.run(_build(), capture_output=True, text=True, timeout=120)
        ids = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
        return ids
    except subprocess.TimeoutExpired:
        return []


def whisper_transcribe_video(video_id, out_dir):
    """Download audio for one video and transcribe with Whisper.
    Returns True if a transcript was written."""
    out_path = out_dir / f"{video_id}.whisper.txt"
    if out_path.exists():
        return True

    with tempfile.TemporaryDirectory() as tmp:
        audio_template = str(Path(tmp) / "%(id)s.%(ext)s")

        def _build():
            return [
                "yt-dlp",
                *_cookies_args(),
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "5",
                "--no-warnings",
                "--ignore-errors",
                "-o", audio_template,
                f"https://www.youtube.com/watch?v={video_id}",
            ]

        try:
            r = subprocess.run(_build(), capture_output=True, text=True, timeout=180)
            if _maybe_disable_cookies(r.stderr):
                subprocess.run(_build(), capture_output=True, timeout=180)
        except subprocess.TimeoutExpired:
            return False

        mp3_files = list(Path(tmp).glob("*.mp3"))
        if not mp3_files:
            return False

        try:
            model = get_whisper_model()
            if model is None:
                return False
            use_fp16 = _resolve_whisper_device().startswith("cuda")
            result = model.transcribe(str(mp3_files[0]), fp16=use_fp16)
            text = result.get("text", "").strip()
            if len(text) < 80:
                return False
            out_path.write_text(text, encoding="utf-8")
            return True
        except Exception as e:
            print(f"  Whisper error on {video_id}: {str(e)[:100]}")
            return False


# ═════════════════════════════════════════════════════════════════════════════
# SCRAPE ONE CHANNEL
# ═════════════════════════════════════════════════════════════════════════════
def scrape_channel(handle, category, priority):
    out = OUT_DIR / category / handle.lstrip("@")
    out.mkdir(parents=True, exist_ok=True)

    # Step 1: try /shorts (no duration filter — shorts are already short)
    _, err1 = run_ytdlp_subs(handle, "/shorts", out, max_duration=None)
    sub_count = len(list(out.glob("*.json3")))

    # Step 2: if no subs, try /videos with duration filter
    used_videos = False
    err2 = ""
    if sub_count == 0:
        _, err2 = run_ytdlp_subs(handle, "/videos", out, max_duration=300)
        sub_count = len(list(out.glob("*.json3")))
        used_videos = True

    # Step 3: if still nothing AND Whisper enabled+installed, transcribe top N
    whisper_count = 0
    if sub_count == 0 and USE_WHISPER_FALLBACK and _WHISPER_AVAILABLE:
        # Try /shorts tab first for IDs, then /videos
        video_ids = list_channel_video_ids(handle, "/shorts", WHISPER_MAX_VIDEOS_PER_CHANNEL)
        if not video_ids:
            video_ids = list_channel_video_ids(handle, "/videos", WHISPER_MAX_VIDEOS_PER_CHANNEL)
        for vid in video_ids:
            if whisper_transcribe_video(vid, out):
                whisper_count += 1

    # Build error snippet for reporting
    err_snippet = ""
    total = sub_count + whisper_count
    if total == 0:
        combined = (err2 or err1 or "").strip().split("\n")
        for line in reversed(combined):
            if "ERROR" in line or "WARNING" in line or "TIMEOUT" in line:
                err_snippet = line[:130]
                break
        if not err_snippet and combined:
            err_snippet = combined[-1][:130]

    return {
        "handle": handle,
        "category": category,
        "priority": priority,
        "sub_count": sub_count,
        "whisper_count": whisper_count,
        "total": total,
        "used_videos_tab": used_videos,
        "status": "ok" if total > 0 else "no_transcripts",
        "error": err_snippet,
    }


# ═════════════════════════════════════════════════════════════════════════════
# TRANSCRIPT PARSING + JSONL BUILDING
# ═════════════════════════════════════════════════════════════════════════════
def parse_json3_transcript(filepath):
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
    stats = {"written": 0, "skipped_short": 0, "from_subs": 0, "from_whisper": 0}

    with open(jsonl_path, "w", encoding="utf-8") as out_f:
        # json3 (auto-subs)
        for f in Path(out_dir).rglob("*.json3"):
            text = parse_json3_transcript(f)
            if len(text) < 80:
                stats["skipped_short"] += 1
                continue
            vid_id = f.stem.removesuffix(".en")
            channel = f.parent.name
            category = f.parent.parent.name
            out_f.write(json.dumps({
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": f"Write a short-form video script in the style of @{channel} ({category} category)."},
                    {"role": "assistant", "content": text}
                ],
                "source": f"youtube_transcript_{category}",
                "channel": channel,
                "video_id": vid_id,
                "weight": 4,
                "transcript_source": "auto_subs",
            }) + "\n")
            stats["written"] += 1
            stats["from_subs"] += 1

        # Whisper transcripts
        for f in Path(out_dir).rglob("*.whisper.txt"):
            text = f.read_text(encoding="utf-8").strip()
            if len(text) < 80:
                stats["skipped_short"] += 1
                continue
            vid_id = f.stem.removesuffix(".whisper")
            channel = f.parent.name
            category = f.parent.parent.name
            out_f.write(json.dumps({
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user",   "content": f"Write a short-form video script in the style of @{channel} ({category} category)."},
                    {"role": "assistant", "content": text}
                ],
                "source": f"youtube_transcript_{category}",
                "channel": channel,
                "video_id": vid_id,
                "weight": 4,
                "transcript_source": "whisper",
            }) + "\n")
            stats["written"] += 1
            stats["from_whisper"] += 1

    return jsonl_path, stats


# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    to_scrape = [(h, c, p) for h, c, p in CHANNELS if p >= MIN_PRIORITY]
    print(f"Story Scraper v2")
    print(f"Channels: {len(to_scrape)} (priority >= {MIN_PRIORITY})")
    print(f"Cookies from browser: {COOKIES_BROWSER or 'DISABLED'}")
    whisper_label = f"ENABLED ({WHISPER_MODEL_SIZE}, device={WHISPER_DEVICE})" if USE_WHISPER_FALLBACK else "DISABLED"
    print(f"Whisper fallback: {whisper_label}")
    print(f"Strategy per channel: /shorts → /videos (<300s) → whisper")
    print()

    metadata_log = []
    failed = []

    # NOTE: if Whisper is enabled, run channels sequentially to avoid GPU contention
    workers = 1 if USE_WHISPER_FALLBACK else MAX_WORKERS

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(scrape_channel, h, c, p): (h, c, p) for h, c, p in to_scrape}
        for i, future in enumerate(as_completed(futures), 1):
            h, c, p = futures[future]
            try:
                r = future.result(timeout=3600)
                metadata_log.append(r)
                if r["total"] > 0:
                    src = []
                    if r["sub_count"]: src.append(f"{r['sub_count']} subs")
                    if r["whisper_count"]: src.append(f"{r['whisper_count']} whisper")
                    tag = " [videos]" if r["used_videos_tab"] else ""
                    print(f"[{i:3d}/{len(to_scrape)}] {h:25s} ✓ {' + '.join(src)}{tag}")
                else:
                    print(f"[{i:3d}/{len(to_scrape)}] {h:25s} ✗ 0  {r['error']}")
            except Exception as e:
                failed.append(h)
                print(f"[{i:3d}/{len(to_scrape)}] {h:25s} ✗ EXCEPTION: {str(e)[:80]}")

    with open("story_v2_scrape_log.json", "w") as f:
        json.dump(metadata_log, f, indent=2)

    total_subs = sum(r["sub_count"] for r in metadata_log)
    total_whisper = sum(r["whisper_count"] for r in metadata_log)
    print(f"\n{'='*60}")
    print(f"Auto-subs transcripts: {total_subs}")
    print(f"Whisper transcripts:   {total_whisper}")
    print(f"Channels that failed:  {sum(1 for r in metadata_log if r['total']==0)}")

    print(f"\nBuilding training JSONL...")
    jsonl_path, stats = build_jsonl(str(OUT_DIR))
    print(f"Total training examples: {stats['written']}")
    print(f"  from auto-subs:  {stats['from_subs']}")
    print(f"  from Whisper:    {stats['from_whisper']}")
    print(f"  skipped (short): {stats['skipped_short']}")

    print("\nZipping...")
    with zipfile.ZipFile("story-v2-dataset.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path)
        zf.write("story_v2_scrape_log.json")
        for f in Path(OUT_DIR).rglob("*.json3"):
            zf.write(f)
        for f in Path(OUT_DIR).rglob("*.whisper.txt"):
            zf.write(f)

    size_mb = Path("story-v2-dataset.zip").stat().st_size / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"Output: story-v2-dataset.zip ({size_mb:.1f} MB)")
    print(f"Upload to Claude for merge into training_data_v7.")

    from collections import Counter
    cats = Counter(r["category"] for r in metadata_log)
    print(f"\nBy category:")
    for cat in cats:
        n_chan = sum(1 for r in metadata_log if r["category"] == cat)
        n_trans = sum(r["total"] for r in metadata_log if r["category"] == cat)
        print(f"  {cat:25s} {n_chan:3d} channels | {n_trans:5d} transcripts")

    zero = [r["handle"] for r in metadata_log if r["total"] == 0]
    if zero:
        print(f"\nChannels with 0 transcripts:")
        for h in zero:
            print(f"  {h}")
