"""
Story evaluator — scores a scene manifest against viral storytelling metrics.

Usage:
    from evaluators.story_evaluator import evaluate
    result = evaluate(manifest_dict)
    print(result.score, result.breakdown)
"""

from __future__ import annotations
import sys
from pathlib import Path
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.scene_manifest import validate_manifest, SceneManifest


@dataclass
class EvalResult:
    score: float                          # 0.0 – 1.0 overall
    passed: bool                          # score >= pass_threshold
    breakdown: dict[str, float]           # per-metric scores
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"Score: {self.score:.2f} | {'PASS' if self.passed else 'FAIL'}"]
        for k, v in self.breakdown.items():
            lines.append(f"  {k:<28} {v:.2f}")
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  ✗ {e}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        return "\n".join(lines)


PASS_THRESHOLD = 0.70

# Weights for each metric (must sum to 1.0)
METRIC_WEIGHTS = {
    "valid_schema":           0.20,
    "hook_strength":          0.15,
    "runtime_fit":            0.12,
    "beat_completeness":      0.12,
    "emotional_escalation":   0.12,
    "curiosity_gap":          0.10,
    "narration_brevity":      0.08,
    "dialogue_pacing":        0.06,
    "visual_clarity":         0.05,
}

assert abs(sum(METRIC_WEIGHTS.values()) - 1.0) < 1e-6, "Weights must sum to 1.0"


def _score_valid_schema(manifest: SceneManifest | None, err: str | None) -> tuple[float, list[str]]:
    if manifest is None:
        return 0.0, [f"Schema validation failed: {err}"]
    return 1.0, []


def _score_hook_strength(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    errors, warnings = [], []
    hook = m.scenes[0]
    score = 1.0

    if hook.beat_type != "hook":
        errors.append("First scene is not beat_type='hook'")
        score -= 0.5

    if hook.duration_sec > 3.5:
        warnings.append(f"Hook is {hook.duration_sec}s — ideally under 3s")
        score -= 0.2
    elif hook.duration_sec > 4.0:
        errors.append(f"Hook duration {hook.duration_sec}s exceeds 4s limit")
        score -= 0.4

    if hook.emotion_intensity < 0.5:
        warnings.append(f"Hook emotion_intensity {hook.emotion_intensity} is low — should open with energy")
        score -= 0.2

    # Narration should be short and punchy
    words = len(hook.narration.split())
    if words > 20:
        warnings.append(f"Hook narration is {words} words — aim for under 15")
        score -= 0.1

    return max(0.0, score), errors, warnings


def _score_runtime_fit(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    errors, warnings = [], []
    total = sum(s.duration_sec for s in m.scenes)
    target = m.target_duration_sec
    diff = abs(total - target)

    if diff <= 2:
        score = 1.0
    elif diff <= 5:
        score = 0.7
        warnings.append(f"Total runtime {total:.1f}s deviates {diff:.1f}s from target {target}s")
    else:
        score = max(0.0, 1.0 - (diff - 5) * 0.1)
        errors.append(f"Total runtime {total:.1f}s too far from target {target}s")

    if m.target_duration_sec < 28 or m.target_duration_sec > 34:
        warnings.append(f"target_duration_sec={m.target_duration_sec} — 28–34s is the viral sweet spot")
        score *= 0.8

    return score, errors, warnings


def _score_beat_completeness(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    errors, warnings = [], []
    beats = [s.beat_type for s in m.scenes]
    required = {"hook", "twist", "payoff"}
    recommended = {"foreshadow", "obstacle"}
    score = 1.0

    for b in required:
        if b not in beats:
            errors.append(f"Missing required beat: '{b}'")
            score -= 0.3

    for b in recommended:
        if b not in beats:
            warnings.append(f"Missing recommended beat: '{b}'")
            score -= 0.1

    if beats[-1] != "payoff":
        errors.append("Last scene must be 'payoff'")
        score -= 0.2

    return max(0.0, score), errors, warnings


def _score_emotional_escalation(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    errors, warnings = [], []
    intensities = [s.emotion_intensity for s in m.scenes]

    # Expect general upward trend (allow minor dips)
    inversions = 0
    for i in range(1, len(intensities)):
        if intensities[i] < intensities[i - 1] - 0.1:
            inversions += 1

    if m.scenes[-1].emotion_intensity < 0.85:
        errors.append(f"Final payoff emotion_intensity {m.scenes[-1].emotion_intensity} — should be ≥0.85")
        score = 0.4
    elif inversions == 0:
        score = 1.0
    elif inversions == 1:
        score = 0.8
        warnings.append("One intensity inversion — story dips in tension briefly")
    else:
        score = max(0.3, 1.0 - inversions * 0.2)
        warnings.append(f"{inversions} intensity inversions — escalation is inconsistent")

    return score, errors, warnings


def _score_curiosity_gap(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    errors, warnings = [], []
    beats = [s.beat_type for s in m.scenes]

    has_twist = "twist" in beats
    has_foreshadow = "foreshadow" in beats
    twist_near_end = False

    if has_twist:
        twist_pos = beats.index("twist")
        twist_near_end = twist_pos >= len(beats) - 3

    if not has_twist:
        errors.append("No 'twist' beat — curiosity gap requires a reversal")
        return 0.0, errors, warnings

    score = 0.6
    if twist_near_end:
        score += 0.2
    else:
        warnings.append("Twist appears too early — should be near the end for maximum impact")

    if has_foreshadow:
        score += 0.2
    else:
        warnings.append("No 'foreshadow' beat — planting setup improves payoff impact")

    return min(1.0, score), errors, warnings


def _score_narration_brevity(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    warnings = []
    total_words = sum(len(s.narration.split()) for s in m.scenes)
    avg_words = total_words / len(m.scenes)

    if avg_words <= 12:
        score = 1.0
    elif avg_words <= 18:
        score = 0.8
        warnings.append(f"Average narration {avg_words:.0f} words/scene — aim for 12 or under")
    elif avg_words <= 25:
        score = 0.5
        warnings.append(f"Average narration {avg_words:.0f} words/scene — too verbose")
    else:
        score = 0.2
        warnings.append(f"Average narration {avg_words:.0f} words/scene — this is way too long")

    return score, [], warnings


def _score_dialogue_pacing(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    warnings = []
    scenes_with_dialogue = [s for s in m.scenes if s.dialogue]

    if not scenes_with_dialogue:
        return 0.9, [], []  # Narration-only is fine

    for s in scenes_with_dialogue:
        words = len(s.dialogue.split())
        if words > 15:
            warnings.append(f"Scene {s.scene_id} dialogue is {words} words — keep dialogue punchy (<15 words)")

    score = 1.0 if not warnings else 0.7
    return score, [], warnings


def _score_visual_clarity(m: SceneManifest) -> tuple[float, list[str], list[str]]:
    warnings = []
    score = 1.0

    for s in m.scenes:
        if len(s.visual_description) < 10:
            warnings.append(f"Scene {s.scene_id} visual_description too vague")
            score -= 0.05
        if len(s.action) < 10:
            warnings.append(f"Scene {s.scene_id} action too vague")
            score -= 0.05
        if not s.characters_visible:
            warnings.append(f"Scene {s.scene_id} has no characters_visible")
            score -= 0.05

    return max(0.0, score), [], warnings


def evaluate(manifest_data: dict, pass_threshold: float = PASS_THRESHOLD) -> EvalResult:
    """Score a manifest dict. Returns EvalResult with score and breakdown."""
    all_errors = []
    all_warnings = []
    breakdown = {}

    manifest, schema_err = validate_manifest(manifest_data)

    # Schema validity (fatal if fails — other metrics get 0)
    schema_score, schema_errors = _score_valid_schema(manifest, schema_err)
    all_errors.extend(schema_errors)
    breakdown["valid_schema"] = schema_score

    if manifest is None:
        for metric in METRIC_WEIGHTS:
            if metric != "valid_schema":
                breakdown[metric] = 0.0
        total = schema_score * METRIC_WEIGHTS["valid_schema"]
        return EvalResult(
            score=round(total, 4),
            passed=total >= pass_threshold,
            breakdown=breakdown,
            errors=all_errors,
            warnings=all_warnings,
        )

    # Run all metrics
    metrics = [
        ("hook_strength",        _score_hook_strength(manifest)),
        ("runtime_fit",          _score_runtime_fit(manifest)),
        ("beat_completeness",    _score_beat_completeness(manifest)),
        ("emotional_escalation", _score_emotional_escalation(manifest)),
        ("curiosity_gap",        _score_curiosity_gap(manifest)),
        ("narration_brevity",    _score_narration_brevity(manifest)),
        ("dialogue_pacing",      _score_dialogue_pacing(manifest)),
        ("visual_clarity",       _score_visual_clarity(manifest)),
    ]

    for name, result in metrics:
        score_val, errors, warnings = result
        breakdown[name] = round(score_val, 4)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    # Weighted total
    total = sum(breakdown[m] * w for m, w in METRIC_WEIGHTS.items())

    return EvalResult(
        score=round(total, 4),
        passed=total >= pass_threshold,
        breakdown=breakdown,
        errors=all_errors,
        warnings=all_warnings,
    )


def evaluate_file(path: str, verbose: bool = False) -> dict:
    """Evaluate all manifests in a JSONL file. Returns aggregate stats."""
    import json

    scores = []
    pass_count = 0
    fail_count = 0

    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            # Support both raw manifest and instruct-format examples
            if "messages" in data:
                assistant_content = next(
                    (m["content"] for m in data["messages"] if m["role"] == "assistant"), None
                )
                if assistant_content is None:
                    continue
                try:
                    manifest_data = json.loads(assistant_content)
                except Exception:
                    fail_count += 1
                    continue
            else:
                manifest_data = data

            result = evaluate(manifest_data)
            scores.append(result.score)
            if result.passed:
                pass_count += 1
            else:
                fail_count += 1

            if verbose and not result.passed:
                print(f"Line {i+1} FAIL:\n{result.summary()}\n")

    if not scores:
        return {"error": "No valid examples found"}

    return {
        "total": len(scores),
        "pass": pass_count,
        "fail": fail_count,
        "pass_rate": round(pass_count / len(scores), 3),
        "mean_score": round(sum(scores) / len(scores), 4),
        "min_score": round(min(scores), 4),
        "max_score": round(max(scores), 4),
    }


if __name__ == "__main__":
    import argparse, json

    parser = argparse.ArgumentParser(description="Evaluate scene manifest quality")
    parser.add_argument("path", nargs="?", help="JSONL file to evaluate (or stdin manifest JSON)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.path:
        stats = evaluate_file(args.path, verbose=args.verbose)
        print(json.dumps(stats, indent=2))
    else:
        # Read single manifest from stdin
        data = json.load(sys.stdin)
        result = evaluate(data)
        print(result.summary())
