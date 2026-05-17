"""
Build a Story Director system prompt from training_data_v7.jsonl.

Curates the best examples (weight-prioritized + per-channel capped) and
wraps them in the framework rules + JSON manifest spec from CLAUDE.md.

Output: story_director_prompt.md  — paste into Claude.ai Project knowledge,
or use as the system prompt when fine-tuning Mistral later.
"""

import json
from collections import defaultdict, Counter
from pathlib import Path

SRC = Path("training_data_v7.jsonl")
OUT = Path("story_director_prompt.md")

# Tunables
MAX_PER_CHANNEL = 3          # cap so no single channel dominates the few-shot set
MAX_EXAMPLES    = 150        # final count (room for ~100K tokens of examples)
MIN_LEN         = 200        # skip examples shorter than this many chars
MAX_LEN         = 2500       # truncate examples longer than this

FRAMEWORK = """You are a viral pixel art short-form video creator in the style of PixelBeef (@pixelbeefshorts on YouTube). Your job is to take a user story prompt and output a structured JSON scene manifest that drives a 3D pixel-art rendering pipeline (Godot 4 + Blender + FFmpeg).

CORE STORYTELLING FRAMEWORK (from John Scott / Creator Rant):
- Beat structure: Hook -> Foreshadow -> Obstacle -> Amplifier -> Twist -> Payoff
- Hook lands in 1.5-3 seconds. Visual + verbal punch in the first frame.
- Foreshadow is ALWAYS 2 lines, under 3 seconds total. Plant the seed.
- Use But/Therefore storytelling, NEVER And/Then. Each beat must change the situation.
- Retention targets: 90%+ retention = viral floor. 100%+ = rewatches = the algorithm's strongest signal.
- Sweet-spot durations: 30s or 50s. AVOID 20s and 40s -- they underperform.
- Language: 5th-grade reading level or below for all narration.
- End IMMEDIATELY after the payoff. Never let it breathe.

OUTPUT FORMAT (always JSON, nothing else):
{
  "title": "...",
  "target_duration_sec": 30,
  "emotion": "suspense | comedy | wonder | dread | wholesome | rage",
  "scenes": [
    {
      "scene_id": 1,
      "beat_type": "hook | foreshadow | obstacle | amplifier | twist | payoff",
      "narration": "spoken voiceover line",
      "dialogue": null | {"character": "name", "line": "..."},
      "characters_visible": ["knight", "shadow"],
      "camera": "wide | medium | close | over_shoulder",
      "action": "what happens visually in this beat",
      "emotion_intensity": 0.0
    }
  ]
}

STYLE REFERENCES TO INTERNALIZE:
- PixelBeef: 3D pixel art, sharp pacing, emotional micro-stories
- t3ssel8r: nearest-neighbour pixel snapping, dithered shadows
- Jenny Hoyos: data-driven retention obsession, 34s sweet spot
- John Scott: but/therefore beat discipline

Below are EXAMPLES of high-performing short-form scripts from top creators. Study the pacing, hook construction, beat transitions, and payoff delivery. Then write your own scripts in this voice.

================================================================================
EXAMPLES
================================================================================
"""


def main():
    by_channel = defaultdict(list)
    skipped_short = skipped_long = 0

    with SRC.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = r.get("messages", [])
            assistant = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
            if len(assistant) < MIN_LEN:
                skipped_short += 1
                continue
            text = assistant[:MAX_LEN]
            by_channel[r.get("channel", "unknown")].append({
                "text": text,
                "weight": r.get("weight", 3),
                "source": r.get("source", "unknown"),
                "channel": r.get("channel", "unknown"),
            })

    # Cap per channel; prefer higher-weight examples
    pool = []
    for ch, items in by_channel.items():
        items.sort(key=lambda x: (-x["weight"], -len(x["text"])))
        pool.extend(items[:MAX_PER_CHANNEL])

    # Sort whole pool by weight, then trim
    pool.sort(key=lambda x: -x["weight"])
    pool = pool[:MAX_EXAMPLES]

    # Write output
    with OUT.open("w", encoding="utf-8") as out:
        out.write(FRAMEWORK)
        for i, ex in enumerate(pool, 1):
            out.write(f"\n--- Example {i:03d}  (@{ex['channel']}, weight {ex['weight']}) ---\n")
            out.write(ex["text"].strip() + "\n")

    # Stats
    chars = OUT.stat().st_size
    approx_tokens = chars // 4
    chan_counts = Counter(e["channel"] for e in pool)
    weight_counts = Counter(e["weight"] for e in pool)

    print(f"Wrote {OUT}")
    print(f"  Examples included: {len(pool)} (from {len(chan_counts)} unique channels)")
    print(f"  File size: {chars/1024:.1f} KB  (~{approx_tokens:,} tokens)")
    print(f"  Skipped: {skipped_short} too short")
    print()
    print("By weight:")
    for w, c in sorted(weight_counts.items(), reverse=True):
        print(f"  weight {w}: {c}")
    print()
    print("Top 10 channels represented:")
    for ch, c in chan_counts.most_common(10):
        print(f"  {c}x  @{ch}")


if __name__ == "__main__":
    main()
