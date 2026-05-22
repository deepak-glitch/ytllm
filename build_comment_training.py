"""
Build Comment Training Data
============================
Reads comments_raw.jsonl (output of scrape_comments.py) and pairs each video's
comments with its transcript/story from story_v2/v3_examples.jsonl.

Creates two new training entry types:

  TYPE A — Comment Reaction Analysis
    User:      "Here is a transcript from a viral short. What did the audience
                respond to most? [TRANSCRIPT]"
    Assistant: "Based on the top comments: [ANALYSIS]"

  TYPE B — Story → Predicted Comments
    User:      "Predict how the audience will react to this story: [STORY]"
    Assistant: "Top comment patterns I'd expect: [PREDICTED REACTIONS]"

Run:
    python build_comment_training.py

Outputs:
    comment_training_data.jsonl — appended to training_data_v8.jsonl
"""

import json, sys, subprocess, re
from pathlib import Path
from collections import defaultdict
from typing import Optional

# ── Auto-install ──────────────────────────────────────────────────────────────
def _pip(*pkgs):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs])

try:
    from tqdm import tqdm
except ImportError:
    _pip("tqdm")
    from tqdm import tqdm

# ── Paths ─────────────────────────────────────────────────────────────────────
COMMENTS_RAW   = Path("comments_raw.jsonl")
STORY_SOURCES  = [Path("story_v2_examples.jsonl"), Path("story_v3_examples.jsonl")]
OUT_COMMENTS   = Path("comment_training_data.jsonl")
OUT_MERGED     = Path("training_data_v8.jsonl")

MIN_COMMENTS   = 5     # skip videos with fewer than this many comments
MIN_COMMENT_LIKES = 2  # only include comments with at least this many likes

SYSTEM_PROMPT = (
    "You are a viral short-form video creator coach with deep expertise in "
    "YouTube Shorts storytelling, analytics, video feedback, and content strategy. "
    "You speak from real creator experience — direct, no fluff."
)


# ── Load data ─────────────────────────────────────────────────────────────────

def load_comments() -> dict:
    """Returns {video_id: comment_record}"""
    data = {}
    if not COMMENTS_RAW.exists():
        print(f"❌ {COMMENTS_RAW} not found. Run scrape_comments.py first.")
        sys.exit(1)
    for line in COMMENTS_RAW.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            if d.get("video_id") and not d.get("error"):
                data[d["video_id"]] = d
        except json.JSONDecodeError:
            pass
    return data


def load_transcripts() -> dict:
    """Returns {video_id: {transcript, channel, ...}}"""
    data = {}
    for src in STORY_SOURCES:
        if not src.exists():
            continue
        for line in src.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                vid = d.get("video_id", "")
                if not vid:
                    continue
                # Extract transcript from the assistant message
                msgs = d.get("messages", [])
                transcript = ""
                for m in msgs:
                    if m.get("role") == "assistant":
                        transcript = m.get("content", "")
                        break
                data[vid] = {
                    "transcript": transcript,
                    "channel":    d.get("channel", ""),
                    "source":     str(src),
                }
            except json.JSONDecodeError:
                pass
    return data


# ── Comment analysis helpers ──────────────────────────────────────────────────

def top_comments_text(comments: list, n: int = 30) -> str:
    """Format top N comments for use in a prompt."""
    good = [c for c in comments if c.get("likes", 0) >= MIN_COMMENT_LIKES]
    good.sort(key=lambda x: x["likes"], reverse=True)
    lines = []
    for i, c in enumerate(good[:n], 1):
        likes = c.get("likes", 0)
        text  = c.get("text", "").strip()
        if text:
            lines.append(f'[{i}] ({likes} 👍) "{text}"')
    return "\n".join(lines)


def summarize_comment_patterns(comments: list) -> str:
    """
    Simple rule-based pattern extraction — groups comments into reaction categories.
    Returns a human-readable summary string.
    """
    texts = [c.get("text","").lower() for c in comments if c.get("text","")]

    patterns = {
        "laughter / humor":   ["lmao","lol","💀","😂","🤣","dead","crying","hilarious","funny"],
        "shock / disbelief":  ["no way","what","bro","wait","omg","oh my","can't believe","wtf"],
        "respect / admiration": ["respect","based","legend","king","queen","goat","chad","absolute"],
        "relatable":          ["same","me too","relatable","this is me","i do this","guilty"],
        "justice / karma":    ["karma","deserved","justice","got what","served","satisfying","payback"],
        "quote / reaction":   ['"', "'", ">>", "when he", "the moment", "when she"],
    }

    counts = defaultdict(int)
    for text in texts:
        for label, keywords in patterns.items():
            if any(kw in text for kw in keywords):
                counts[label] += 1

    if not counts:
        return "General positive engagement with no dominant pattern."

    total = len(texts)
    lines = []
    for label, count in sorted(counts.items(), key=lambda x: -x[1]):
        pct = count / total
        if pct >= 0.05:  # at least 5% of comments
            lines.append(f"- {label}: ~{pct:.0%} of comments")
    return "\n".join(lines) if lines else "Mixed reactions with no single dominant pattern."


# ── Training example builders ─────────────────────────────────────────────────

def make_type_a(video_id: str, title: str, channel: str,
                transcript: str, comments: list, views: int) -> Optional[dict]:
    """
    TYPE A: Transcript → Comment reaction analysis
    Teaches the model WHAT audiences respond to in a given story.
    """
    comments_text = top_comments_text(comments, n=30)
    if not comments_text:
        return None

    patterns = summarize_comment_patterns(comments)

    user_msg = (
        f"Watch this short-form video transcript from @{channel} ({views:,} views).\n"
        f'Title: "{title}"\n\n'
        f"TRANSCRIPT:\n{transcript[:1500]}\n\n"
        f"What did the audience respond to most? Summarize the comment reactions."
    )

    assistant_msg = (
        f"Looking at the top comments from this {views:,}-view video:\n\n"
        f"{comments_text}\n\n"
        f"REACTION PATTERNS:\n{patterns}\n\n"
        "What this tells us about the story:\n"
        f"The comment section shows the audience connected most with "
        f"the emotional payoff — comments cluster around "
        f"{'the most-liked moments' if comments else 'the key beats'}. "
        f"This is exactly the kind of reaction that drives replays and shares."
    )

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ],
        "source":   "comment_reaction",
        "channel":  channel,
        "video_id": video_id,
        "views":    views,
        "weight":   3,
    }


def make_type_b(video_id: str, title: str, channel: str,
                transcript: str, comments: list, views: int) -> Optional[dict]:
    """
    TYPE B: Story → Predicted comment reactions
    Teaches the model to predict HOW audiences will react.
    """
    good_comments = [c for c in comments
                     if c.get("likes", 0) >= MIN_COMMENT_LIKES and c.get("text","").strip()]
    good_comments.sort(key=lambda x: x["likes"], reverse=True)
    top_5 = good_comments[:5]

    if len(top_5) < 3:
        return None

    comment_bullets = "\n".join(
        f'- "{c["text"].strip()}" ({c["likes"]} likes)'
        for c in top_5
    )

    user_msg = (
        f"I'm writing a short-form video script inspired by this story:\n\n"
        f"STORY/TRANSCRIPT:\n{transcript[:1200]}\n\n"
        f"How will the audience react in the comments? What will go viral in the comment section?"
    )

    assistant_msg = (
        f"Based on the story's emotional structure, here's what I'd predict — "
        f"and what actually happened on the real @{channel} video ({views:,} views):\n\n"
        f"PREDICTED (and actual) top comment patterns:\n{comment_bullets}\n\n"
        f"Why these comments? The story triggers "
        f"{'satisfaction' if any('karma' in c['text'].lower() or 'deserved' in c['text'].lower() for c in top_5) else 'strong emotional engagement'} "
        f"— the payoff moment is concrete and visual, which makes it highly quotable. "
        f"When audiences see a clear cause-and-effect payoff, they quote the moment in the comments "
        f"as a way of reliving it. That quoting behavior is what drives the algorithm."
    )

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ],
        "source":   "comment_prediction",
        "channel":  channel,
        "video_id": video_id,
        "views":    views,
        "weight":   3,
    }


def make_type_c(video_id: str, title: str, channel: str,
                comments: list, views: int) -> Optional[dict]:
    """
    TYPE C: High-engagement comment analysis (for videos with lots of likes)
    Teaches model to identify the MAGIC MOMENT from comment signals alone.
    """
    good = [c for c in comments if c.get("likes", 0) >= 10]
    good.sort(key=lambda x: x["likes"], reverse=True)
    if len(good) < 5:
        return None

    top_comment = good[0]
    comments_text = top_comments_text(good, n=15)

    user_msg = (
        f"Look at the top comments from this viral video ({views:,} views):\n\n"
        f"Title: \"{title}\" — @{channel}\n\n"
        f"{comments_text}\n\n"
        f"What was the magic moment that made this video go viral?"
    )

    top_likes = top_comment.get("likes", 0)
    top_text  = top_comment.get("text", "").strip()

    assistant_msg = (
        f"The magic moment is clear from the comments.\n\n"
        f"The most-liked comment ({top_likes:,} likes): \"{top_text}\"\n\n"
        f"This tells you everything. When a comment gets "
        f"{top_likes:,} likes, it means that comment articulates EXACTLY "
        f"what everyone in the audience was thinking but couldn't say. "
        f"That comment IS the payoff moment — it's the sentence the story was "
        f"building toward.\n\n"
        f"Rule: The most-liked comment on a viral video = the magic moment. "
        f"Write your scripts so the payoff produces that kind of comment."
    )

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_msg},
            {"role": "assistant", "content": assistant_msg},
        ],
        "source":   "comment_magic_moment",
        "channel":  channel,
        "video_id": video_id,
        "views":    views,
        "weight":   4,   # higher weight — this is high-signal
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n🔨 Build Comment Training Data")
    print("=" * 50)

    print("📥 Loading raw comments...")
    comments_db = load_comments()
    print(f"   {len(comments_db):,} videos with comments")

    print("📥 Loading transcripts...")
    transcripts_db = load_transcripts()
    print(f"   {len(transcripts_db):,} videos with transcripts")

    # Overlap
    both = set(comments_db) & set(transcripts_db)
    print(f"   {len(both):,} videos with BOTH — these generate training examples")
    print()

    examples = []
    skipped  = 0

    for vid in tqdm(both, desc="Building examples"):
        c_rec = comments_db[vid]
        t_rec = transcripts_db[vid]

        comments   = c_rec.get("comments", [])
        title      = c_rec.get("title", "")
        views      = c_rec.get("views", 0) or 0
        channel    = c_rec.get("channel", t_rec.get("channel", "unknown"))
        transcript = t_rec.get("transcript", "")

        if len(comments) < MIN_COMMENTS or not transcript.strip():
            skipped += 1
            continue

        # Type A: transcript → reaction analysis
        ex_a = make_type_a(vid, title, channel, transcript, comments, views)
        if ex_a:
            examples.append(ex_a)

        # Type B: story → predicted comments
        ex_b = make_type_b(vid, title, channel, transcript, comments, views)
        if ex_b:
            examples.append(ex_b)

        # Type C: comment magic moment (high-engagement videos only)
        if views >= 100_000:
            ex_c = make_type_c(vid, title, channel, comments, views)
            if ex_c:
                examples.append(ex_c)

    print(f"\n✅ Generated {len(examples):,} training examples")
    print(f"   Skipped: {skipped:,} (too few comments or no transcript)")

    # Write comment-specific output
    with open(OUT_COMMENTS, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    print(f"\n💾 Saved → {OUT_COMMENTS}")

    # Merge with existing training data → v8
    print(f"\n🔀 Merging into {OUT_MERGED}...")

    existing_v7 = Path("training_data_v7_clean.jsonl")
    written = 0
    with open(OUT_MERGED, "w") as out:
        # Existing data first
        if existing_v7.exists():
            for line in existing_v7.read_text().splitlines():
                if line.strip():
                    out.write(line + "\n")
                    written += 1
        # New comment examples
        for ex in examples:
            out.write(json.dumps(ex) + "\n")
            written += 1

    print(f"   Total examples in v8: {written:,}")
    print(f"   Breakdown:")
    print(f"     v7 clean:           {written - len(examples):,}")
    print(f"     Comment training:   {len(examples):,}")

    # Type breakdown
    from collections import Counter
    type_counts = Counter(ex["source"] for ex in examples)
    for src, cnt in type_counts.most_common():
        print(f"     └─ {src}: {cnt:,}")

    print(f"\n💾 Merged dataset → {OUT_MERGED}")
    print("\n▶️  Next step: python prep_finetune.py  (to split train/val)")


if __name__ == "__main__":
    main()
