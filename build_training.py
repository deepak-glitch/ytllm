"""
build_training.py — Fast standalone Step 4
Reads checkpoints_api/ in parallel, builds training JSONL, merges into v9.
Run this instead of waiting for youtube_api_scraper.py Step 4.
"""
import os, json, re, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

try:
    from tqdm import tqdm
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "tqdm"])
    from tqdm import tqdm

CHECKPOINT_DIR  = Path("checkpoints_api")
OUT_RAW         = Path("api_raw.jsonl")
OUT_TRAINING    = Path("api_training.jsonl")
EXISTING_V8     = Path("training_data_v8.jsonl")
OUT_V9          = Path("training_data_v9.jsonl")
READ_WORKERS    = 32   # parallel file reads
MIN_WORDS       = 10

SYSTEM_PROMPT = (
    "You are a viral short-form video creator coach with deep expertise in "
    "YouTube Shorts storytelling, analytics, video feedback, and content strategy. "
    "You speak from real creator experience — direct, no fluff."
)

# ── Load checkpoints in parallel ─────────────────────────────────────────────
def _read_one(p: Path):
    try:
        rec = json.loads(p.read_text())
        return rec if not rec.get("error") else None
    except Exception:
        return None

def load_checkpoints_fast() -> list:
    paths = list(CHECKPOINT_DIR.glob("*.json"))
    print(f"   Reading {len(paths):,} checkpoint files ({READ_WORKERS} parallel)...")
    records = []
    with ThreadPoolExecutor(max_workers=READ_WORKERS) as pool:
        futures = {pool.submit(_read_one, p): p for p in paths}
        with tqdm(total=len(futures), desc="Loading", unit="f") as pbar:
            for future in as_completed(futures):
                rec = future.result()
                if rec:
                    records.append(rec)
                pbar.update(1)
    return records

# ── Training example builders ─────────────────────────────────────────────────
def _top_comments_text(comments, n=25):
    good = sorted(
        [c for c in comments if c.get("likes", 0) >= 2 and c.get("text", "")],
        key=lambda x: x["likes"], reverse=True,
    )
    return "\n".join(
        f'[{i+1}] ({c["likes"]} 👍) "{c["text"].strip()}"'
        for i, c in enumerate(good[:n])
    )

def make_examples(rec: dict) -> list:
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

    # 1. Transcript → script style
    if transcript and len(transcript.split()) >= MIN_WORDS:
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

    # 2. Transcript + comments → reaction analysis
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

    # 3. Story → predicted comments
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

    # 4. Magic moment (100k+ views)
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

    # 5. Comments-only hook
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

    # 6. Tags → story angle
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


def main():
    print("\n🔨 build_training.py — Fast Step 4")
    print("=" * 60)

    if not CHECKPOINT_DIR.exists() or not any(CHECKPOINT_DIR.glob("*.json")):
        print("❌ No checkpoints found in checkpoints_api/")
        print("   Make sure you're in the ytllm_v2 directory.")
        sys.exit(1)

    # Load all checkpoints in parallel
    t0 = time.time()
    records = load_checkpoints_fast()
    print(f"   Loaded {len(records):,} records in {time.time()-t0:.1f}s")
    print()

    # Build training examples
    print("📊 Building training examples...")
    all_examples = []
    for rec in tqdm(records, desc="Building", unit="v"):
        all_examples.extend(make_examples(rec))
    print(f"   Generated {len(all_examples):,} examples")
    print()

    # Write api_raw.jsonl
    print(f"💾 Writing {OUT_RAW}...")
    with open(OUT_RAW, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    print(f"   {OUT_RAW.stat().st_size / 1_048_576:.1f} MB")

    # Write api_training.jsonl
    print(f"💾 Writing {OUT_TRAINING}...")
    with open(OUT_TRAINING, "w") as f:
        for ex in all_examples:
            f.write(json.dumps(ex) + "\n")
    print(f"   {OUT_TRAINING.stat().st_size / 1_048_576:.1f} MB")

    # Merge v8 + new → v9
    print(f"💾 Merging into {OUT_V9}...")
    merged, seen_ids = 0, set()
    with open(OUT_V9, "w") as f:
        if EXISTING_V8.exists():
            for line in EXISTING_V8.read_text().splitlines():
                if line.strip():
                    try:
                        ex = json.loads(line)
                        key = ex.get("video_id","") + ex.get("source","")
                        if key not in seen_ids:
                            seen_ids.add(key); f.write(line + "\n"); merged += 1
                    except Exception:
                        pass
        for ex in all_examples:
            key = ex.get("video_id","") + ex.get("source","")
            if key not in seen_ids:
                seen_ids.add(key); f.write(json.dumps(ex) + "\n"); merged += 1

    type_counts = Counter(ex["source"] for ex in all_examples)
    print(f"\n{'='*60}")
    print(f"✅ DONE")
    print(f"   Checkpoint records:   {len(records):,}")
    print(f"   New examples:         {len(all_examples):,}")
    print(f"   v9 total (v8 + new):  {merged:,}")
    print(f"   {OUT_V9.stat().st_size / 1_048_576:.1f} MB")
    print()
    print("📊 Example types:")
    for src, cnt in type_counts.most_common():
        print(f"   {src:35s} {cnt:>6,}")
    print()
    print("▶️  Download: run the download cell in Colab")


if __name__ == "__main__":
    main()
