# Story Director Rules

Extracted from Creator Rant masterclass (13 weight=5 lessons). These are FIXED RULES, not training examples — append to the system prompt or use as a reference doc when scoring outputs.

---

## 1. Story craft

### Where ideas come from
- Personal experiences (most reliable source)
- Reddit (especially r/prorevenge, r/pettyrevenge, r/AmITheAsshole, magnet-fishing, found-something subs)
- Trending news stories (animate them — works best when story itself is already viral)
- Trending videos online — don't copy the story, copy the *premise* and rewrite
- Things everyone collectively hates (rage-bait works — drives comment volume)
- Stuff you just make up (most of it is fiction, don't apologize)

### Hook construction
- Hook must promise that *something specific is about to happen*
- "About to get robbed" / "about to get arrested" / "about to lose everything" — these tell the viewer to stick around
- Pair the threat with a contradiction: `"X is about to happen, but Y has a plan"` — viewer must stay to see the plan
- Weird premises also work as hooks: "He glued his iPhone to the ground" — viewer needs the explanation
- Test the hook by reading it aloud — if you can feel the next line coming naturally, it works

### But/therefore storytelling
- Never "and then... and then... and then" — that's a list, not a story
- Use "but" and "therefore" between beats — each beat changes the situation
- Pattern: setup BUT obstacle THEREFORE response BUT twist THEREFORE payoff
- Every "but" promises something — viewer stays to see the payoff

### Holding back the twist
- The twist line goes at the very end
- Never reveal the mechanism early — let the viewer assemble it
- Use phrasing that lets viewers re-watch and notice setup they missed
- "Turns out this was not her first robbery" > "She had a decoy phone"
- Clarity is better than clever — but a little clever drives comments (people arguing in replies = engagement signal)

### Line writing rules
- Read every line out loud before keeping it
- Repetition of sentence structure builds rhythm: "She reached in her purse, pulled out her phone, hid it under her leg"
- Cut filler words ruthlessly — every word must earn its place
- Don't state what the visual already shows
- Write long first, then compress — final version should be the shortest possible cut
- 5th-grade reading level or below

### Length targets
- 28–34 seconds is the sweet spot
- Avoid 20s (too short to build) and 40s (too long to retain)
- End IMMEDIATELY after the payoff — never let it breathe

---

## 2. Pacing & timing

### Cut all dead air
- Any pause longer than ~0.3s before the next line — cut it
- If a head-turn or animation has too much hold time, speed it up (200–400% if no mouth visible)
- Silences kill retention more than fast cuts ever will

### J-cuts (audio leads video)
- Start the next line's audio under the previous clip
- Switch the visual on the *beat* of the next word, not before it
- Especially powerful when transitioning between camera angles

### Music timing
- Music hits should land on the visual cuts
- If the music's hit is off, move the cut — never the music's downbeat
- Cut music off the moment the payoff lands (don't fade)

### Pacing pass workflow
1. Watch through once, mark every spot that drags
2. Cut the drag without mercy
3. Watch again — if anything still feels slow, cut more
4. Re-time J-cuts to land on music hits

---

## 3. Visual production (Blender)

### Eye line
- Subject's eyes should sit at 75% up the frame (not center)
- Camera height matters more than camera distance

### Camera moves
- Use keyframes — start position, intermediate, end
- For dramatic emphasis: zoom in on the subject as they speak
- For reveals: pan/rotate around the character to expose what's behind them
- Long camera moves should be fast — slow camera = boring

### Environment building
- Use BlenderKit assets — never model from scratch unless required
- Bus / road / buildings / sky — all BlenderKit
- Avoid photo-scan assets for foreground (300K+ polys tank render time)
- Background buildings can be ChatGPT-generated PNGs on flat planes
- Reuse environments across multiple shorts

### Lighting
- Use HDRI for ambient light (Blenderkit sunny/night presets)
- Set render → film → transparent so HDRI doesn't show as background
- Add manual sky as image plane behind scene
- For dark areas: emission shader at low strength on background planes

### Character rigging
- Parent props (gun, phone) to hand bones using "child of" constraint
- Don't rig from scratch — BlenderKit has pre-rigged characters

---

## 4. Audio production

### Voiceover normalization
- Normalize peak to 0 dB
- Then lower gain to -0.1 dB to prevent clipping
- Apply to every clip individually

### Sound effects (use Quiver plugin in Premiere)
- Whoosh on every camera move
- Gasp + gunshot for tension moments — layer multiple gasps
- Phone rings, dings for accents
- Fart sounds for engagement bait (drives comments)

### Music selection
- Use chorus of song, not verse — choruses hit harder
- Pull from Epidemic Sound or similar royalty-free library
- One music track per short — don't switch mid-video

---

## 5. Captions & export

### Caption settings
- Max 15 characters per line
- Min 1.5 seconds duration
- Single line only — never multi-line
- Position: 300px below center (above shorts UI buttons)
- Font: ~115pt
- Drop shadow + stroke (Excalibur presets)

### Caption styling
- First 1–3 words of hook as single-word captions in red — drives attention
- Standard captions in white
- Remove all punctuation (transcription tools get it wrong, inconsistent)
- Move caption transitions to align with cuts

### Engagement bait visuals
- Red circle over an object → "what is that?" comments
- Arrows pointing at characters with "ding" sound
- Stupid-looking arrows fit stupid-looking shorts

### Thumbnail
- Pick a frame with exaggerated expression (big head, wide eyes)
- Red circle highlighting an object (gun, phone, character) — increases curiosity
- Eventually move to custom thumbnails for shorts that get featured

### Upload sequence
1. Export to MP4
2. Transfer to phone (Google Drive)
3. Upload via YouTube mobile app
4. Title: question form or how-to ("How to outsmart a thief")
5. Link to previous short in "related video" field — chains traffic
6. Cross-post to Instagram and TikTok

---

## 6. Hard rules (do not violate)

- Hook lands in 1.5–3 seconds
- Foreshadow is 2 lines max, under 3 seconds total
- 5th-grade reading level
- End immediately after payoff
- No "and then" — use but/therefore
- One story, one premise, one payoff
- 28–34 seconds total runtime
- Custom thumbnail with red-circle highlight
- Link previous short for chain retention
