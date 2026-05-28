"""
Story Director — Claude API + training data few-shot context.

Usage:
    python generate_story.py "A delivery driver who discovers a package addressed to himself"
    python generate_story.py  (interactive mode, prompts you)

How it works:
    1. Loads ~50 best examples from training_data_v8.jsonl (john scott, jenny hoyos,
       discord wisdom, script examples) and injects them into the system prompt.
    2. Caches the entire system prompt + training context using Anthropic prompt caching
       — first call pays ~$0.05, subsequent calls pay ~$0.003 (cached tokens are 90% cheaper).
    3. Calls claude-opus-4-7 with the cached context + your story prompt.
    4. Returns a JSON scene manifest ready to feed into the Godot render pipeline.

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

import json
import os
import sys
import textwrap
from pathlib import Path
from collections import defaultdict

import anthropic

# ── Config ────────────────────────────────────────────────────────────────────

TRAINING_DATA = Path(__file__).parent / "training_data_v8.jsonl"
MAX_TRAINING_EXAMPLES = 50   # how many training examples to inject as context
MIN_EXAMPLE_LEN = 150        # skip very short assistant responses
MAX_EXAMPLE_LEN = 800        # truncate long ones to keep token count reasonable

# These sources contain the highest-signal creator wisdom
PRIORITY_SOURCES = {
    "john_scott_lesson",           # Creator Rant masterclass — weight 4-5
    "jenny_hoyos_interview",       # Jenny Hoyos retention data — weight 4
    "synthetic_script_30s",        # Beat-structure scripts — weight 3
    "synthetic_structure",         # Beat breakdowns — weight 3
    "hook_formulas",               # Hook patterns — weight 3
    "discord_qa",                  # Real creator Q&A — weight 4
    "yt_transcript_masterclass_creator_rant",  # Creator Rant lessons
}

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_CORE = """You are a Story Director for viral short-form pixel-art animated videos in the style of PixelBeef (@pixelbeefshorts).

Your ONLY job: take a story prompt and output a structured JSON scene manifest.

## Beat Structure (mandatory)
1. hook        — visual + verbal punch in first 1.5-3 seconds. Promise something is coming.
2. foreshadow  — exactly 2 lines, under 3 seconds. Plant the seed of what's coming.
3. obstacle    — the conflict hits. Use "but" — something goes wrong.
4. amplifier   — stakes escalate. Use "therefore" — things get worse because of obstacle.
5. twist       — unexpected reversal. Subvert what the viewer predicted.
6. payoff      — instant resolution. One expression. Cut immediately.

## Hard Rules
- Total runtime: 28-34 seconds (target 30s or 50s — never 20s or 40s)
- 5th-grade reading level — short punchy narration only
- But/Therefore storytelling — NEVER "and then"
- End IMMEDIATELY after payoff — no breathing room
- emotion_intensity escalates: hook ~0.6 → payoff ~1.0
- Hook must land the promise in the first frame — no setup, drop in mid-action

## Output Format
Respond with ONLY valid JSON. No markdown. No explanation. No code fences.

{
  "title": "string",
  "target_duration_sec": 30,
  "emotion": "suspense|comedy|horror|heartwarming|action|mystery|triumph|tragedy|shock|curiosity",
  "scenes": [
    {
      "scene_id": 1,
      "beat_type": "hook|foreshadow|obstacle|amplifier|twist|payoff",
      "duration_sec": 3,
      "narration": "spoken voiceover line",
      "dialogue": null,
      "characters_visible": ["character_name"],
      "camera": "wide|medium|close|extreme_close|overhead|low_angle",
      "visual_description": "what the viewer sees",
      "action": "what happens physically in this beat",
      "emotion_intensity": 0.7
    }
  ]
}"""

# ── Load training wisdom ──────────────────────────────────────────────────────

def load_training_wisdom(path: Path) -> str:
    """
    Loads the best creator wisdom from training data as a block of text
    to inject into the system prompt context.
    """
    if not path.exists():
        return ""

    by_source = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            source = rec.get("source", "")
            if source not in PRIORITY_SOURCES:
                continue
            msgs = rec.get("messages", [])
            user_msg = next((m["content"] for m in msgs if m["role"] == "user"), "")
            asst_msg = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
            if len(asst_msg) < MIN_EXAMPLE_LEN:
                continue
            by_source[source].append({
                "weight": rec.get("weight", 3),
                "user": user_msg[:200],
                "assistant": asst_msg[:MAX_EXAMPLE_LEN],
            })

    # Sort each source by weight (highest first), cap per source to avoid dominance
    pool = []
    caps = {
        "john_scott_lesson": 7,
        "jenny_hoyos_interview": 10,
        "synthetic_script_30s": 8,
        "synthetic_structure": 8,
        "hook_formulas": 5,
        "discord_qa": 10,
        "yt_transcript_masterclass_creator_rant": 5,
    }
    for source, items in by_source.items():
        items.sort(key=lambda x: -x["weight"])
        cap = caps.get(source, 5)
        pool.extend(items[:cap])

    pool.sort(key=lambda x: -x["weight"])
    pool = pool[:MAX_TRAINING_EXAMPLES]

    if not pool:
        return ""

    lines = [
        "\n\n## Creator Wisdom (extracted from real masterclasses and creator Q&A)\n",
        "Study these principles. They define what makes a Short go viral.\n",
    ]
    for ex in pool:
        lines.append(f"\nQ: {ex['user']}")
        lines.append(f"A: {ex['assistant']}\n")

    return "\n".join(lines)


# ── Few-shot JSON example ─────────────────────────────────────────────────────

FEW_SHOT_PROMPT = "A bus robbery where the woman had a decoy phone"

FEW_SHOT_MANIFEST = {
    "title": "Not Her First Robbery",
    "target_duration_sec": 30,
    "emotion": "suspense",
    "scenes": [
        {
            "scene_id": 1,
            "beat_type": "hook",
            "duration_sec": 3,
            "narration": "This bus is about to get robbed. But this woman — she's got a plan.",
            "dialogue": None,
            "characters_visible": ["woman", "thief"],
            "camera": "wide",
            "visual_description": "City bus interior. Masked thief stands at front, gun raised. Passengers freeze.",
            "action": "Thief raises gun, everyone freezes except one woman who stays eerily calm",
            "emotion_intensity": 0.7
        },
        {
            "scene_id": 2,
            "beat_type": "foreshadow",
            "duration_sec": 3,
            "narration": "One by one, he took from every passenger. She was next.",
            "dialogue": None,
            "characters_visible": ["thief", "woman"],
            "camera": "medium",
            "visual_description": "Thief moves down aisle collecting phones and wallets. Woman watches without moving.",
            "action": "Thief approaches row by row, woman's hand slowly moves toward her purse",
            "emotion_intensity": 0.6
        },
        {
            "scene_id": 3,
            "beat_type": "obstacle",
            "duration_sec": 5,
            "narration": "But the moment his back turned — she started digging.",
            "dialogue": None,
            "characters_visible": ["woman"],
            "camera": "close",
            "visual_description": "Woman's hands frantically searching inside large purse",
            "action": "Woman pulls out phone, slides it under her leg before thief turns around",
            "emotion_intensity": 0.8
        },
        {
            "scene_id": 4,
            "beat_type": "amplifier",
            "duration_sec": 5,
            "narration": "Therefore — when he got to her, she had a phone ready. Just not THE phone.",
            "dialogue": None,
            "characters_visible": ["woman", "thief"],
            "camera": "close",
            "visual_description": "Thief looms over her, pillowcase open. Woman reaches into purse — not under her leg.",
            "action": "Woman slowly produces a different phone, hands it over",
            "emotion_intensity": 0.9
        },
        {
            "scene_id": 5,
            "beat_type": "twist",
            "duration_sec": 4,
            "narration": "He took it. Walked off the bus. Never looked back.",
            "dialogue": None,
            "characters_visible": ["woman"],
            "camera": "medium",
            "visual_description": "Thief exits. Door closes. Woman stares forward for one beat.",
            "action": "Woman waits for door to close, then lifts leg",
            "emotion_intensity": 0.95
        },
        {
            "scene_id": 6,
            "beat_type": "payoff",
            "duration_sec": 3,
            "narration": "Turns out — this wasn't her first robbery.",
            "dialogue": None,
            "characters_visible": ["woman"],
            "camera": "extreme_close",
            "visual_description": "Real phone in her hand, screen lit. Small smirk.",
            "action": "Cut to black immediately",
            "emotion_intensity": 1.0
        }
    ]
}


# ── Build system prompt with cached training context ──────────────────────────

def build_system_prompt() -> str:
    wisdom = load_training_wisdom(TRAINING_DATA)
    return SYSTEM_CORE + wisdom


# ── Generate scene manifest ───────────────────────────────────────────────────

def generate_manifest(story_prompt: str, verbose: bool = True) -> dict:
    """
    Call Claude API with cached training context and return a JSON scene manifest.

    The system prompt (with all training wisdom) is cached after the first call.
    Subsequent calls with the same prompt reuse the cache — 90% token cost reduction.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Set ANTHROPIC_API_KEY environment variable")

    client = anthropic.Anthropic(api_key=api_key)
    system_prompt = build_system_prompt()

    if verbose:
        print(f"System prompt: ~{len(system_prompt)//4:,} tokens (cached after first call)")
        print(f"Story prompt : {story_prompt}")
        print("Calling claude-opus-4-7...")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},  # cache the entire training context
            }
        ],
        messages=[
            # Few-shot example — cached together with system prompt
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": FEW_SHOT_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            },
            {
                "role": "assistant",
                "content": json.dumps(FEW_SHOT_MANIFEST, indent=2),
            },
            # Actual request
            {"role": "user", "content": story_prompt},
        ],
    )

    raw = response.content[0].text.strip()

    # Strip any accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    manifest = json.loads(raw)

    if verbose:
        usage = response.usage
        cache_read = getattr(usage, "cache_read_input_tokens", 0)
        cache_write = getattr(usage, "cache_creation_input_tokens", 0)
        print(f"\nTokens — input: {usage.input_tokens}, output: {usage.output_tokens}")
        if cache_write:
            print(f"         cache WRITE: {cache_write:,}  (paid once, reused for free next time)")
        if cache_read:
            print(f"         cache READ:  {cache_read:,}  (90% cheaper than fresh input)")

    return manifest


# ── Pretty print manifest ─────────────────────────────────────────────────────

def print_manifest(manifest: dict) -> None:
    print(f"\n{'='*60}")
    print(f"  {manifest.get('title', 'Untitled')}")
    print(f"  {manifest.get('target_duration_sec', '?')}s  |  emotion: {manifest.get('emotion', '?')}")
    print(f"{'='*60}")
    for scene in manifest.get("scenes", []):
        beat = scene.get("beat_type", "?").upper()
        dur  = scene.get("duration_sec", "?")
        narr = scene.get("narration", "")
        act  = scene.get("action", "")
        cam  = scene.get("camera", "")
        intens = scene.get("emotion_intensity", 0)
        print(f"\n[{beat}]  {dur}s  cam:{cam}  intensity:{intens}")
        print(f"  NARRATION: {narr}")
        print(f"  ACTION:    {act}")
    print(f"\n{'='*60}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        print("Story Director — Claude API")
        print("Enter your story prompt (or Ctrl+C to quit):\n")
        prompt = input("> ").strip()
        if not prompt:
            print("No prompt given.")
            sys.exit(1)

    try:
        manifest = generate_manifest(prompt, verbose=True)
        print_manifest(manifest)

        # Save to outputs/
        out_dir = Path(__file__).parent / "outputs"
        out_dir.mkdir(exist_ok=True)
        safe_title = manifest.get("title", "untitled").lower().replace(" ", "_")[:40]
        out_file = out_dir / f"{safe_title}.json"
        out_file.write_text(json.dumps(manifest, indent=2))
        print(f"\nSaved: {out_file}")

    except json.JSONDecodeError as e:
        print(f"\nError: Claude returned non-JSON output. {e}")
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"\nAPI error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
