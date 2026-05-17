"""
Split training_data_v7.jsonl into multiple .md files for Claude.ai Project upload.

Stories are sorted by weight DESCENDING (highest first), then by channel name.
Chunked so each file stays under MAX_FILE_MB.

Output: stories/01_weight5.md, stories/02_weight4_partNN.md, ...
"""

import json
from pathlib import Path
from collections import Counter

SRC = Path("training_data_v7.jsonl")
OUT_DIR = Path("stories")
OUT_DIR.mkdir(exist_ok=True)

MAX_FILE_MB   = 4          # split files larger than this
MIN_LEN       = 200        # skip stories shorter than this many chars
MAX_STORY_LEN = 5000       # truncate any single story longer than this


def load_all():
    stories = []
    skipped = 0
    with SRC.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = r.get("messages", [])
            assistant = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
            if len(assistant) < MIN_LEN:
                skipped += 1
                continue
            stories.append({
                "text":    assistant[:MAX_STORY_LEN],
                "weight":  r.get("weight", 3),
                "channel": r.get("channel", "unknown"),
                "source":  r.get("source", "unknown"),
                "vid":     r.get("video_id", ""),
            })
    return stories, skipped


def fmt_story(idx, s):
    return (
        f"## Story {idx:05d}\n"
        f"- **Weight:** {s['weight']}\n"
        f"- **Channel:** @{s['channel']}\n"
        f"- **Source:** {s['source']}\n"
        f"- **Video ID:** {s['vid']}\n\n"
        f"{s['text'].strip()}\n\n"
        f"---\n\n"
    )


def write_chunked(weight, stories, file_num_start):
    """Write all stories of a given weight, splitting into multiple files if too large."""
    max_bytes = MAX_FILE_MB * 1024 * 1024
    buf = []
    buf_size = 0
    part = 1
    written_files = []
    file_num = file_num_start

    def flush():
        nonlocal buf, buf_size, part, file_num
        if not buf:
            return
        # Single-part case: no _partNN suffix
        suffix = "" if part == 1 and (buf_size_remaining_check()) else f"_part{part:02d}"
        filename = OUT_DIR / f"{file_num:02d}_weight{weight}{suffix}.md"
        header = f"# Weight {weight} Stories"
        if suffix:
            header += f" (part {part})"
        header += f"\n\nTotal stories in this file: {len(buf)}\n\n---\n\n"
        filename.write_text(header + "".join(buf), encoding="utf-8")
        written_files.append((filename, len(buf), buf_size))
        buf = []
        buf_size = 0
        part += 1

    def buf_size_remaining_check():
        # Helper used by flush() to decide if suffix is needed.
        # Returns True if all stories of this weight fit in one part.
        return all_in_one[0]

    # First pass: would everything fit in one file?
    total_bytes = sum(len(fmt_story(i, s).encode("utf-8")) for i, s in enumerate(stories, 1))
    all_in_one = [total_bytes <= max_bytes]

    for i, s in enumerate(stories, 1):
        entry = fmt_story(i, s)
        entry_bytes = len(entry.encode("utf-8"))
        if buf_size + entry_bytes > max_bytes and buf:
            flush()
            file_num += 1
        buf.append(entry)
        buf_size += entry_bytes

    flush()
    return written_files, file_num


def main():
    stories, skipped = load_all()
    print(f"Loaded {len(stories)} stories (skipped {skipped} for being too short)")

    # Sort by weight DESCENDING, then channel ASC for stable grouping
    stories.sort(key=lambda s: (-s["weight"], s["channel"]))

    # Group by weight (descending order preserved)
    weights_seen = []
    by_weight = {}
    for s in stories:
        w = s["weight"]
        if w not in by_weight:
            by_weight[w] = []
            weights_seen.append(w)
        by_weight[w].append(s)

    # Write each weight tier into one or more files
    file_num = 1
    all_written = []
    for w in weights_seen:
        written, file_num = write_chunked(w, by_weight[w], file_num)
        all_written.extend(written)
        file_num += 1  # next weight tier starts at next index

    print(f"\nWrote {len(all_written)} files to {OUT_DIR}/")
    print()
    for path, n_stories, n_bytes in all_written:
        print(f"  {path.name:40s}  {n_stories:5d} stories  {n_bytes/1024/1024:.2f} MB")

    total_mb = sum(b for _, _, b in all_written) / 1024 / 1024
    print(f"\nTotal: {sum(n for _, n, _ in all_written)} stories across {len(all_written)} files ({total_mb:.1f} MB)")
    print()
    print("Upload these to Claude.ai Project knowledge in order.")
    print("Highest-weight stories appear first (weight 5 -> 4 -> 3 -> 2).")


if __name__ == "__main__":
    main()
