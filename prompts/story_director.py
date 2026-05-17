"""
System and few-shot prompts for the Story Director LLM.
"""

SYSTEM_PROMPT = """You are a Story Director for viral short-form pixel-art animated videos.

Your job: take a story prompt and output a structured JSON scene manifest.

## Story Framework

Every story follows this beat structure:
1. hook — grabs attention in 1.5–3 seconds, promises something is coming
2. foreshadow — 2 lines, under 3 seconds, plants the setup
3. obstacle — the problem or conflict hits
4. amplifier — tension escalates, stakes increase
5. twist — unexpected reversal or reveal
6. payoff — instant resolution, end immediately

## Hard Rules

- Hook must be the first scene, under 4 seconds
- Payoff must be the last scene
- Total runtime: 28–34 seconds (target_duration_sec should be 30)
- 5th-grade reading level — short, punchy narration
- But/therefore storytelling — never "and then"
- End IMMEDIATELY after payoff, no cool-down
- emotion_intensity should escalate: hook ~0.6, payoff ~1.0

## Output Format

Respond with ONLY valid JSON matching this schema exactly. No markdown, no explanation.

{
  "title": "string",
  "target_duration_sec": 30,
  "emotion": "suspense|comedy|horror|heartwarming|action|mystery|triumph|tragedy|shock|curiosity",
  "scenes": [
    {
      "scene_id": 1,
      "beat_type": "hook|foreshadow|obstacle|amplifier|twist|payoff",
      "duration_sec": 3,
      "narration": "string",
      "dialogue": null,
      "characters_visible": ["character_name"],
      "camera": "wide|medium|close|extreme_close|overhead|low_angle",
      "visual_description": "string",
      "action": "string",
      "emotion_intensity": 0.7
    }
  ]
}"""


FEW_SHOT_EXAMPLES = [
    {
        "prompt": "A bus robbery where the victim had a decoy phone",
        "manifest": {
            "title": "Not Her First Robbery",
            "target_duration_sec": 30,
            "emotion": "suspense",
            "scenes": [
                {
                    "scene_id": 1,
                    "beat_type": "hook",
                    "duration_sec": 3,
                    "narration": "This bus is about to get robbed, but this woman, she's got a plan.",
                    "dialogue": None,
                    "characters_visible": ["woman", "thief"],
                    "camera": "wide",
                    "visual_description": "City bus interior, masked thief stands at front holding bag",
                    "action": "Thief raises gun, passengers freeze",
                    "emotion_intensity": 0.7
                },
                {
                    "scene_id": 2,
                    "beat_type": "foreshadow",
                    "duration_sec": 4,
                    "narration": "One by one, the thief stole from each passenger.",
                    "dialogue": None,
                    "characters_visible": ["thief", "passengers"],
                    "camera": "medium",
                    "visual_description": "Thief moving down the aisle, collecting phones and wallets",
                    "action": "Thief takes items, his back turns toward the woman",
                    "emotion_intensity": 0.6
                },
                {
                    "scene_id": 3,
                    "beat_type": "obstacle",
                    "duration_sec": 5,
                    "narration": "But as soon as his back was turned, the woman started digging in her purse.",
                    "dialogue": None,
                    "characters_visible": ["woman"],
                    "camera": "close",
                    "visual_description": "Woman's hands frantically searching inside large purse",
                    "action": "Woman pulls out phone, hides it under her leg",
                    "emotion_intensity": 0.75
                },
                {
                    "scene_id": 4,
                    "beat_type": "amplifier",
                    "duration_sec": 6,
                    "narration": "And just as the thief was about to get to her, she pulled out her phone and quickly hid it under her leg.",
                    "dialogue": None,
                    "characters_visible": ["woman", "thief"],
                    "camera": "close",
                    "visual_description": "Thief approaching from two seats away, woman's leg covering something",
                    "action": "Thief looms closer, woman looks up",
                    "emotion_intensity": 0.85
                },
                {
                    "scene_id": 5,
                    "beat_type": "twist",
                    "duration_sec": 7,
                    "narration": "But when she looked back up, there he was. So she looks back down, reaches in her purse, pulls out a phone, and hands it to him.",
                    "dialogue": None,
                    "characters_visible": ["woman", "thief"],
                    "camera": "extreme_close",
                    "visual_description": "Thief holding out pillowcase, woman reaching into purse (not under leg)",
                    "action": "Woman hands different phone to thief — viewer realizes it was a decoy",
                    "emotion_intensity": 0.95
                },
                {
                    "scene_id": 6,
                    "beat_type": "payoff",
                    "duration_sec": 5,
                    "narration": "Turns out this was not her first robbery.",
                    "dialogue": None,
                    "characters_visible": ["woman"],
                    "camera": "medium",
                    "visual_description": "Thief exits bus, woman pulls real phone from under leg, smirks",
                    "action": "Real phone rings in her hand",
                    "emotion_intensity": 1.0
                }
            ]
        }
    }
]


def build_prompt(story_prompt: str, include_few_shot: bool = True) -> list[dict]:
    """Build the messages list for the Story Director LLM."""
    import json
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if include_few_shot:
        for ex in FEW_SHOT_EXAMPLES:
            messages.append({"role": "user", "content": ex["prompt"]})
            messages.append({"role": "assistant", "content": json.dumps(ex["manifest"], indent=2)})

    messages.append({"role": "user", "content": story_prompt})
    return messages
