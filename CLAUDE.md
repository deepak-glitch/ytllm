# Pixel Art Story Video Generator — Project Brief for Claude Code

## What we're building
An end-to-end AI pipeline that:
1. Takes a story prompt from the user
2. Generates a structured scene manifest (Story Director LLM)
3. Creates 3D pixel art characters and environments (Godot 4 + Blender)
4. Renders the scenes headless and stitches into a final MP4 video

Reference style: https://www.youtube.com/@pixelbeefshorts (3D pixel art shorts)

---

## Full system architecture

```
User story prompt
      ↓
Story Director LLM (fine-tuned Mistral-7B)
      → outputs JSON scene manifest
      ↓
Character LLM (fine-tuned CodeLlama)
      → outputs Blender Python scripts → .glb files
      ↓
Godot 4 Headless Renderer
      → applies pixel art shader (GodotPixelRenderer by bukkbeek)
      → exports PNG frame sequences per scene
      ↓
Python Orchestrator (FFmpeg + ElevenLabs TTS)
      → stitches frames + dialogue + music → final MP4
```

---

## Story Director LLM — training data (DONE)

### What exists
- `training_data_v3.jsonl` — 361 examples, ready for fine-tuning
- OpenAI-compatible instruct format (works with Together AI, Axolotl, LLaMA-Factory)

### Sources in the dataset
| Source | Count | Weight |
|--------|-------|--------|
| Discord Q&A (creator answered) | 68 | 3-4 |
| Discord monologues (creator advice) | 121 | 2-3 |
| Jenny Hoyos interview (Creator Science) | 17 | 4 |
| John Scott masterclass lesson | 7 | 4 |
| Pranish peer DM advice | 3 | 3 |
| Web research (VidCon 2025, algo data) | 12 | 4 |
| Synthetic pixel art scripts (40 scenarios) | 40 | 3 |
| Synthetic hooks (8 per scenario) | 42 | 3 |
| Synthetic beat structures | 40 | 3 |
| Synthetic analytics scenarios | 8 | 3 |
| Synthetic platform advice | 3 | 3 |

### Viral story framework (extracted from creator masterclass)
Structure: Hook → Foreshadow → Obstacle → Amplifier → Twist → Payoff

Key rules:
- Hook must land in 1.5-3 seconds
- Foreshadow is always 2 lines, under 3 seconds
- But/therefore storytelling (not and/then)
- 90%+ retention = viral minimum; 100%+ = rewatches = algorithm's strongest signal
- Sweet spots: 30s or 50s (not 20s or 40s — they underperform)
- 5th grade reading level or below for all narration
- End IMMEDIATELY after payoff — never let it breathe

### JSON scene manifest format (Story Director output)
```json
{
  "title": "The Cursed Sword",
  "target_duration_sec": 30,
  "emotion": "suspense",
  "scenes": [
    {
      "scene_id": 1,
      "beat_type": "hook",
      "narration": "There he was.",
      "dialogue": null,
      "characters_visible": ["knight"],
      "camera": "wide",
      "action": "Knight reaches for sword, hand recoils",
      "emotion_intensity": 0.7
    }
  ]
}
```

---

## What needs to be built next

### Priority 1 — Grow the training dataset
Run this on your machine, then upload the zip back:
```bash
pip install yt-dlp
python3 full_pipeline.py
```
This scrapes 300+ curated YouTube channels for transcripts.

Also: Download Creator Rant masterclass lesson videos from creatorrant.com,
set MASTERCLASS_VIDEO_DIR in full_pipeline.py, re-run.
Those lessons get weight:5 (highest priority).

Target: 3,000+ examples before fine-tuning.

### Priority 2 — Fine-tune the Story Director LLM
```bash
pip install together
# Base model: mistralai/Mistral-7B-Instruct-v0.2
# Dataset: training_data_v3.jsonl
# Platform: Together AI or RunPod A100
# Cost: ~$5-20 for full fine-tune
```

### Priority 3 — Godot render pipeline (start this NOW in parallel)

#### 3a. Install GodotPixelRenderer shader
Repo: https://github.com/bukkbeek/GodotPixelRenderer
Apply to a Godot 4 scene. Get one scene rendering with pixel art style.

#### 3b. Write headless export script
```bash
godot --headless --script export_scene.gd -- scene.tscn output/
```
Script should: load .tscn → play animation → export PNG frames → exit.

#### 3c. Build one scene end-to-end manually
1. Make one character in Blender (low-poly, rigged)
2. Export as .glb
3. Import to Godot 4
4. Apply GodotPixelRenderer shader
5. Export headless → PNG frames
6. Stitch with FFmpeg:
```bash
ffmpeg -r 24 -i frame_%04d.png -c:v libx264 -pix_fmt yuv420p output.mp4
```

### Priority 4 — Character generation LLM
- Base model: CodeLlama-7B or Mistral-7B
- Input: character description ("a stoic samurai with broken armor")
- Output: Blender Python script that generates low-poly rigged mesh
- Training data: build 50-100 characters manually first → use as examples
- Fine-tune on Together AI after Godot pipeline is working

### Priority 5 — Python orchestrator
Reads JSON scene manifest → calls Character LLM → runs Godot headless per scene
→ calls ElevenLabs TTS for dialogue → stitches with FFmpeg.

---

## Key files to know about

### Scripts (run on your machine)
- `full_pipeline.py` — scrapes 300+ YouTube channels + processes masterclass lessons
- `scrape_channels.py` — channel list only (300+ channels, 15 categories)
- `download_datasets.py` — pulls HuggingFace + Kaggle datasets

### Training data files
- `training_data_v3.jsonl` — current best dataset (361 examples, use this for fine-tuning)
- `synthetic_local.jsonl` — 133 synthetic examples (pixel art scripts, hooks, beat structures)
- `web_research_examples.jsonl` — 12 examples from VidCon 2025, algo research, Kaggle links
- `creator_wisdom.txt` — raw creator advice extracted from Discord (readable reference)
- `qa_readable.md` — all 68 Q&A pairs in human-readable format

### Kaggle datasets to download
- kaggle.com/datasets/danishbaloch010/youtube-shorts-data-for-virality-analysis
- kaggle.com/datasets/kanchana1990/viral-shorts-youtubes-most-viewed
- kaggle.com/datasets/rsrishav/youtube-trending-video-dataset (updated daily)
- kaggle.com/datasets/tarekmasryo/youtube-shorts-and-tiktok-trends-2025
- kaggle.com/datasets/amansingh0000000/youtube-2025-dataset

---

## Tech stack

| Component | Technology |
|-----------|-----------|
| Story Director LLM | Mistral-7B-Instruct fine-tuned |
| Character LLM | CodeLlama-7B fine-tuned |
| 3D rendering | Godot 4 (headless) |
| Pixel art shader | GodotPixelRenderer (bukkbeek) |
| Character creation | Blender + Python scripting |
| Video assembly | FFmpeg |
| TTS / dialogue | ElevenLabs |
| Fine-tuning platform | Together AI or RunPod A100 |
| Orchestration | Python |

---

## Immediate next actions (in order)

1. [ ] Run `full_pipeline.py` on local machine → upload zip back to Claude chat
2. [ ] Download Creator Rant masterclass lessons → point MASTERCLASS_VIDEO_DIR → re-run pipeline
3. [ ] Upload more course lesson transcripts to Claude chat for processing
4. [ ] Install Godot 4 + GodotPixelRenderer → get one pixel art scene rendering
5. [ ] Make one character in Blender → export .glb → import Godot → render headless
6. [ ] Fine-tune Story Director on Together AI once dataset hits 3000+ examples
7. [ ] Build Python orchestrator that reads JSON manifest → drives render pipeline

---

## Context on the creator / niche

- Style reference: PixelBeef (@pixelbeefshorts) — 3D pixel art rendered in Godot
- Shader reference: t3ssel8r — pixel snapping shader, nearest-neighbour, dithering
- Story framework: John Scott (Creator Rant) viral story formula
- Analytics framework: Jenny Hoyos data-driven approach (34s sweet spot, 90%+ retention)
- Rendering tool: GodotPixelRenderer by bukkbeek (GitHub)
- Character pipeline: Blender Python scripting → low-poly rigged → .glb → Godot

---

## Notes for Claude Code

- All training data is in OpenAI instruct JSONL format — compatible with Together AI, Axolotl, LLaMA-Factory, OpenAI fine-tuning API
- The scraper (full_pipeline.py) uses yt-dlp — no API keys needed
- Godot 4 headless mode works on Linux/Mac/Windows: `godot --headless`
- When building the render pipeline, test with a simple cube scene first before characters
- The JSON scene manifest is the interface between LLM and renderer — keep it stable
- ElevenLabs has a free tier for TTS prototyping
