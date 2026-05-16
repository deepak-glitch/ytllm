"""
Story Director LLM — YouTube Channel Transcript Scraper v3
─────────────────────────────────────────────────────────────────────────────
Targets ONLY the 58 channels that returned 0 transcripts in v2.
Strategy per channel:
  1. /shorts with Edge cookies (handles age-gates, bot detection)
  2. /videos with Edge cookies + duration filter
  3. Whisper fallback — ONLY if cookie-based subs returned 0

Run on YOUR machine:
  pip install yt-dlp openai-whisper
  python scrape_story_v3.py

Output: story-v3-dataset.zip → upload back to Claude.
─────────────────────────────────────────────────────────────────────────────
"""

import os, json, re, glob, subprocess, sys, shutil, zipfile, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────
# AUTO-INSTALL
# ─────────────────────────────────────────────
def _pip_install(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=False)

try:
    import yt_dlp  # noqa
except ImportError:
    print("Installing yt-dlp...")
    _pip_install("yt-dlp")

_WHISPER_AVAILABLE = False
try:
    import whisper  # noqa
    _WHISPER_AVAILABLE = True
except ImportError:
    print("Installing openai-whisper (one-time, ~1 GB)...")
    _pip_install("openai-whisper")
    try:
        import whisper  # noqa
        _WHISPER_AVAILABLE = True
    except ImportError:
        print("WARNING: Whisper install failed — fallback disabled.")

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

if shutil.which("ffmpeg") is None:
    print("WARNING: ffmpeg not found on PATH. Whisper transcription will fail.")
    print("         Windows: download from https://ffmpeg.org/download.html and add to PATH")

# ═════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═════════════════════════════════════════════════════════════════════════════
COOKIES_BROWSER = "edge"          # User is logged in as 18+ on Edge

USE_WHISPER_FALLBACK = True       # Only triggers if cookie subs return 0
WHISPER_MODEL_SIZE = "base"       # tiny / base / small / medium / large
WHISPER_MAX_VIDEOS_PER_CHANNEL = 20
WHISPER_DEVICE = "auto"           # auto / cuda:1 / cuda:0 / cpu

MAX_VIDEOS_PER_CHANNEL = 150
MIN_PRIORITY = 3
MAX_DURATION_SEC = 600
MAX_WORKERS = 3                   # parallel yt-dlp channels (reduced when Whisper on)
OUT_DIR = Path("story_v3_transcripts")
OUT_DIR.mkdir(exist_ok=True)


# ═════════════════════════════════════════════════════════════════════════════
# CHANNELS — only the 58 that failed in v2
# (Excludes: @Haminations, @jaidenanimations, @itsalexclark, @TheOdd1sOut, @Veritasium)
# ═════════════════════════════════════════════════════════════════════════════
CHANNELS = [
    # ── ANIMATED NARRATION STORY (9) ──
    ("@inanutshell",         "animated_story",   5),   # Kurzgesagt
    ("@TED-Ed",              "animated_story",   5),
    ("@danielthrasher",      "animated_story",   4),
    ("@SomethingElseYT",     "animated_story",   4),
    ("@GingerPale",          "animated_story",   4),
    ("@Domics",              "animated_story",   4),
    ("@LetMeExplainStudios", "animated_story",   4),
    ("@SwooZie",             "animated_story",   4),
    ("@illymation",          "animated_story",   4),

    # ── DOCUMENTARY NARRATION (12) ──
    ("@MarkRober",           "doc_short",        5),
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

    # ── WORLDBUILDING / LORE NARRATION (11) ──
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

    # ── STORY-DRIVEN COMMENTARY (9) ──
    ("@drewisgooden",        "commentary_story", 5),
    ("@Danny-Gonzalez",      "commentary_story", 5),
    ("@EddyBurback",         "commentary_story", 5),
    ("@KurtisConner",        "commentary_story", 4),
    ("@penguinz0",           "commentary_story", 4),
    ("@JarvisJohnson",       "commentary_story", 4),
    ("@ScottTheWoz",         "commentary_story", 4),
    ("@SunnyV2",             "commentary_story", 4),
    ("@EmpLemon",            "commentary_story", 5),

    # ── STORY CRAFT / SCREENWRITING (4) ──
    ("@StudioBinder",        "story_craft",      5),
    ("@TaleFoundry",         "story_craft",      5),
    ("@BrandonSanderson",    "story_craft",      5),
    ("@FilmRiot",            "story_craft",      4),

    # ── EMOTIONAL / STORY NARRATION (5) ──
    ("@MyStoryAnimated",     "emotional_story",  5),
    ("@AnthonyPadilla",      "emotional_story",  5),
    ("@yestheory",           "emotional_story",  5),
    ("@Struthless",          "emotional_story",  5),
    ("@WongFuProductions",   "emotional_story",  4),

    # ── REDDIT / KARMA STORY NARRATION (2) ──
    ("@rSlash",              "reddit_story",     5),
    ("@DnDShorts",           "reddit_story",     4),

    # ── TRUE CRIME / SUSPENSE NARRATION (4) ──
    ("@Nightmind",           "true_crime_story", 4),
    ("@CreepsMcPasta",       "true_crime_story", 4),
    ("@ScaryInteresting",    "true_crime_story", 4),
    ("@Charismaoncommand",   "true_crime_story", 4),

    # ── NARRATION-HEAVY VIRAL SHORTS (2) ──
    ("@NasDaily",            "zackd_style",      5),
    ("@CasuallyExplained",   "zackd_style",      4),
]


# ═════════════════════════════════════════════════════════════════════════════
# WHISPER LAZY LOAD
# ═════════════════════════════════════════════════════════════════════════════
_whisper_model = None
_resolved_device = None

def _resolve_whisper_device():
    global _resolved_device
    if _resolved_device is not None:
        return _resolved_device
    if WHISPER_DEVICE != "auto":
        _resolved_device = WHISPER_DEVICE
        return _resolved_device
    if _TORCH_AVAILABLE and _torch.cuda.is_available():
        n = _torch.cuda.device_count()
        if n >= 2:
            _resolved_device = "cuda:1"
            print(f"Whisper GPU: cuda:1 ({_torch.cuda.get_device_name(1)})")
        else:
            _resolved_device = "cuda:0"
            print(f"Whisper GPU: cuda:0 ({_torch.cuda.get_device_name(0)})")
    else:
        _resolved_device = "cpu"
        print("Whisper GPU: cpu (no CUDA — install torch+cu121 for GPU speed)")
    return _resolved_device


def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        if not _WHISPER_AVAILABLE:
            return None
        import whisper
        device = _resolve_whisper_device()
        print(f"Loading Whisper '{WHISPER_MODEL_SIZE}' on {device} (first time only)...")
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
        print("Whisper model loaded.")
    return _whisper_model


# ═════════════════════════════════════════════════════════════════════════════
# yt-dlp HELPERS
# ═════════════════════════════════════════════════════════════════════════════
_COOKIES_DISABLED = False

def _cookies_args():
    if COOKIES_BROWSER and not _COOKIES_DISABLED:
        return ["--cookies-from-browser", COOKIES_BROWSER]
    return []


def _maybe_disable_cookies(stderr_text):
    global _COOKIES_DISABLED
    if _COOKIES_DISABLED or not stderr_text:
        return False
    s = stderr_text.lower()
    if (("could not copy" in s and "cookie database" in s)
            or "could not find a cookie" in s
            or "failed to decrypt with dpapi" in s
            or "failed to decrypt cookie" in s):
        _COOKIES_DISABLED = True
        print(f"  WARN: Cannot read {COOKIES_BROWSER} cookies (locked or DPAPI-encrypted). "
              f"Continuing WITHOUT cookies — Whisper will handle the rest.")
        return True
    return False


def _build_subs_cmd(handle, tab, out_dir, max_duration):
    url = f"https://www.youtube.com/{handle}{tab}"
    cmd = [
        "yt-dlp",
        *_cookies_args(),
        "--age-limit", "99",
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
    url = f"https://www.youtube.com/{handle}{tab}"
    def _build():
        return [
            "yt-dlp",
            *_cookies_args(),
            "--age-limit", "99",
            "--flat-playlist",
            "--print", "%(id)s",
            "--playlist-end", str(max_count),
            "--ignore-errors",
            "--no-warnings",
            url,
        ]
    try:
        r = subprocess.run(_build(), capture_output=True, text=True, timeout=120)
        if _maybe_disable_cookies(r.stderr):
            r = subprocess.run(_build(), capture_output=True, text=True, timeout=120)
        return [line.strip() for line in r.stdout.strip().split("\n") if line.strip()]
    except subprocess.TimeoutExpired:
        return []


def whisper_transcribe_video(video_id, out_dir):
    out_path = out_dir / f"{video_id}.whisper.txt"
    if out_path.exists():
        return True

    with tempfile.TemporaryDirectory() as tmp:
        audio_template = str(Path(tmp) / "%(id)s.%(ext)s")
        def _build():
            return [
                "yt-dlp",
                *_cookies_args(),
                "--age-limit", "99",
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

        mp3s = list(Path(tmp).glob("*.mp3"))
        if not mp3s:
            return False
        try:
            model = get_whisper_model()
            if model is None:
                return False
            use_fp16 = _resolve_whisper_device().startswith("cuda")
            result = model.transcribe(str(mp3s[0]), fp16=use_fp16)
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

    # 1. /shorts with cookies (no duration filter — shorts are short)
    _, err1 = run_ytdlp_subs(handle, "/shorts", out, max_duration=None)
    sub_count = len(list(out.glob("*.json3")))

    # 2. /videos with cookies + duration filter (only if /shorts returned nothing)
    used_videos = False
    err2 = ""
    if sub_count == 0:
        _, err2 = run_ytdlp_subs(handle, "/videos", out, max_duration=MAX_DURATION_SEC)
        sub_count = len(list(out.glob("*.json3")))
        used_videos = True

    # 3. Whisper fallback — only when cookies returned 0
    whisper_count = 0
    if sub_count == 0 and USE_WHISPER_FALLBACK and _WHISPER_AVAILABLE:
        video_ids = list_channel_video_ids(handle, "/shorts", WHISPER_MAX_VIDEOS_PER_CHANNEL)
        if not video_ids:
            video_ids = list_channel_video_ids(handle, "/videos", WHISPER_MAX_VIDEOS_PER_CHANNEL)
        for vid in video_ids:
            if whisper_transcribe_video(vid, out):
                whisper_count += 1

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
# JSONL BUILDING
# ═════════════════════════════════════════════════════════════════════════════
def parse_json3_transcript(filepath):
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        words = []
        for event in data.get("events", []):
            for seg in event.get("segs", []):
                utf8 = seg.get("utf8", "").strip()
                if utf8 and utf8 != "\n":
                    words.append(utf8)
        return re.sub(r"\s+", " ", " ".join(words)).strip()
    except Exception:
        return ""


def build_jsonl(out_dir):
    SYSTEM = (
        "You are a viral short-form video creator. Write engaging short-form story "
        "scripts with strong hooks, clear obstacles, satisfying twists, and tight "
        "payoffs. Every word must earn its place."
    )
    jsonl_path = Path("story_v3_examples.jsonl")
    stats = {"written": 0, "skipped_short": 0, "from_subs": 0, "from_whisper": 0}

    with open(jsonl_path, "w", encoding="utf-8") as out_f:
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
    print(f"Story Scraper v3")
    print(f"Channels: {len(to_scrape)} (priority >= {MIN_PRIORITY})")
    print(f"Cookies from browser: {COOKIES_BROWSER or 'DISABLED'}")
    whisper_label = f"ENABLED ({WHISPER_MODEL_SIZE}, device={WHISPER_DEVICE})" if USE_WHISPER_FALLBACK else "DISABLED"
    print(f"Whisper fallback: {whisper_label} (triggers only when cookies return 0)")
    print(f"Strategy per channel: /shorts -> /videos (<{MAX_DURATION_SEC}s) -> whisper")
    print()

    metadata_log = []
    failed = []

    # Sequential when Whisper enabled to avoid GPU contention
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
                    print(f"[{i:3d}/{len(to_scrape)}] {h:25s} OK {' + '.join(src)}{tag}")
                else:
                    print(f"[{i:3d}/{len(to_scrape)}] {h:25s} FAIL 0  {r['error']}")
            except Exception as e:
                failed.append(h)
                print(f"[{i:3d}/{len(to_scrape)}] {h:25s} EXCEPTION: {str(e)[:80]}")

    with open("story_v3_scrape_log.json", "w", encoding="utf-8") as f:
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
    with zipfile.ZipFile("story-v3-dataset.zip", "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(jsonl_path)
        zf.write("story_v3_scrape_log.json")
        for f in Path(OUT_DIR).rglob("*.json3"):
            zf.write(f)
        for f in Path(OUT_DIR).rglob("*.whisper.txt"):
            zf.write(f)

    size_mb = Path("story-v3-dataset.zip").stat().st_size / 1024 / 1024
    print(f"\n{'='*60}")
    print(f"Output: story-v3-dataset.zip ({size_mb:.1f} MB)")
    print(f"Upload to Claude for merge into training data.")

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
