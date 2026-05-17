"""
Merge the cleaned v7 dataset with synthetic JSON manifest examples.

Usage:
  python training/merge_final.py

Output:
  training/training_data_final.jsonl  — ready for fine-tuning
"""

import json
import random
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).parent.parent

SOURCES = [
    ROOT / "training_data_v7_clean.jsonl",              # 9720 transcript/script examples
    ROOT / "synthetic_data" / "manifests_v1.jsonl",     # 980 template JSON manifests
    ROOT / "synthetic_data" / "manifests_claude.jsonl", # 114 Haiku-generated manifests
    ROOT / "synthetic_data" / "manifests_10k.jsonl",    # 9746 template JSON manifests
]

OUT = ROOT / "training" / "training_data_final.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    examples = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


def main():
    all_examples = []
    for src in SOURCES:
        if not src.exists():
            print(f"  SKIP (not found): {src.name}")
            continue
        examples = load_jsonl(src)
        print(f"  Loaded {len(examples):>6} examples from {src.name}")
        all_examples.extend(examples)

    print(f"\nTotal before dedup: {len(all_examples)}")

    # Deduplicate on assistant content
    seen = set()
    deduped = []
    for e in all_examples:
        key = tuple(
            m["content"] for m in e.get("messages", []) if m["role"] == "assistant"
        )
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    print(f"Total after dedup:  {len(deduped)}")

    random.seed(42)
    random.shuffle(deduped)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w") as f:
        for e in deduped:
            f.write(json.dumps(e) + "\n")

    sources = Counter(e.get("source", "unknown") for e in deduped)
    weights = Counter(e.get("weight") for e in deduped)

    print(f"\nWritten to: {OUT}")
    print(f"Weight distribution: {dict(weights)}")
    print(f"\nTop sources:")
    for src, cnt in sources.most_common(10):
        print(f"  {src:<45} {cnt}")


if __name__ == "__main__":
    main()
