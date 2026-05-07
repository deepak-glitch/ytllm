"""
Scrape ALL Shorts transcripts from style-reference channels (no per-channel limit).

Run on YOUR machine:
  python3 run_extra_channels.py

Output: extra-channels-dataset.zip in cwd. Upload to Claude.
"""
import json, re, subprocess, sys, zipfile
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "yt-dlp", "-q"])

CHANNELS = [
    ("@Superficial2",      "story_reference"),
    ("@ithinkitsgeorge",   "story_reference"),
    ("@HeyJohnScott",      "story_reference"),
    ("@JennyHoyos",        "story_reference"),
    ("@pixelbeefshorts",   "story_reference"),
    ("@NotableNet",        "story_reference"),
    ("@Ripped-x",          "story_reference"),
    ("@Chupes-p34",        "story_reference"),
    ("@HisYTStory",        "story_reference"),
    ("@rennrat78",         "story_reference"),
    ("@Zynerroid00123",    "story_reference"),
    ("@DailyPretzel",      "story_reference"),
    ("@polemod",           "story_reference"),
    ("@Bobbie-26",         "story_reference"),
    ("@Minutemadness5",    "story_reference"),
    ("@ProfessorMrAlex",   "story_reference"),
    ("@DevRamo",           "story_reference"),
    ("@Cutiepaw-3D",       "story_reference"),
    ("@eng_universelabz",  "story_reference"),
    ("@lifeinpoly",        "story_reference"),
    ("@LowPolyShorts",     "story_reference"),
    ("@RoStoriezYT",       "story_reference"),
    ("@Christs_Echo",      "story_reference"),
    ("@Zupaya",            "story_reference"),
    ("@RealOneLovey",      "story_reference"),
    ("@Christify777",      "story_reference"),
]

OUT = Path("extra_channels_output")
TRANSCRIPTS = OUT / "transcripts"
ARCHIVES = OUT / "archives"
OUT.mkdir(exist_ok=True)
TRANSCRIPTS.mkdir(exist_ok=True)
ARCHIVES.mkdir(exist_ok=True)

SYSTEM = ("You are a viral short-form video creator coach specializing in pixel art animated "
          "Shorts. Expert in hooks, story structure, retention, and visual storytelling.")


def seed_archive(handle, out_dir, archive_path):
    """Pre-populate yt-dlp's --download-archive from already-downloaded json3 files
    so resumed runs skip the metadata page fetch entirely (those fetches are what
    trigger YouTube rate limits on big channels)."""
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
    print(f"  archive: {len(archived | new_ids)} videos already done (will skip)")


def scrape_channel(handle, category):
    out_dir = TRANSCRIPTS / category / handle.lstrip("@")
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVES / f"{handle.lstrip('@')}.txt"
    seed_archive(handle, out_dir, archive_path)
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
    print(f"Scraping {handle} (no limit)...")
    subprocess.run(cmd)
    saved = list(out_dir.glob("*.json3"))
    print(f"  {handle}: {len(saved)} transcripts")
    return len(saved)


def parse_json3_timed(fpath):
    """Return one line per caption event prefixed with [seconds] timestamp."""
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
            lines.append(f"[{t:.1f}] {text}")
    return "\n".join(lines)


if __name__ == "__main__":
    for h, c in CHANNELS:
        scrape_channel(h, c)

    examples = []
    for f in TRANSCRIPTS.rglob("*.json3"):
        text = parse_json3_timed(f)
        if len(text) < 100:
            continue
        category = f.parent.parent.name
        channel = f.parent.name
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content":
                    f"Write a paced short-form video script in the style of @{channel} with timing markers."},
                {"role": "assistant", "content": text},
            ],
            "source": f"yt_transcript_{category}",
            "channel": channel,
            "weight": 4,
            "format": "timed",
        })

    out_jsonl = Path("extra_channels_examples.jsonl")
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    zip_path = "extra-channels-dataset.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(out_jsonl)
        for jf in TRANSCRIPTS.rglob("*.json3"):
            zf.write(jf, str(jf.relative_to(OUT)))

    print(f"\n{'='*55}")
    print(f"Output: {zip_path}")
    print(f"Examples: {len(examples)}")
    print("Upload to Claude for merge into v5.")
