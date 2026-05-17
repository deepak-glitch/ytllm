"""
Prep training_data_v7 for Qwen3.5-35B-A3B fine-tuning on DeepInfra.

- Validates messages format (system/user/assistant turns)
- Filters out malformed / too-short / too-long examples
- Splits into train + validation (95/5)
- Reports weight distribution (DeepInfra has no per-example weighting;
  upsample manually before this script if you want to honor weights)
- Estimates token count + cost
- Writes finetune_train.jsonl and finetune_val.jsonl

DeepInfra fine-tune pricing for Qwen3.5-35B-A3B (LoRA, as of 2026):
  ~$0.0005 per 1K training tokens
  Reference total: ~$15-25 for a 10k-example run at 3 epochs.
"""

import json
import random
from pathlib import Path
from collections import Counter

SRC      = Path("training_data_v7.jsonl")
TRAIN    = Path("finetune_train.jsonl")
VAL      = Path("finetune_val.jsonl")

# Filtering — sized for Qwen3.5 (256K context, but 32K cap keeps training memory sane)
MIN_ASSISTANT_CHARS = 150        # ~38 tokens — filters 1-line junk, keeps short craft examples
MAX_TOTAL_CHARS     = 32000      # ~8K tokens — comfortable LoRA training budget
VAL_FRACTION        = 0.05
SEED                = 42

# Cost estimation — DeepInfra Qwen3.5-35B-A3B LoRA
COST_PER_1K_TOKENS_LORA = 0.0005


def approx_tokens(text):
    """Rough estimate: ~4 chars per token for English."""
    return len(text) / 4


def validate_and_filter(records):
    kept = []
    stats = Counter()
    weights_kept = Counter()

    for r in records:
        msgs = r.get("messages")
        if not msgs or not isinstance(msgs, list):
            stats["no_messages"] += 1
            continue

        roles = [m.get("role") for m in msgs]
        if "user" not in roles or "assistant" not in roles:
            stats["missing_role"] += 1
            continue

        if not all(isinstance(m.get("content"), str) and m["content"].strip() for m in msgs):
            stats["empty_content"] += 1
            continue

        assistant = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
        if len(assistant) < MIN_ASSISTANT_CHARS:
            stats["too_short"] += 1
            continue

        total_chars = sum(len(m["content"]) for m in msgs)
        if total_chars > MAX_TOTAL_CHARS:
            stats["too_long"] += 1
            continue

        weights_kept[r.get("weight", "unweighted")] += 1
        # Keep messages only — DeepInfra ignores metadata
        kept.append({"messages": msgs})

    return kept, stats, weights_kept


def main():
    records = []
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    print(f"Loaded {len(records)} raw records from {SRC}")

    kept, stats, weights_kept = validate_and_filter(records)
    print(f"\nFiltering results:")
    for reason, count in stats.most_common():
        print(f"  Dropped {count:5d}  ({reason})")
    print(f"  Kept    {len(kept):5d}")

    print(f"\nWeight distribution of kept examples (DeepInfra ignores these):")
    for w in sorted(weights_kept, key=lambda x: (isinstance(x, str), x)):
        print(f"  weight={w!s:>11}  {weights_kept[w]:5d}")
    print(f"  Tip: upsample high-weight examples in v7 before prep if you want them to dominate.")

    random.seed(SEED)
    random.shuffle(kept)
    val_size = max(1, int(len(kept) * VAL_FRACTION))
    val   = kept[:val_size]
    train = kept[val_size:]

    with TRAIN.open("w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with VAL.open("w", encoding="utf-8") as f:
        for r in val:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total_chars = sum(sum(len(m["content"]) for m in r["messages"]) for r in train)
    total_tokens = total_chars / 4
    lora_cost = (total_tokens / 1000) * COST_PER_1K_TOKENS_LORA

    print(f"\nSplit:")
    print(f"  Train: {len(train):5d}  examples  ({TRAIN})")
    print(f"  Val:   {len(val):5d}  examples  ({VAL})")
    print()
    print(f"Training set:")
    print(f"  Total chars:  {total_chars:>12,}")
    print(f"  Approx tokens:{total_tokens:>12,.0f}")
    print(f"  File size:    {TRAIN.stat().st_size/1024/1024:>10.1f} MB")
    print()
    print(f"Estimated DeepInfra cost (Qwen3.5-35B-A3B LoRA, 3 epochs):")
    print(f"  LoRA fine-tune: ${lora_cost*3:.2f}")
    print()
    print("Next step: upload to DeepInfra and start the fine-tune.")


if __name__ == "__main__":
    main()
