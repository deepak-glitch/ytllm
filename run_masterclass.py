"""
Transcribe Creator Rant masterclass lessons -> JSONL -> zip.

Run:  python3 run_masterclass.py "C:/Users/deepa/OneDrive/Documents/creator-rant"

Prereqs:
  - ffmpeg on PATH
      Windows:  winget install ffmpeg     (or download from ffmpeg.org and add bin/ to PATH)
      macOS:    brew install ffmpeg
      Linux:    sudo apt install ffmpeg
  - First run auto-installs openai-whisper + torch (~1-2 GB download) and
    the Whisper 'small' model weights (~500 MB).

Output: masterclass-dataset.zip in cwd. Upload to Claude.
"""
import json, re, subprocess, sys, zipfile
from pathlib import Path

if len(sys.argv) != 2:
    sys.exit('Usage: python3 run_masterclass.py "<folder_with_mp4s>"')

video_dir = Path(sys.argv[1]).expanduser()
if not video_dir.is_dir():
    sys.exit(f"Not a directory: {video_dir}")

videos = sorted(video_dir.glob("*.mp4"))
if not videos:
    sys.exit(f"No .mp4 files in {video_dir}")

print(f"Found {len(videos)} lessons. Installing openai-whisper if needed...")
subprocess.run([sys.executable, "-m", "pip", "install", "openai-whisper", "-q"], check=True)
import whisper

MODEL = "small"  # base / small / medium — 'small' is the speed/quality sweet spot
print(f"Loading Whisper '{MODEL}' (first run downloads weights)...")
model = whisper.load_model(MODEL)

SYSTEM = ("You are a viral short-form video creator coach specializing in pixel art animated "
          "Shorts. Expert in hooks, story structure, retention, and visual storytelling.")

examples = []
for i, vf in enumerate(videos, 1):
    print(f"[{i}/{len(videos)}] transcribing {vf.name} ...")
    result = model.transcribe(str(vf), fp16=False)
    text = re.sub(r"\s+", " ", result["text"]).strip()
    if len(text) < 100:
        print(f"  skipped (too short: {len(text)} chars)")
        continue
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",
             "content": f"Teach me about viral short-form video storytelling. Lesson: {vf.stem}"},
            {"role": "assistant", "content": text},
        ],
        "source": "masterclass_creator_rant_local",
        "lesson": vf.stem,
        "weight": 5,
    })
    print(f"  ok ({len(text)} chars)")

out_jsonl = Path("masterclass_examples.jsonl")
with open(out_jsonl, "w", encoding="utf-8") as f:
    for ex in examples:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")

zip_path = "masterclass-dataset.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.write(out_jsonl)

print(f"\n{'='*55}\nDone. {len(examples)} lessons -> {zip_path}\nUpload to Claude.")
