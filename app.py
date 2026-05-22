"""
Viral Story Analyzer — Streamlit Web App
=========================================
Paste a YouTube Short URL  →  see why it went viral from comment reactions.
Paste a story idea          →  get a viral score, narration draft + pixel art plan.

Run:
    streamlit run app.py
"""

import os, json
import streamlit as st
from viral_analyzer import (
    extract_video_id,
    get_video_metadata,
    get_transcript,
    get_comments,
    analyze_url,
    analyze_idea,
    format_report,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Viral Story Analyzer",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ Viral Story Analyzer")
st.caption("Decode why stories go viral · Score your ideas · Draft pixel art narration")

# ── API key ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔑 Config")
    api_key = st.text_input(
        "Google API Key",
        value=os.getenv("GOOGLE_API_KEY", ""),
        type="password",
        help="Get one free at https://aistudio.google.com/app/apikey",
    )
    st.markdown("---")
    st.markdown("**Mode guide**")
    st.markdown("🎬 **YouTube URL** — fetches transcript + top comments, then decodes WHY it went viral")
    st.markdown("💡 **Story idea** — predicts viral score, drafts narration, plans pixel art")
    st.markdown("---")
    st.markdown("**Examples**")
    st.code("https://youtube.com/shorts/raRr8LI0MhU")
    st.markdown("or just describe your idea:")
    st.code("Two guys at drive-through. Guy 2 honks\nand flips Guy 1. Guy 1 gets to the\nwindow, pays for his OWN food... then\ntakes Guy 2's order too. Guy 2 has to\ndrive back around and reorder.")

# ── Input ─────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    user_input = st.text_area(
        "YouTube Short URL  **or**  story description",
        height=120,
        placeholder=(
            "Paste a YouTube Shorts URL...\n"
            "— OR —\n"
            "Describe your story idea here (the drive-through revenge, the gym stare-down, etc.)"
        ),
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    analyze_btn = st.button("⚡ Analyze", type="primary", use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Uses Gemini 1.5 Flash\n(free tier ~1500 req/day)")

# ── Run ───────────────────────────────────────────────────────────────────────
if analyze_btn:
    if not user_input.strip():
        st.warning("Paste a YouTube URL or story idea first.")
        st.stop()
    if not api_key:
        st.error("Add your Google API key in the sidebar.")
        st.stop()

    is_url = any(x in user_input for x in ["youtube.com", "youtu.be", "shorts/"])

    with st.spinner("🔍 Fetching data & analyzing..."):
        try:
            if is_url:
                video_id = extract_video_id(user_input.strip())
                metadata, analysis = analyze_url(video_id, api_key)
            else:
                metadata = None
                analysis = analyze_idea(user_input.strip(), api_key)
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            st.stop()

    # ── Results layout ────────────────────────────────────────────────────────
    st.markdown("---")

    # Header
    if metadata and metadata.get("title"):
        st.subheader(f"📊 {metadata['title']}")
        mcols = st.columns(3)
        mcols[0].metric("Views",    f"{metadata.get('views',0):,}")
        mcols[1].metric("Duration", f"{metadata.get('duration',0)}s")
        mcols[2].metric("Channel",  metadata.get("channel","—"))
    else:
        st.subheader("📊 Story Idea Analysis")

    st.markdown("---")

    # Viral score — hero section
    sd = analysis.get("viral_score", {})
    score = sd.get("score", 0)
    max_s = sd.get("max", 10)
    verdict = sd.get("verdict", "")

    score_col, bar_col = st.columns([1, 3])
    score_col.metric("⚡ Viral Score", f"{score} / {max_s}")
    with bar_col:
        st.progress(score / max_s)
        st.caption(verdict)

    # Score breakdown
    if "breakdown" in sd:
        bd = sd["breakdown"]
        bcols = st.columns(len(bd))
        for col, (k, v) in zip(bcols, bd.items()):
            col.metric(k.replace("_"," ").title(), f"{v}/10")

    st.markdown("---")

    # Two-column layout for main content
    left, right = st.columns(2)

    with left:
        # Viral DNA
        dna = analysis.get("viral_dna", {})
        st.markdown("### 🧬 Viral DNA")
        st.markdown(f"**Emotion:** {dna.get('core_emotion','—')}")
        st.markdown(f"**Archetype:** {dna.get('archetype','—')}")
        st.markdown(f"**Magic moment:** {dna.get('magic_moment','—')}")
        st.markdown(f"**Rewatch trigger:** {dna.get('rewatch_trigger','—')}")
        st.markdown(f"**Shareability:** {dna.get('shareability','—')}")

        # Story beats
        st.markdown("### 🎬 Story Beats")
        beats = analysis.get("story_beats", {})
        order  = ["hook","foreshadow","obstacle","amplifier","twist","payoff"]
        icons  = {"hook":"🪝","foreshadow":"👁️","obstacle":"⛔","amplifier":"🔥","twist":"🌀","payoff":"✅"}
        colors = {"hook":"#FF6B6B","foreshadow":"#FFD93D","obstacle":"#6BCB77",
                  "amplifier":"#FF6B6B","twist":"#4D96FF","payoff":"#6BCB77"}
        for beat in order:
            if beat in beats:
                icon = icons.get(beat,"•")
                col = colors.get(beat,"#999")
                st.markdown(
                    f'<div style="border-left:3px solid {col};padding:4px 10px;margin:4px 0">'
                    f'<b>{icon} {beat.upper()}</b><br>{beats[beat]}</div>',
                    unsafe_allow_html=True,
                )

        # Pixel art
        pix = analysis.get("pixel_art_adaptation", {})
        if pix:
            st.markdown("### 🎮 Pixel Art Adaptation")
            st.markdown(f"**Title:** {pix.get('suggested_title','—')}")
            feasibility = pix.get("feasibility","—")
            f_color = {"easy":"green","medium":"orange","hard":"red"}.get(feasibility,"grey")
            st.markdown(
                f"**Feasibility:** <span style='color:{f_color};font-weight:bold'>{feasibility.upper()}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Duration:** ~{pix.get('estimated_duration_sec',30)}s")
            st.markdown("**Key scenes to animate:**")
            for vm in pix.get("visual_moments",[]):
                st.markdown(f"- 🎬 {vm}")
            hint = pix.get("scene_manifest_hint") or pix.get("adaptation_notes","")
            if hint:
                st.info(f"📝 {hint}")

    with right:
        # Comment analysis (URL mode)
        ca = analysis.get("comment_analysis", {})
        if ca:
            st.markdown("### 💬 Comment Analysis")
            st.markdown(f"**Dominant reaction:** {ca.get('dominant_reaction','—')}")
            st.markdown(f"**Top quoted moment:** {ca.get('top_quoted_moment','—')}")
            st.markdown("**Comment patterns:**")
            for arch in ca.get("comment_archetypes",[]):
                st.markdown(f"- {arch}")

            ss = ca.get("sentiment_split", {})
            if ss:
                st.markdown("**Sentiment breakdown:**")
                sent_cols = st.columns(4)
                sent_cols[0].metric("❤️ Love it",    f"{ss.get('love_it',0):.0%}")
                sent_cols[1].metric("😄 Entertained",f"{ss.get('entertained',0):.0%}")
                sent_cols[2].metric("😐 Neutral",    f"{ss.get('neutral',0):.0%}")
                sent_cols[3].metric("👎 Disagree",   f"{ss.get('disagree',0):.0%}")

            best = ca.get("best_comment","")
            if best:
                st.markdown("**⭐ Best comment:**")
                st.success(f'"{best}"')

        # Predicted comments (idea mode)
        pc = analysis.get("predicted_comment_reactions",[])
        if pc:
            st.markdown("### 💬 Predicted Comment Reactions")
            for p in pc:
                st.markdown(f"- {p}")

        # Improvements (idea mode)
        imps = analysis.get("improvements",[])
        if imps:
            st.markdown("### 🚀 Make It More Viral")
            for i, imp in enumerate(imps, 1):
                st.markdown(f"**{i}.** {imp}")

        # Narration draft (idea mode)
        nd = analysis.get("narration_draft", {})
        if nd:
            st.markdown("### ✍️ Narration Draft")
            st.markdown(
                f'<div style="background:#1e1e2e;border-radius:8px;padding:16px;'
                f'font-family:monospace;line-height:1.8">'
                f'<span style="color:#ff6b6b">🪝 HOOK</span>    "{nd.get("hook_line","")}"<br>'
                + "".join(
                    f'<span style="color:#ffd93d">👁️ FORE</span>    "{line}"<br>'
                    for line in nd.get("foreshadow_lines",[])
                )
                + "".join(
                    f'<span style="color:#aaa">        </span>"{line}"<br>'
                    for line in nd.get("body_lines",[])
                )
                + f'<span style="color:#6bcb77">✅ PAYOFF</span>  "{nd.get("payoff_line","")}"'
                + "</div>",
                unsafe_allow_html=True,
            )

        # Training value (URL mode)
        tv = analysis.get("training_value", {})
        if tv:
            st.markdown("### 📚 Training Value")
            worth = tv.get("worth_adding", False)
            st.markdown(
                f"**Add to dataset:** {'✅ YES' if worth else '❌ NO'}  "
                f"**Beat:** {tv.get('beat_demonstrated','—')}"
            )
            st.info(f"💡 {tv.get('one_sentence_lesson','')}")

    # ── Raw JSON expander ──────────────────────────────────────────────────────
    with st.expander("🗂 Full JSON output"):
        st.json({"metadata": metadata, "analysis": analysis})

    # ── Download ───────────────────────────────────────────────────────────────
    st.download_button(
        "⬇️ Download JSON",
        data=json.dumps({"metadata": metadata, "analysis": analysis}, indent=2),
        file_name="viral_analysis.json",
        mime="application/json",
    )
