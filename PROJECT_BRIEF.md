# Project Brief — Pixel Art Story Video Generator

## What this project is

An end-to-end AI pipeline that turns a text story prompt into a finished pixel-art animated short video (YouTube Shorts / TikTok / Instagram Reels format). The visual style reference is PixelBeef (@pixelbeefshorts) — 3D pixel-art rendered in Godot using a shader-based pixelation pass.

## Pipeline architecture

```
User story prompt
      ↓
Story Director LLM (fine-tuned Mistral-7B or Qwen3-8B)
      → outputs JSON scene manifest
      ↓
Character LLM (fine-tuned CodeLlama or Mistral)
      → outputs Blender Python scripts → .glb character files
      ↓
Godot 4 Headless Renderer
      → applies GodotPixelRenderer shader (by bukkbeek)
      → exports PNG frame sequences per scene
      ↓
Python Orchestrator
      → FFmpeg stitches frames
      → ElevenLabs TTS for dialogue/narration
      → final MP4 output
```

## Key components

| Component | Technology | Status |
|-----------|------------|--------|
| Story Director LLM | Mistral-7B-Instruct or Qwen3-8B, fine-tuned | Dataset ready, not yet fine-tuned |
| Character LLM | CodeLlama-7B or Mistral-7B, fine-tuned | Not started |
| 3D rendering | Godot 4 headless | Not started |
| Pixel art shader | GodotPixelRenderer (github.com/bukkbeek) | Not installed |
| Character creation | Blender + Python scripting + BlenderKit | Not started |
| Video assembly | FFmpeg | Standard tooling |
| TTS / dialogue | ElevenLabs | Free tier OK for prototyping |
| Fine-tuning platform | Together AI or RunPod A100 | Not yet used |

## Story framework (for the Story Director LLM)

Structure: **Hook → Foreshadow → Obstacle → Amplifier → Twist → Payoff**

Hard rules:
- Hook must land in 1.5–3 seconds
- Foreshadow is 2 lines, under 3 seconds
- But/therefore storytelling — never "and then"
- 5th-grade reading level or below
- 28–34 second total runtime (avoid 20s and 40s — they underperform)
- End immediately after payoff
- 90%+ retention = viral minimum

These rules came from the John Scott (Creator Rant) viral story masterclass and Jenny Hoyos (Creator Science) analytics framework.

## JSON scene manifest format (Story Director output)

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

This JSON is the interface between the LLM and the Godot renderer — it must stay stable.

## Training data — current state

**File:** `training_data_v7_clean.jsonl` (9,720 examples)
**Format:** OpenAI-compatible instruct format (`messages` with system/user/assistant)

**Sources:**
- Scraped YouTube transcripts from 300+ curated channels (storytelling, viral shorts, animation, masterclasses)
- Discord Q&A and monologues from the PixelBeef creator
- Jenny Hoyos / Creator Science interview
- Synthetic pixel-art scripts, hooks, and beat structures
- VidCon 2025 and Kaggle algorithm-research data

**Weight distribution:**
- weight=4 (high quality): 6,785 examples
- weight=3 (medium): 2,933 examples
- weight=2 (low): 2 examples
- weight=5 examples were extracted into `story_director_rules.md` (used as system-prompt rules, not training pairs)

**Cleaning applied:**
- Removed 94 examples missing user turn
- Removed 193 duplicate assistant responses
- Removed 96 examples over 6K tokens (exceeded Mistral-7B context)
- Removed 13 weight=5 masterclass lessons (now in rules file)

## Known dataset issue

**The biggest open problem:** zero examples currently output the JSON scene manifest format. Almost all assistant responses are raw YouTube transcripts or plain-text scripts. The model trained on this dataset will learn to write transcripts, not JSON.

To fix this, the dataset needs ~500–1000 synthetic examples where the assistant outputs proper JSON scene manifests following the viral story framework.

## Repository structure

```
ytllm/
├── CLAUDE.md                          # Full project brief
├── story_director_rules.md            # Production rules (from masterclass)
├── training_data_v7.jsonl             # Raw dataset (10,116 examples)
├── training_data_v7.txt               # Same, human-readable
├── training_data_v7_clean.jsonl       # Cleaned dataset (9,720 examples)
├── training_data_v7_clean.txt         # Same, human-readable
├── full_pipeline.py                   # Scrapes 300+ YouTube channels via yt-dlp
├── scrape_channels.py                 # Channel list (300+ channels, 15 categories)
├── scrape_story_v3.py                 # Latest scraper
├── prep_finetune.py                   # Prepares dataset for fine-tuning
├── merge_dataset.py                   # Combines datasets
├── generate_synthetic_local.py        # Generates synthetic examples
└── finetune_train.jsonl / val.jsonl   # Train/val split
```

## Immediate next steps (priority order)

1. **Generate JSON manifest training examples** — write a script that produces 500–1000 synthetic examples mapping story prompts → JSON scene manifests following the viral framework
2. **Fine-tune Story Director** on Together AI (Mistral-7B or Qwen3-8B base, ~$5–20 cost)
3. **Install Godot 4 + GodotPixelRenderer** — get one pixel-art scene rendering
4. **Build one scene end-to-end manually** — Blender character → .glb → Godot → headless PNG export → FFmpeg MP4
5. **Build Python orchestrator** — reads JSON manifest, drives Blender/Godot/FFmpeg/ElevenLabs

## Reference creators / tools

- **PixelBeef** (@pixelbeefshorts) — visual style reference
- **t3ssel8r** — pixel snapping shader reference
- **John Scott (Creator Rant)** — viral story formula
- **Jenny Hoyos (Creator Science)** — analytics framework (34s sweet spot, retention focus)
- **bukkbeek (GitHub)** — GodotPixelRenderer shader
- **BlenderKit** — Blender asset library (paid, recommended)
- **Quiver / Excalibur** — Premiere plugins for SFX hotkeys (used in production workflow)

## Notes for the next AI

- All training data is OpenAI instruct JSONL — compatible with Together AI, Axolotl, LLaMA-Factory, OpenAI fine-tuning API
- Scraper uses yt-dlp, no API keys needed
- Godot 4 headless works cross-platform: `godot --headless --script export_scene.gd -- scene.tscn output/`
- Test renderer with a cube scene before characters
- The JSON scene manifest is the contract between LLM and renderer — don't change its shape mid-development
- ElevenLabs has a free tier for TTS prototyping
- Don't waste budget fine-tuning a 32B model on this dataset until JSON examples are added — train a 7–8B model first
