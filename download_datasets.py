"""
Run on YOUR machine: python3 download_datasets.py
Then upload story-director-datasets.zip here
"""
import subprocess, sys, os, json

os.makedirs("datasets/hf", exist_ok=True)
os.makedirs("datasets/transcripts", exist_ok=True)

# Install deps
subprocess.run([sys.executable, "-m", "pip", "install", "datasets", "yt-dlp", "-q"])

from datasets import load_dataset

DATASETS = [
    ("benxh/tiktok-hooks-finetune",                         "train", "tiktok_hooks"),
    ("Gopher-Lab/TikTok_Hottest_Video_Transcript_Example",  "train", "tiktok_hottest_transcripts"),
    ("Gryphe/ChatGPT-4o-Writing-Prompts",                   "train", "chatgpt_writing_prompts"),
    ("euclaise/writingprompts",                             "train", "reddit_writing_prompts"),
    ("kanchana1990/viral-shorts-youtubes-most-viewed",       "train", "viral_yt_shorts"),
    ("danishbaloch010/youtube-shorts-data-for-virality-analysis", "train", "yt_shorts_virality"),
    ("RafaM97/marketing_social_media",                       "train", "social_media_marketing"),
]

for name, split, outname in DATASETS:
    print(f"Downloading {name} ...")
    try:
        ds = load_dataset(name, split=split)
        path = f"datasets/hf/{outname}.jsonl"
        ds.to_json(path)
        print(f"  OK — {len(ds)} rows → {path}")
    except Exception as e:
        print(f"  FAILED: {e}")

CHANNELS = [
    ("JennyHoyos",  "https://www.youtube.com/@JennyHoyos/shorts"),
    ("pixelbeef",   "https://www.youtube.com/@pixelbeef/shorts"),
    ("ZackDFilms",  "https://www.youtube.com/@ZackDFilms/shorts"),
    ("RyanTrahan",  "https://www.youtube.com/@RyanTrahan/shorts"),
    ("MrBeast",     "https://www.youtube.com/@MrBeast/shorts"),
]

for name, url in CHANNELS:
    out_dir = f"datasets/transcripts/{name}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"Downloading transcripts: {name} ...")
    cmd = [
        "yt-dlp",
        "--write-auto-sub", "--sub-lang", "en", "--sub-format", "json3",
        "--skip-download", "--match-filter", "duration < 65",
        "--max-downloads", "150",
        "-o", f"{out_dir}/%(id)s.%(ext)s",
        url
    ]
    subprocess.run(cmd, capture_output=True)
    count = len([f for f in os.listdir(out_dir) if f.endswith(".json3")])
    print(f"  Got {count} transcript files")

import shutil
shutil.make_archive("story-director-datasets", "zip", ".", "datasets")
print("\n=== DONE ===")
print("Upload story-director-datasets.zip to Claude")
