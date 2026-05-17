"""
Benchmark few-shot prompting — tests how well Claude outputs valid JSON
scene manifests using only the system prompt + few-shot examples.

Usage:
  python evaluators/benchmark_prompting.py --count 50 --model claude-haiku-4-5-20251001
  python evaluators/benchmark_prompting.py --count 50 --model claude-sonnet-4-5
"""

import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from schemas.scene_manifest import validate_json_string
from evaluators.story_evaluator import evaluate
from prompts.story_director import build_prompt
from synthetic_data.generate import STORY_PROMPTS, tokens_to_cost

TEST_PROMPTS = [
    "A man finds his wallet stolen but the thief left something behind",
    "A kid accidentally orders 1000 pizzas instead of 1",
    "A woman realizes mid-flight she has the wrong passport",
    "A janitor discovers a secret room behind a wall at work",
    "A street musician plays a song only one person recognizes",
    "A couple argues over directions and ends up somewhere amazing",
    "A dog walker loses all 6 dogs at once in the park",
    "A man buys a lottery ticket as a joke and wins",
    "A chef serves the wrong dish to a food critic and it goes viral",
    "A nurse recognizes her patient from a news story about a heist",
    "A boy finds his grandfather's old phone still has messages on it",
    "A rideshare driver realizes his passenger is his old boss",
    "A woman's smart speaker starts answering questions she never asked",
    "A man pretends to be a doctor at a party and has to deliver a baby",
    "A package thief steals a box that was meant to be returned",
    "A teacher catches a student cheating but the answer was correct",
    "A security guard falls asleep and wakes up locked inside the mall",
    "A man proposes at a restaurant but the wrong table cheers",
    "A hiker finds a trail camera pointed at his campsite",
    "A woman wins a contest she never entered",
]


def run_benchmark(model: str, count: int, api_key: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    prompts = (TEST_PROMPTS * ((count // len(TEST_PROMPTS)) + 1))[:count]

    results = []
    total_in_tok = 0
    total_out_tok = 0
    total_cost = 0.0

    print(f"Model: {model}")
    print(f"Prompts: {count}")
    print("-" * 60)

    for i, prompt in enumerate(prompts):
        messages = build_prompt(prompt, include_few_shot=True)
        system = next(m["content"] for m in messages if m["role"] == "system")
        convo = [m for m in messages if m["role"] != "system"]

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1200,
                system=system,
                messages=convo,
            )
            content = response.content[0].text.strip()
            in_tok = response.usage.input_tokens
            out_tok = response.usage.output_tokens
        except Exception as e:
            results.append({"prompt": prompt, "valid_json": False, "schema_valid": False, "score": 0.0, "error": str(e)})
            print(f"  [{i+1}/{count}] ERROR: {e}")
            continue

        total_in_tok += in_tok
        total_out_tok += out_tok
        call_cost = tokens_to_cost(in_tok, out_tok)
        total_cost += call_cost

        # Strip markdown fences
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        # Check JSON validity
        try:
            data = json.loads(content)
            valid_json = True
        except Exception:
            valid_json = False
            data = None

        # Check schema validity
        if valid_json:
            manifest, err = validate_json_string(json.dumps(data))
            schema_valid = err is None
        else:
            schema_valid = False

        # Score with evaluator
        if schema_valid:
            eval_result = evaluate(data)
            score = eval_result.score
            passed = eval_result.passed
        else:
            score = 0.0
            passed = False

        results.append({
            "prompt": prompt,
            "valid_json": valid_json,
            "schema_valid": schema_valid,
            "score": score,
            "passed": passed,
            "cost": call_cost,
        })

        status = "PASS" if passed else ("JSON_OK" if valid_json else "FAIL")
        print(f"  [{i+1}/{count}] {status} score={score:.2f} cost=${call_cost:.4f} | {prompt[:50]}")

    # Aggregate
    n = len(results)
    valid_json_rate  = sum(1 for r in results if r.get("valid_json"))  / n
    schema_rate      = sum(1 for r in results if r.get("schema_valid")) / n
    pass_rate        = sum(1 for r in results if r.get("passed"))       / n
    mean_score       = sum(r.get("score", 0) for r in results) / n

    summary = {
        "model": model,
        "total_prompts": n,
        "valid_json_rate":  round(valid_json_rate,  3),
        "schema_valid_rate": round(schema_rate,     3),
        "evaluator_pass_rate": round(pass_rate,     3),
        "mean_score":        round(mean_score,      4),
        "total_cost_usd":    round(total_cost,      4),
        "total_input_tokens":  total_in_tok,
        "total_output_tokens": total_out_tok,
    }
    return summary, results


def main():
    parser = argparse.ArgumentParser(description="Benchmark Claude few-shot JSON manifest generation")
    parser.add_argument("--count",  type=int, default=20,  help="Number of prompts to test")
    parser.add_argument("--model",  type=str, default="claude-haiku-4-5-20251001")
    parser.add_argument("--output", type=str, default=None, help="Save full results to JSONL")
    args = parser.parse_args()

    import os, json as _json
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            cfg = _json.load(open(Path(__file__).parent.parent / ".claude/settings.local.json"))
            api_key = cfg["env"]["ANTHROPIC_API_KEY"]
        except Exception:
            print("Set ANTHROPIC_API_KEY or add it to .claude/settings.local.json")
            sys.exit(1)

    summary, results = run_benchmark(args.model, args.count, api_key)

    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k:<25} {v}")

    if args.output:
        with open(args.output, "w") as f:
            for r in results:
                f.write(_json.dumps(r) + "\n")
        print(f"\nFull results saved to {args.output}")


if __name__ == "__main__":
    main()
