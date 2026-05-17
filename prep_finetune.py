"""
Prep v7 for Mistral-7B fine-tuning on Together AI.

- Validates messages format (system/user/assistant turns)
- Filters out malformed / too-short / too-long examples
- Splits into train + validation (95/5)
- Estimates token count + cost
- Writes finetune_train.jsonl and finetune_val.jsonl

Together AI fine-tune pricing (Mistral-7B as of 2025):
  ~$0.0008 per 1K training tokens (LoRA)
  ~$0.002 per 1K training tokens (full fine-tune)
"""

import json
import random
from pathlib import Path
from collections import Counter

SRC      = Path("training_data_v7.jsonl")
TRAIN    = Path("finetune_train.jsonl")
VAL      = Path("finetune_val.jsonl")

# Filtering
MIN_ASSISTANT_CHARS = 200
MAX_TOTAL_CHARS     = 12000      # ~3K tokens, safe for Mistral 8K context
VAL_FRACTION        = 0.05
SEED                = 42

# Cost estimation
COST_PER_1K_TOKENS_LORA = 0.0008
COST_PER_1K_TOKENS_FULL = 0.002


def approx_tokens(text):
    """Rough estimate: ~4 chars per token for English."""
    return len(text) / 4


def validate_and_filter(records):
    kept = []
    stats = Counter()

    for r in records:
        msgs = r.get("messages")
        if not msgs or not isinstance(msgs, list):
            stats["no_messages"] += 1
            continue

        roles = [m.get("role") for m in msgs]
        # Need at least one user + one assistant turn
        if "user" not in roles or "assistant" not in roles:
            stats["missing_role"] += 1
            continue

        # Validate every message has content
        if not all(isinstance(m.get("content"), str) and m["content"].strip() for m in msgs):
            stats["empty_content"] += 1
            continue

        # Filter by assistant length
        assistant = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
        if len(assistant) < MIN_ASSISTANT_CHARS:
            stats["too_short"] += 1
            continue

        total_chars = sum(len(m["content"]) for m in msgs)
        if total_chars > MAX_TOTAL_CHARS:
            stats["too_long"] += 1
            continue

        # Only keep the messages field — drop metadata that Together doesn't need
        kept.append({"messages": msgs})

    return kept, stats


def main():
    records = []
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    print(f"Loaded {len(records)} raw records from {SRC}")

    kept, stats = validate_and_filter(records)
    print(f"\nFiltering results:")
    for reason, count in stats.most_common():
        print(f"  Dropped {count:5d}  ({reason})")
    print(f"  Kept    {len(kept):5d}")

    # Shuffle deterministically + split
    random.seed(SEED)
    random.shuffle(kept)
    val_size = max(1, int(len(kept) * VAL_FRACTION))
    val   = kept[:val_size]
    train = kept[val_size:]

    # Write
    with TRAIN.open("w", encoding="utf-8") as f:
        for r in train:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with VAL.open("w", encoding="utf-8") as f:
        for r in val:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Token + cost estimate
    total_chars = sum(sum(len(m["content"]) for m in r["messages"]) for r in train)
    total_tokens = total_chars / 4
    lora_cost = (total_tokens / 1000) * COST_PER_1K_TOKENS_LORA
    full_cost = (total_tokens / 1000) * COST_PER_1K_TOKENS_FULL

    print(f"\nSplit:")
    print(f"  Train: {len(train):5d}  examples  ({TRAIN})")
    print(f"  Val:   {len(val):5d}  examples  ({VAL})")
    print()
    print(f"Training set:")
    print(f"  Total chars:  {total_chars:>12,}")
    print(f"  Approx tokens:{total_tokens:>12,.0f}")
    print(f"  File size:    {TRAIN.stat().st_size/1024/1024:>10.1f} MB")
    print()
    print(f"Estimated Together AI cost (Mistral-7B, 3 epochs):")
    print(f"  LoRA fine-tune: ${lora_cost*3:.2f}")
    print(f"  Full fine-tune: ${full_cost*3:.2f}")
    print()
    print("Next step: upload to Together AI and start the fine-tune.")
    print("  pip install together")


if __name__ == "__main__":
    main()
