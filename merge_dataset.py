"""
Merge dataset shards into training_data_v4.jsonl.

Inputs:
  - training_data_v3.jsonl (existing)
  - scraped_transcripts.jsonl (from full_pipeline.py)
  - masterclass_examples.jsonl (from run_masterclass.py)

Dedup: by normalized assistant content. Highest weight wins.
Lesson name cleanup: strips the 'file-uploadssitesNNNvideoUUID_' Squarespace
prefix and trailing 'mp4' from masterclass lesson stems.

Run: python3 merge_dataset.py <out.jsonl> <input1.jsonl> [input2.jsonl ...]
"""
import gzip, json, re, sys
from collections import Counter
from pathlib import Path

LESSON_PREFIX_RE = re.compile(r"^file-uploadssites\d+video[a-f0-9-]+_")
LESSON_MP4_RE = re.compile(r"_?mp4$")


def clean_lesson_name(name: str) -> str:
    name = LESSON_PREFIX_RE.sub("", name)
    name = LESSON_MP4_RE.sub("", name)
    return name


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def assistant_content(ex):
    for m in ex["messages"]:
        if m["role"] == "assistant":
            return m["content"]
    return ""


def maybe_clean(ex):
    if ex.get("source") != "masterclass_creator_rant_local":
        return ex
    if "lesson" in ex:
        ex["lesson"] = clean_lesson_name(ex["lesson"])
    for m in ex["messages"]:
        if m["role"] == "user":
            m["content"] = re.sub(
                r"Lesson: (file-uploadssites\d+video[a-f0-9-]+_[^\s]+)",
                lambda mo: "Lesson: " + clean_lesson_name(mo.group(1)),
                m["content"],
            )
    return ex


def main():
    if len(sys.argv) < 3:
        sys.exit("Usage: python3 merge_dataset.py <out.jsonl> <in1.jsonl> [in2.jsonl ...]")

    out_path = Path(sys.argv[1])
    in_paths = [Path(p) for p in sys.argv[2:]]
    for p in in_paths:
        if not p.is_file():
            sys.exit(f"Missing input: {p}")

    by_key = {}
    raw_per_input = Counter()
    dropped_dupes = 0
    for p in in_paths:
        opener = gzip.open if p.suffix == ".gz" else open
        for line in opener(p, "rt", encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            ex = json.loads(line)
            ex = maybe_clean(ex)
            raw_per_input[p.name] += 1
            key = normalize(assistant_content(ex))
            if not key:
                continue
            if key in by_key:
                if ex.get("weight", 0) > by_key[key].get("weight", 0):
                    by_key[key] = ex
                dropped_dupes += 1
            else:
                by_key[key] = ex

    merged = list(by_key.values())
    with open(out_path, "w", encoding="utf-8") as f:
        for ex in merged:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    sources = Counter(ex.get("source", "?") for ex in merged)
    weights = Counter(ex.get("weight", "?") for ex in merged)

    print(f"Inputs:")
    for name, n in raw_per_input.items():
        print(f"  {n:5d}  {name}")
    print(f"\nMerged: {len(merged)} unique examples (dropped {dropped_dupes} duplicates)")
    print(f"Output: {out_path}")
    print(f"\nBy weight:")
    for k, n in sorted(weights.items()):
        print(f"  {n:5d}  weight={k}")
    print(f"\nBy source:")
    for s, n in sources.most_common():
        print(f"  {n:5d}  {s}")


if __name__ == "__main__":
    main()
