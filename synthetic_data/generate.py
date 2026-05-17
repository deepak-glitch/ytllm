"""
Synthetic JSON manifest dataset generator.

Generates training examples in instruct format:
  user: story prompt
  assistant: valid JSON scene manifest

Run:
  python synthetic_data/generate.py --count 1000 --output synthetic_data/manifests_v1.jsonl

Optional LLM mode (requires OPENAI_API_KEY or TOGETHER_API_KEY):
  python synthetic_data/generate.py --count 1000 --llm together --model Qwen/Qwen3-8B-Instruct
"""

import json
import random
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.scene_manifest import validate_manifest
from prompts.story_director import SYSTEM_PROMPT, build_prompt


# ---------------------------------------------------------------------------
# Seed story prompts — varied genres, premises, hooks
# ---------------------------------------------------------------------------

STORY_PROMPTS = [
    # Everyday relatable
    "A man stuck in traffic desperately needs to use the bathroom",
    "A delivery driver accidentally rings the wrong doorbell",
    "A woman realizes she wore her shirt inside out to an important meeting",
    "A guy accidentally texts his boss the message meant for his friend",
    "A kid microwaves something they shouldn't have",
    "A woman locks her keys in the car with the engine running",
    "Someone falls asleep on public transit and misses their stop by 10 stations",
    "A man accidentally calls his teacher mom",

    # Revenge / karma
    "A parking space thief gets instant karma",
    "A food thief at work gets caught by their own trap",
    "A bully on the school bus hurts himself on a prank he set for someone else",
    "A man superglues his mailbox to stop kids knocking it over",
    "A neighbor keeps stealing packages until one is booby-trapped",
    "A shoplifter gets caught by their own selfie",

    # Clever / heist
    "A bus robbery where the victim had a hidden decoy phone",
    "A street vendor uses a clever trick to double his sales",
    "A student hides a cheat sheet in the most unexpected place",
    "A thief returns stolen goods after realizing who they stole from",
    "A woman outsmarts a scammer by playing along until the last second",
    "A man talks his way out of a speeding ticket using only the truth",

    # Horror / suspense
    "A hiker realizes they've been followed the entire trail",
    "A woman hears someone in her attic but it's been empty for years",
    "A hotel guest finds evidence someone was living in the walls",
    "A man finds his identical twin — he's an only child",
    "A security guard reviews footage and realizes what they missed",
    "A woman's smart home starts responding to a second voice",

    # Heartwarming / twist
    "A homeless man returns a wallet and discovers what's inside",
    "A grumpy old man secretly feeds stray cats every night",
    "A little girl asks a police officer to arrest her mom — for a sweet reason",
    "A nurse realizes the patient she's helping saved her life years ago",
    "A stray dog leads a mailman to a hidden emergency",

    # Action / thriller
    "A man realizes mid-flight he's seated next to someone who wants to rob him",
    "A getaway driver has second thoughts at the last possible second",
    "A woman realizes the rideshare driver has locked the doors",
    "A pickpocket steals a phone and immediately gets a call he has to answer",

    # Comedy
    "A man tries to pretend he knows how to cook at a first date dinner",
    "A guy buys a lie detector app and uses it on his whole family",
    "A kid tries to sell lemonade but keeps underselling it on accident",
    "A man's autocorrect starts a chain reaction he can't stop",
    "A guy wears a Halloween costume to the wrong party",

    # Mystery / revelation
    "A woman finds a letter addressed to her — dated 30 years from now",
    "A boy discovers why his grandfather always sits by the same window",
    "A man finds his own obituary in a newspaper from last week",
    "A girl realizes the imaginary friend she had as a child was real",
    "A detective solves the case by noticing one tiny impossible detail",

    # Social / viral premise
    "A man bets a horse will pick better stock trades than him — and it does",
    "A content creator goes viral for all the wrong reasons",
    "A man challenges a street performer and immediately regrets it",
    "A student earns extra credit in the most unexpected way",
    "A kid answers a teacher's trick question perfectly without knowing it",
]


# ---------------------------------------------------------------------------
# Template-based generation
# ---------------------------------------------------------------------------

EMOTIONS = ["suspense", "comedy", "horror", "heartwarming", "action", "mystery", "triumph", "shock", "curiosity"]
CAMERAS = ["wide", "medium", "close", "extreme_close", "overhead", "low_angle"]

BEAT_TEMPLATES = {
    "hook": {
        "duration_sec": lambda: round(random.uniform(2.0, 3.5), 1),
        "emotion_intensity": lambda: round(random.uniform(0.55, 0.75), 2),
        "camera": lambda: random.choice(["wide", "medium"]),
    },
    "foreshadow": {
        "duration_sec": lambda: round(random.uniform(2.5, 4.0), 1),
        "emotion_intensity": lambda: round(random.uniform(0.5, 0.65), 2),
        "camera": lambda: random.choice(["medium", "wide"]),
    },
    "obstacle": {
        "duration_sec": lambda: round(random.uniform(4.0, 6.0), 1),
        "emotion_intensity": lambda: round(random.uniform(0.65, 0.80), 2),
        "camera": lambda: random.choice(["medium", "close"]),
    },
    "amplifier": {
        "duration_sec": lambda: round(random.uniform(4.0, 7.0), 1),
        "emotion_intensity": lambda: round(random.uniform(0.75, 0.90), 2),
        "camera": lambda: random.choice(["close", "medium"]),
    },
    "twist": {
        "duration_sec": lambda: round(random.uniform(4.0, 7.0), 1),
        "emotion_intensity": lambda: round(random.uniform(0.88, 0.97), 2),
        "camera": lambda: random.choice(["extreme_close", "close"]),
    },
    "payoff": {
        "duration_sec": lambda: round(random.uniform(3.0, 5.0), 1),
        "emotion_intensity": lambda: 1.0,
        "camera": lambda: random.choice(["medium", "wide"]),
    },
}

BEAT_SEQUENCES = [
    ["hook", "foreshadow", "obstacle", "amplifier", "twist", "payoff"],
    ["hook", "foreshadow", "obstacle", "twist", "payoff"],
    ["hook", "obstacle", "amplifier", "twist", "payoff"],
    ["hook", "foreshadow", "obstacle", "amplifier", "amplifier", "twist", "payoff"],
]


def _placeholder_text(beat: str, prompt: str) -> dict:
    """Generate placeholder narration/action/visual for a beat."""
    templates = {
        "hook": {
            "narration": f"Nobody expected what was about to happen.",
            "action": "Scene opens with the main character in an ordinary situation",
            "visual_description": "Wide establishing shot of the setting with main character visible",
        },
        "foreshadow": {
            "narration": "But something felt off.",
            "action": "Character notices a detail that will matter later",
            "visual_description": "Camera lingers on an object or person in the background",
        },
        "obstacle": {
            "narration": "Then everything changed.",
            "action": "The central conflict or problem hits the character directly",
            "visual_description": "Close shot of character's reaction to the obstacle",
        },
        "amplifier": {
            "narration": "And just when it couldn't get worse — it did.",
            "action": "Stakes escalate, character is under maximum pressure",
            "visual_description": "Tension framing — character cornered or overwhelmed",
        },
        "twist": {
            "narration": "But nobody saw this coming.",
            "action": "The unexpected reversal — the thing the viewer was not expecting",
            "visual_description": "Reveal shot — the hidden truth becomes visible",
        },
        "payoff": {
            "narration": "Turns out, they'd planned this all along.",
            "action": "Resolution snaps into place — cut immediately after",
            "visual_description": "Final image — character in control, situation resolved",
        },
    }
    return templates[beat]


def generate_template_manifest(prompt: str) -> dict:
    """Generate a valid manifest dict from templates."""
    beat_seq = random.choice(BEAT_SEQUENCES)
    emotion = random.choice(EMOTIONS)
    target = 30

    scenes = []
    for i, beat in enumerate(beat_seq):
        tmpl = BEAT_TEMPLATES[beat]
        text = _placeholder_text(beat, prompt)
        scenes.append({
            "scene_id": i + 1,
            "beat_type": beat,
            "duration_sec": tmpl["duration_sec"](),
            "narration": text["narration"],
            "dialogue": None,
            "characters_visible": ["character"],
            "camera": tmpl["camera"](),
            "visual_description": text["visual_description"],
            "action": text["action"],
            "emotion_intensity": tmpl["emotion_intensity"](),
        })

    # Adjust last scene duration so total ≈ target
    current_total = sum(s["duration_sec"] for s in scenes)
    diff = target - current_total
    scenes[-1]["duration_sec"] = round(max(2.0, scenes[-1]["duration_sec"] + diff), 1)

    title = prompt.replace("A ", "").replace("a ", "").strip()
    title = title[:60].title() if len(title) > 60 else title.title()

    return {
        "title": title,
        "target_duration_sec": target,
        "emotion": emotion,
        "scenes": scenes,
    }


def manifest_to_training_example(prompt: str, manifest: dict) -> dict:
    """Wrap a manifest into OpenAI instruct format."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": json.dumps(manifest, indent=2)},
        ],
        "source": "synthetic_json_manifest",
        "weight": 4,
    }


# ---------------------------------------------------------------------------
# LLM-based generation (optional)
# ---------------------------------------------------------------------------

def generate_llm_manifest(prompt: str, client, model: str) -> dict | None:
    """Call an LLM to generate a manifest. Returns dict or None on failure."""
    import json as _json
    messages = build_prompt(prompt, include_few_shot=True)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.8,
            max_tokens=1200,
        )
        content = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = _json.loads(content)
        manifest, err = validate_manifest(data) if True else (None, None)
        if err:
            return None
        return data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic JSON manifest training data")
    parser.add_argument("--count", type=int, default=1000, help="Number of examples to generate")
    parser.add_argument("--output", type=str, default="synthetic_data/manifests_v1.jsonl")
    parser.add_argument("--llm", choices=["together", "openai"], default=None,
                        help="Use LLM for generation instead of templates")
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-8B-Instruct",
                        help="Model to use for LLM generation")
    parser.add_argument("--template-fallback", action="store_true",
                        help="Fall back to templates if LLM generation fails")
    args = parser.parse_args()

    client = None
    if args.llm:
        try:
            from openai import OpenAI
            import os
            if args.llm == "together":
                client = OpenAI(
                    api_key=os.environ["TOGETHER_API_KEY"],
                    base_url="https://api.together.xyz/v1",
                )
            else:
                client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        except Exception as e:
            print(f"Failed to init LLM client: {e}")
            sys.exit(1)

    # Expand prompt pool by repeating and shuffling if count > pool size
    prompts = STORY_PROMPTS.copy()
    while len(prompts) < args.count:
        prompts.extend(STORY_PROMPTS)
    random.shuffle(prompts)
    prompts = prompts[:args.count]

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    valid = 0
    invalid = 0

    with open(out_path, "w") as f:
        for i, prompt in enumerate(prompts):
            manifest = None

            if client:
                manifest = generate_llm_manifest(prompt, client, args.model)
                if manifest is None:
                    invalid += 1
                    if not args.template_fallback:
                        continue
                    manifest = generate_template_manifest(prompt)
            else:
                manifest = generate_template_manifest(prompt)

            # Validate
            _, err = validate_manifest(manifest)
            if err:
                invalid += 1
                continue

            example = manifest_to_training_example(prompt, manifest)
            f.write(json.dumps(example) + "\n")
            valid += 1

            if (i + 1) % 100 == 0:
                print(f"  [{i+1}/{args.count}] valid={valid} invalid={invalid}")

    print(f"\nDone. {valid} valid examples written to {out_path} ({invalid} discarded)")


if __name__ == "__main__":
    main()
