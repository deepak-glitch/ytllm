"""
Convert training_data_final.jsonl (role/content format) to Axolotl sharegpt format.

Input:  {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
Output: {"conversations": [{"from": "system", ...}, {"from": "human", ...}, {"from": "gpt", ...}]}

Usage:
  python training/convert_to_sharegpt.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

ROLE_MAP = {"system": "system", "user": "human", "assistant": "gpt"}

src = ROOT / "training" / "training_data_final.jsonl"
dst = ROOT / "training" / "training_data_sharegpt.jsonl"


def convert(example: dict) -> dict | None:
    messages = example.get("messages", [])
    if not messages:
        return None
    conversations = []
    for m in messages:
        role = ROLE_MAP.get(m.get("role", ""))
        if not role:
            return None
        conversations.append({"from": role, "value": m["content"]})
    return {"conversations": conversations}


ok = 0
skipped = 0
with open(src) as fin, open(dst, "w") as fout:
    for line in fin:
        line = line.strip()
        if not line:
            continue
        try:
            out = convert(json.loads(line))
            if out:
                fout.write(json.dumps(out) + "\n")
                ok += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

print(f"Converted: {ok}  Skipped: {skipped}")
print(f"Output: {dst}")
