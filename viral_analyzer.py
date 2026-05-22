"""
Viral Story Analyzer
====================
Two modes:
  1. YouTube URL  → fetches transcript + comments → Gemini decodes WHY it went viral
  2. Story idea   → Gemini predicts viral potential, scores it, drafts narration

Usage:
  python viral_analyzer.py "https://youtube.com/shorts/raRr8LI0MhU"
  python viral_analyzer.py "Two guys at drive-through. Guy 2 honked and flipped guy 1..."

Output: rich terminal report + viral_analysis_output.json
"""

import os, json, re, sys, subprocess
from pathlib import Path
from typing import Optional


# ── Auto-install deps ────────────────────────────────────────────────────────
def _pip(*packages):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *packages])

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    _pip("youtube-transcript-api")
    from youtube_transcript_api import YouTubeTranscriptApi

try:
    import yt_dlp
except ImportError:
    _pip("yt-dlp")
    import yt_dlp

try:
    import google.generativeai as genai
except ImportError:
    _pip("google-generativeai")
    import google.generativeai as genai


MAX_COMMENTS = 150  # top N comments to fetch and analyze


# ── Helpers ──────────────────────────────────────────────────────────────────

def extract_video_id(url: str) -> str:
    for pat in [
        r"shorts/([a-zA-Z0-9_-]{11})",
        r"v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def get_transcript(video_id: str) -> Optional[str]:
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return " ".join(chunk["text"] for chunk in transcript)
    except Exception as e:
        print(f"  ⚠️  Transcript unavailable: {e}")
        return None


def get_video_metadata(video_id: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            return {
                "title":    info.get("title", ""),
                "views":    info.get("view_count", 0),
                "likes":    info.get("like_count", 0),
                "duration": info.get("duration", 0),
                "channel":  info.get("uploader", ""),
            }
        except Exception as e:
            print(f"  ⚠️  Metadata unavailable: {e}")
            return {}


def get_comments(video_id: str, max_comments: int = MAX_COMMENTS) -> list:
    print(f"  💬 Fetching top {max_comments} comments...")
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "getcomments": max_comments,
        "extractor_args": {
            "youtube": {
                "comment_sort":  ["top"],
                "max_comments":  [str(max_comments)],
            }
        },
    }
    comments = []
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}", download=False
            )
            for c in (info.get("comments") or [])[:max_comments]:
                comments.append({
                    "text":    c.get("text", ""),
                    "likes":   c.get("like_count", 0),
                    "replies": c.get("reply_count", 0),
                })
        except Exception as e:
            print(f"  ⚠️  Comment fetch failed: {e}")

    comments.sort(key=lambda x: x["likes"], reverse=True)
    return comments


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


# ── Prompts ──────────────────────────────────────────────────────────────────

URL_ANALYSIS_PROMPT = """\
You are a viral short-form video analyst. Decode exactly WHY this video went viral
from its transcript and comment reactions.

VIDEO METADATA
--------------
Title:    {title}
Views:    {views:,}
Duration: {duration}s
Channel:  {channel}

TRANSCRIPT
----------
{transcript}

TOP COMMENTS  ({comment_count} fetched, sorted by likes)
------------
{comments_text}

──────────────────────────────────────────────────────────────────────────────
OUTPUT a single JSON object with EXACTLY this shape (no markdown, no extra keys):

{{
  "story_beats": {{
    "hook":       "Opening moment — what happens in first 1-3 seconds",
    "foreshadow": "2-line tease of what's coming (under 3 sec)",
    "obstacle":   "The core conflict / tension",
    "amplifier":  "What raises the stakes / makes it worse",
    "twist":      "The unexpected turn or reveal",
    "payoff":     "The satisfying ending"
  }},
  "viral_dna": {{
    "core_emotion":    "Single dominant emotion (e.g. 'petty justice', 'satisfying karma')",
    "archetype":       "Story archetype (e.g. 'Karma Boomerang', 'Unexpected Hero')",
    "magic_moment":    "The exact beat that made this explode — one sentence",
    "rewatch_trigger": "Why someone watches again",
    "shareability":    "Complete: 'I shared this because...'"
  }},
  "comment_analysis": {{
    "dominant_reaction":    "Most common emotion in comments",
    "top_quoted_moment":    "Which specific moment comments reference most",
    "comment_archetypes":   [
      "Pattern 1 with rough percentage (e.g. '45% — celebrating guy 1\\'s move')",
      "Pattern 2",
      "Pattern 3"
    ],
    "sentiment_split": {{
      "love_it":    0.0,
      "entertained":0.0,
      "neutral":    0.0,
      "disagree":   0.0
    }},
    "best_comment": "Most insightful or funniest comment verbatim"
  }},
  "viral_score": {{
    "score": 0,
    "max":   10,
    "breakdown": {{
      "hook_strength":    0,
      "twist_quality":    0,
      "emotional_payoff": 0,
      "comment_magnet":   0,
      "rewatch_value":    0
    }},
    "verdict": "One-sentence why this did/didn't go viral"
  }},
  "pixel_art_adaptation": {{
    "feasibility":         "easy | medium | hard",
    "suggested_title":     "Snappy pixel art version title",
    "visual_moments":      ["Key scene 1", "Key scene 2", "Key scene 3"],
    "estimated_duration_sec": 30,
    "adaptation_notes":    "Any notes on adapting for pixel art"
  }},
  "training_value": {{
    "worth_adding":            true,
    "beat_demonstrated":       "Which viral beat structure this exemplifies",
    "one_sentence_lesson":     "Lesson for the Story Director LLM"
  }}
}}"""

IDEA_ANALYSIS_PROMPT = """\
You are a viral short-form video analyst. A creator has a story idea they want
to turn into a YouTube Short / pixel art animation. Analyze it and predict viral potential.

STORY IDEA
----------
{story}

──────────────────────────────────────────────────────────────────────────────
OUTPUT a single JSON object with EXACTLY this shape (no markdown, no extra keys):

{{
  "story_beats": {{
    "hook":       "Suggested opening hook (1-3 seconds)",
    "foreshadow": "2-line foreshadow (under 3 sec)",
    "obstacle":   "Core conflict",
    "amplifier":  "What raises the stakes",
    "twist":      "The turn",
    "payoff":     "The payoff"
  }},
  "viral_dna": {{
    "core_emotion":    "Primary emotion this triggers",
    "archetype":       "Story archetype",
    "magic_moment":    "The single moment that would make this blow up",
    "rewatch_trigger": "Why someone rewatches",
    "shareability":    "Why someone shares this"
  }},
  "predicted_comment_reactions": [
    "Predicted reaction pattern 1",
    "Predicted reaction pattern 2",
    "Predicted reaction pattern 3"
  ],
  "viral_score": {{
    "score": 0,
    "max":   10,
    "breakdown": {{
      "hook_strength":    0,
      "twist_quality":    0,
      "emotional_payoff": 0,
      "relatability":     0,
      "rewatch_value":    0
    }},
    "verdict": "One-sentence viral potential verdict"
  }},
  "improvements": [
    "Suggestion 1 to make it more viral",
    "Suggestion 2",
    "Suggestion 3"
  ],
  "pixel_art_adaptation": {{
    "feasibility":         "easy | medium | hard",
    "suggested_title":     "Snappy title",
    "visual_moments":      ["Key scene 1", "Key scene 2", "Key scene 3"],
    "estimated_duration_sec": 30,
    "scene_manifest_hint": "Brief hint for the JSON scene manifest structure"
  }},
  "narration_draft": {{
    "hook_line":       "First line — the hook",
    "foreshadow_lines":["foreshadow line 1", "foreshadow line 2"],
    "body_lines":      ["body line 1", "body line 2", "body line 3"],
    "payoff_line":     "Final line — the payoff"
  }}
}}"""


# ── LLM calls ────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str, api_key: str) -> dict:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content(prompt)
    return json.loads(_strip_fences(response.text))


def analyze_url(video_id: str, api_key: str) -> tuple[dict, dict]:
    """Fetch + analyze a YouTube video. Returns (metadata, analysis)."""
    print("  📊 Fetching metadata...")
    metadata = get_video_metadata(video_id)
    if metadata.get("title"):
        print(f"     Title:  {metadata['title']}")
        print(f"     Views:  {metadata['views']:,}")

    print("  📝 Fetching transcript...")
    transcript = get_transcript(video_id)
    if transcript:
        print(f"     {len(transcript.split())} words")

    comments = get_comments(video_id)
    print(f"     Got {len(comments)} comments")

    print("  🤖 Analyzing with Gemini...")
    comments_text = "\n".join(
        f"[{i+1}] ({c['likes']} 👍) {c['text']}"
        for i, c in enumerate(comments[:60])
    )
    prompt = URL_ANALYSIS_PROMPT.format(
        title=metadata.get("title", "Unknown"),
        views=metadata.get("views", 0),
        duration=metadata.get("duration", 0),
        channel=metadata.get("channel", "Unknown"),
        transcript=transcript or "[Transcript unavailable]",
        comment_count=len(comments),
        comments_text=comments_text,
    )
    analysis = _call_gemini(prompt, api_key)
    return metadata, analysis


def analyze_idea(story: str, api_key: str) -> dict:
    """Analyze a raw story idea. Returns analysis."""
    print("  🤖 Analyzing story idea with Gemini...")
    prompt = IDEA_ANALYSIS_PROMPT.format(story=story)
    return _call_gemini(prompt, api_key)


# ── Report formatter ─────────────────────────────────────────────────────────

def _bar(score: int, max_score: int = 10) -> str:
    filled = max(0, min(score, max_score))
    return "█" * filled + "░" * (max_score - filled)


def format_report(analysis: dict, metadata: dict = None) -> str:
    L = []

    if metadata and metadata.get("title"):
        L.append(f"\n{'='*62}")
        L.append(f"  📊  {metadata['title']}")
        L.append(f"      {metadata.get('views',0):,} views · {metadata.get('duration',0)}s · {metadata.get('channel','')}")
        L.append(f"{'='*62}")
    else:
        L.append(f"\n{'='*62}")
        L.append("  📊  STORY IDEA ANALYSIS")
        L.append(f"{'='*62}")

    # Viral score
    sd = analysis.get("viral_score", {})
    score = sd.get("score", 0)
    L.append(f"\n⚡ VIRAL SCORE   {score}/{sd.get('max',10)}  [{_bar(score)}]")
    L.append(f"   {sd.get('verdict','')}")
    if "breakdown" in sd:
        for k, v in sd["breakdown"].items():
            label = k.replace("_", " ").title()
            L.append(f"   {label:22} {_bar(v, 10)} {v}/10")

    # Viral DNA
    dna = analysis.get("viral_dna", {})
    L.append("\n🧬 VIRAL DNA")
    L.append(f"   Emotion      {dna.get('core_emotion','—')}")
    L.append(f"   Archetype    {dna.get('archetype','—')}")
    L.append(f"   Magic moment {dna.get('magic_moment','—')}")
    L.append(f"   Rewatch      {dna.get('rewatch_trigger','—')}")
    L.append(f"   Shareability {dna.get('shareability','—')}")

    # Story beats
    beats = analysis.get("story_beats", {})
    L.append("\n🎬 STORY BEATS")
    order = ["hook","foreshadow","obstacle","amplifier","twist","payoff"]
    icons = {"hook":"🪝","foreshadow":"👁️ ","obstacle":"⛔","amplifier":"🔥","twist":"🌀","payoff":"✅"}
    for beat in order:
        if beat in beats:
            icon = icons.get(beat, "•")
            L.append(f"   {icon} {beat.upper():11} {beats[beat]}")

    # Comment analysis (URL mode)
    ca = analysis.get("comment_analysis", {})
    if ca:
        L.append("\n💬 COMMENT ANALYSIS")
        L.append(f"   Dominant reaction  {ca.get('dominant_reaction','—')}")
        L.append(f"   Top quoted moment  {ca.get('top_quoted_moment','—')}")
        for arch in ca.get("comment_archetypes", []):
            L.append(f"   • {arch}")
        ss = ca.get("sentiment_split", {})
        if ss:
            L.append(f"\n   Sentiment: ❤️ {ss.get('love_it',0):.0%} love · "
                     f"😄 {ss.get('entertained',0):.0%} entertained · "
                     f"😐 {ss.get('neutral',0):.0%} neutral · "
                     f"👎 {ss.get('disagree',0):.0%} disagree")
        best = ca.get("best_comment","")
        if best:
            L.append(f"\n   ⭐ Best comment: \"{best}\"")

    # Predicted comments (idea mode)
    pc = analysis.get("predicted_comment_reactions", [])
    if pc:
        L.append("\n💬 PREDICTED COMMENT REACTIONS")
        for p in pc:
            L.append(f"   • {p}")

    # Improvements (idea mode)
    imps = analysis.get("improvements", [])
    if imps:
        L.append("\n🚀 MAKE IT MORE VIRAL")
        for i, imp in enumerate(imps, 1):
            L.append(f"   {i}. {imp}")

    # Narration draft (idea mode)
    nd = analysis.get("narration_draft", {})
    if nd:
        L.append("\n✍️  NARRATION DRAFT")
        L.append(f"   🪝 HOOK     \"{nd.get('hook_line','')}\"")
        for line in nd.get("foreshadow_lines", []):
            L.append(f"   👁️  FORE     \"{line}\"")
        for line in nd.get("body_lines", []):
            L.append(f"           \"{line}\"")
        L.append(f"   ✅ PAYOFF   \"{nd.get('payoff_line','')}\"")

    # Pixel art
    pix = analysis.get("pixel_art_adaptation", {})
    if pix:
        L.append("\n🎮 PIXEL ART ADAPTATION")
        L.append(f"   Title        {pix.get('suggested_title','—')}")
        L.append(f"   Feasibility  {pix.get('feasibility','—')}")
        L.append(f"   Duration     ~{pix.get('estimated_duration_sec',30)}s")
        for vm in pix.get("visual_moments", []):
            L.append(f"   🎬 {vm}")
        hint = pix.get("scene_manifest_hint") or pix.get("adaptation_notes","")
        if hint:
            L.append(f"   📝 {hint}")

    # Training value (URL mode)
    tv = analysis.get("training_value", {})
    if tv:
        L.append("\n📚 TRAINING VALUE")
        L.append(f"   Worth adding   {'✅ YES' if tv.get('worth_adding') else '❌ NO'}")
        L.append(f"   Beat shown     {tv.get('beat_demonstrated','—')}")
        L.append(f"   Lesson         {tv.get('one_sentence_lesson','—')}")

    L.append("")
    return "\n".join(L)


# ── Main ─────────────────────────────────────────────────────────────────────

def run(
    input_str: str,
    api_key: str = None,
    save_json: bool = True,
    output_path: str = "viral_analysis_output.json",
) -> dict:
    """
    Analyze a YouTube URL or a story idea.

    Parameters
    ----------
    input_str  : YouTube URL  OR  plain-text story description
    api_key    : Google API key (falls back to GOOGLE_API_KEY env var)
    save_json  : write full JSON result to output_path
    """
    api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError(
            "A Google API key is required.\n"
            "Set the GOOGLE_API_KEY environment variable or pass api_key=..."
        )

    is_url = any(x in input_str for x in ["youtube.com", "youtu.be", "shorts/"])

    if is_url:
        video_id = extract_video_id(input_str)
        print(f"\n🎬  YouTube Short — video ID: {video_id}")
        metadata, analysis = analyze_url(video_id, api_key)
    else:
        print("\n💡  Story idea mode")
        metadata = None
        analysis = analyze_idea(input_str, api_key)

    report = format_report(analysis, metadata)
    print(report)

    if save_json:
        out = Path(output_path)
        with open(out, "w") as f:
            json.dump({"metadata": metadata, "analysis": analysis}, f, indent=2)
        print(f"💾  Full JSON saved → {out}\n")

    return analysis


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Viral Story Analyzer — URL or story idea",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "input",
        help=(
            "YouTube Short URL  — fetches transcript + comments\n"
            "Story description  — predicts viral potential"
        ),
    )
    parser.add_argument("--api-key", help="Google API key (overrides GOOGLE_API_KEY)")
    parser.add_argument("--output", default="viral_analysis_output.json",
                        help="Output JSON path (default: viral_analysis_output.json)")
    parser.add_argument("--no-save", action="store_true", help="Skip saving JSON")
    args = parser.parse_args()

    run(
        args.input,
        api_key=args.api_key,
        save_json=not args.no_save,
        output_path=args.output,
    )
