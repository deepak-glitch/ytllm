"""
Batch Comment Scraper
=====================
Reads every video ID from story_v2_examples.jsonl + story_v3_examples.jsonl,
fetches top comments for each via yt-dlp, and saves them for training.

Run on YOUR machine:
    python scrape_comments.py

Outputs:
    comments_raw.jsonl          — raw comments per video (checkpoint file)
    comment_training_data.jsonl — training-ready JSONL (run after scrape finishes)

Features:
    - Checkpointing — resumes from where it left off if interrupted
    - Concurrent workers (default 6) — ~1532 videos in ~20-40 min
    - Progress bar
    - Skips private/deleted videos gracefully
"""

import json, os, sys, time, subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# ── Auto-install ──────────────────────────────────────────────────────────────
def _pip(*pkgs):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs])

try:
    import yt_dlp
except ImportError:
    print("Installing yt-dlp...")
    _pip("yt-dlp")
    import yt_dlp

try:
    from tqdm import tqdm
except ImportError:
    _pip("tqdm")
    from tqdm import tqdm

# ── Config ────────────────────────────────────────────────────────────────────
WORKERS        = 6          # parallel workers — lower if you get rate-limited
MAX_COMMENTS   = 100        # top N comments per video
CHECKPOINT_FILE = Path("comments_raw.jsonl")
SOURCES = [
    Path("story_v2_examples.jsonl"),
    Path("story_v3_examples.jsonl"),
]

write_lock = Lock()


# ── Load video IDs ────────────────────────────────────────────────────────────

def load_video_ids() -> dict:
    """Returns {video_id: {channel, source_file}}"""
    ids = {}
    for src in SOURCES:
        if not src.exists():
            print(f"  ⚠️  {src} not found — skipping")
            continue
        for line in src.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                vid = d.get("video_id", "")
                if vid:
                    ids[vid] = {
                        "channel":     d.get("channel", "unknown"),
                        "source_file": str(src),
                    }
            except json.JSONDecodeError:
                pass
    return ids


def load_already_scraped() -> set:
    """Video IDs already in the checkpoint file."""
    done = set()
    if CHECKPOINT_FILE.exists():
        for line in CHECKPOINT_FILE.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                done.add(d["video_id"])
            except (json.JSONDecodeError, KeyError):
                pass
    return done


# ── Comment fetching ──────────────────────────────────────────────────────────

def fetch_comments(video_id: str, channel: str) -> dict | None:
    """
    Fetch top comments + metadata for one video.
    Returns a dict ready to write to JSONL, or None on failure.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        "quiet":       True,
        "no_warnings": True,
        "skip_download": True,
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

        raw_comments = info.get("comments") or []
        comments = [
            {
                "text":    c.get("text", "").strip(),
                "likes":   c.get("like_count", 0),
                "replies": c.get("reply_count", 0),
            }
            for c in raw_comments[:MAX_COMMENTS]
            if c.get("text", "").strip()
        ]
        # Sort by likes descending
        comments.sort(key=lambda x: x["likes"], reverse=True)

        return {
            "video_id":     video_id,
            "channel":      channel,
            "title":        info.get("title", ""),
            "views":        info.get("view_count", 0),
            "likes":        info.get("like_count", 0),
            "duration":     info.get("duration", 0),
            "upload_date":  info.get("upload_date", ""),
            "comment_count_fetched": len(comments),
            "comments":     comments,
            "scraped_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    except Exception as e:
        err = str(e)
        # Silently skip unavailable/private/deleted videos
        if any(x in err.lower() for x in ["private", "not available", "removed", "404"]):
            return None
        # Return error record so we don't keep retrying
        return {
            "video_id": video_id,
            "channel":  channel,
            "error":    err[:200],
            "comments": [],
            "comment_count_fetched": 0,
        }


# ── Writer ────────────────────────────────────────────────────────────────────

def append_result(result: dict):
    """Thread-safe append to checkpoint file."""
    with write_lock:
        with open(CHECKPOINT_FILE, "a") as f:
            f.write(json.dumps(result) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n🎬 Batch Comment Scraper")
    print("=" * 50)

    all_ids = load_video_ids()
    print(f"✅ Found {len(all_ids):,} unique video IDs")

    already_done = load_already_scraped()
    if already_done:
        print(f"   Checkpoint: {len(already_done):,} already scraped — resuming")

    todo = {
        vid: meta
        for vid, meta in all_ids.items()
        if vid not in already_done
    }
    print(f"   Remaining:  {len(todo):,} videos to scrape")
    print(f"   Workers:    {WORKERS}")
    print(f"   Max comments/video: {MAX_COMMENTS}")
    print()

    if not todo:
        print("✅ Nothing left to scrape! Run build_comment_training.py next.")
        return

    success = 0
    errors  = 0
    skipped = 0

    items = list(todo.items())

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(fetch_comments, vid, meta["channel"]): vid
            for vid, meta in items
        }

        with tqdm(total=len(futures), unit="video", desc="Scraping") as pbar:
            for future in as_completed(futures):
                vid = futures[future]
                try:
                    result = future.result()
                    if result is None:
                        skipped += 1
                    elif result.get("error"):
                        errors += 1
                        append_result(result)
                    else:
                        success += 1
                        append_result(result)
                except Exception as e:
                    errors += 1
                    append_result({
                        "video_id": vid,
                        "channel":  todo[vid]["channel"],
                        "error":    str(e)[:200],
                        "comments": [],
                        "comment_count_fetched": 0,
                    })
                finally:
                    pbar.update(1)
                    pbar.set_postfix(ok=success, err=errors, skip=skipped)

    print(f"\n✅ Done!")
    print(f"   Successful:  {success:,}")
    print(f"   Errors:      {errors:,}")
    print(f"   Skipped:     {skipped:,} (private/deleted)")
    print(f"\n💾 Saved to: {CHECKPOINT_FILE}")
    print(f"\n▶️  Next step: python build_comment_training.py")


if __name__ == "__main__":
    main()
