"""
Canonical scene manifest schema — single source of truth.
All generators, validators, and renderers reference this file.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


BeatType = Literal["hook", "foreshadow", "obstacle", "amplifier", "twist", "payoff"]
CameraType = Literal["wide", "medium", "close", "extreme_close", "overhead", "low_angle"]
EmotionType = Literal[
    "suspense", "comedy", "horror", "heartwarming", "action",
    "mystery", "triumph", "tragedy", "shock", "curiosity"
]


class Scene(BaseModel):
    scene_id: int = Field(ge=1)
    beat_type: BeatType
    duration_sec: float = Field(gt=0, le=15)
    narration: str = Field(min_length=1, max_length=300)
    dialogue: Optional[str] = Field(default=None, max_length=200)
    characters_visible: list[str] = Field(min_length=1)
    camera: CameraType
    visual_description: str = Field(min_length=5, max_length=300)
    action: str = Field(min_length=5, max_length=200)
    emotion_intensity: float = Field(ge=0.0, le=1.0)


class SceneManifest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    target_duration_sec: int = Field(ge=20, le=60)
    emotion: EmotionType
    scenes: list[Scene] = Field(min_length=3, max_length=12)

    @model_validator(mode="after")
    def validate_structure(self) -> SceneManifest:
        beat_types = [s.beat_type for s in self.scenes]

        # First scene must be hook
        if beat_types[0] != "hook":
            raise ValueError("First scene must be beat_type='hook'")

        # Last scene must be payoff
        if beat_types[-1] != "payoff":
            raise ValueError("Last scene must be beat_type='payoff'")

        # Must contain a twist
        if "twist" not in beat_types:
            raise ValueError("Manifest must contain a 'twist' beat")

        # Hook duration must be under 4 seconds
        hook = self.scenes[0]
        if hook.duration_sec > 4.0:
            raise ValueError(f"Hook duration {hook.duration_sec}s exceeds 4s limit")

        # Scene IDs must be sequential starting at 1
        for i, scene in enumerate(self.scenes):
            if scene.scene_id != i + 1:
                raise ValueError(f"scene_id must be sequential: expected {i+1}, got {scene.scene_id}")

        # Total duration must be within 5s of target
        total = sum(s.duration_sec for s in self.scenes)
        if abs(total - self.target_duration_sec) > 5:
            raise ValueError(
                f"Total scene duration {total:.1f}s deviates >5s from target {self.target_duration_sec}s"
            )

        return self


def validate_manifest(data: dict) -> tuple[SceneManifest | None, str | None]:
    """Parse and validate a manifest dict. Returns (manifest, error)."""
    try:
        return SceneManifest.model_validate(data), None
    except Exception as e:
        return None, str(e)


def validate_json_string(json_str: str) -> tuple[SceneManifest | None, str | None]:
    """Parse and validate a JSON string."""
    import json
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    return validate_manifest(data)
