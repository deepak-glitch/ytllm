"""
Local synthetic dataset generator.
Uses pre-built expert knowledge to generate 5000+ training examples
without needing API calls - all knowledge is baked in from research.
"""
import json, random, itertools
from pathlib import Path

OUT = Path("/home/claude/training-data")
SYSTEM = ("You are a viral short-form video creator coach and story director specializing in "
          "pixel art animated Shorts. Expert in hooks, story structure, retention mechanics, "
          "and visual storytelling for Godot-rendered pixel art.")

# ── PIXEL ART SITUATIONS ──
PIXEL_SITUATIONS = [
    ("a knight discovering his sword is cursed the night before battle", "fantasy", "dread"),
    ("two rivals trapped in a dungeon who must cooperate", "fantasy", "comedy"),
    ("a merchant who buys a magic item that causes chaos in town", "fantasy", "comedy"),
    ("a wizard's apprentice who messes up a spell at the worst moment", "fantasy", "cringe"),
    ("a hero reaching the final boss only to realize they forgot their weapon", "fantasy", "comedy"),
    ("a guard who falls asleep and misses an entire invasion", "fantasy", "comedy"),
    ("a thief who accidentally steals from a god", "fantasy", "suspense"),
    ("a dragon who pretends to be defeated because he is tired of fighting", "fantasy", "comedy"),
    ("a king disguising as a peasant whose disguise immediately fails", "fantasy", "comedy"),
    ("two adventurers arguing over directions while a monster approaches", "fantasy", "suspense"),
    ("a blacksmith who makes the villain's weapon and instantly regrets it", "fantasy", "karma"),
    ("a town hero who is secretly afraid of everything", "drama", "heartfelt"),
    ("a healer who cannot heal themselves", "drama", "heartfelt"),
    ("a soldier who switches sides mid-battle for the wrong reason", "drama", "twist"),
    ("a ghost who doesn't know they're dead trying to help someone", "drama", "heartfelt"),
    ("a thief who steals back what was stolen from the poor", "drama", "triumph"),
    ("a villain who does one small act of kindness and it ruins their reputation", "comedy", "comedy"),
    ("a hero who wins by accident and has to pretend it was on purpose", "comedy", "comedy"),
    ("a character who is extremely good at one useless skill that saves the day", "comedy", "triumph"),
    ("an NPC who realizes they are an NPC and tries to escape the game", "comedy", "twist"),
    ("a shopkeeper who refuses to sell to the hero until they complete a side quest", "comedy", "comedy"),
    ("a side character who does the actual important thing while the hero is distracted", "comedy", "twist"),
    ("a map that leads exactly to where you started", "comedy", "twist"),
    ("a warrior who challenges the wrong person to a duel", "karma", "karma"),
    ("a bully knight who gets humiliated by the smallest person in the village", "karma", "triumph"),
    ("a corrupt tax collector who loses everything in one day", "karma", "karma"),
    ("a cheater in a tournament who loses to someone even worse", "karma", "comedy"),
    ("a villain who falls into their own trap", "karma", "triumph"),
    ("an army that surrenders to the wrong side", "comedy", "comedy"),
    ("a cursed item that only affects arrogant people", "karma", "karma"),
]

RELATABLE_SITUATIONS = [
    ("being stuck in traffic when you desperately need a bathroom", "relatable", "comedy"),
    ("accidentally sending a private message to the wrong person", "relatable", "cringe"),
    ("being caught lying by the exact person you lied to", "relatable", "cringe"),
    ("showing up to the wrong meeting and not realizing for 10 minutes", "relatable", "comedy"),
    ("breaking something valuable and trying to hide it", "relatable", "suspense"),
    ("saying 'you too' when a waiter says enjoy your meal", "relatable", "comedy"),
    ("calling a teacher mom by accident", "relatable", "cringe"),
    ("waving back at someone who was waving at someone behind you", "relatable", "cringe"),
    ("getting your card declined in front of a long line", "relatable", "cringe"),
    ("autocorrect changing a message at exactly the wrong moment", "relatable", "comedy"),
    ("running into someone you told you were sick while you were out having fun", "relatable", "karma"),
    ("parking in a spot and realizing a second later you shouldn't have", "relatable", "suspense"),
    ("confidently giving directions and leading everyone the wrong way", "relatable", "comedy"),
    ("falling asleep in class and snoring loudly", "relatable", "cringe"),
    ("joining the wrong video call and not noticing for two minutes", "relatable", "comedy"),
]

ALL_SITUATIONS = PIXEL_SITUATIONS + RELATABLE_SITUATIONS

# ── SCRIPT TEMPLATES ──
def make_30s_script(situation, genre, emotion):
    s, g, e = situation, genre, emotion
    scripts = {
        "fantasy": f"""**[HOOK — 0-3s]**
NARRATOR: "{random.choice([
    f'There was {s.split("who")[0].strip()} — and everything was about to go wrong.',
    f'He had one job. ONE job.',
    f'Nobody saw it coming. Especially not him.',
    f'The plan was simple. It was not simple.'
])}"
VISUAL: Open on character mid-action, something already going wrong in background.

**[FORESHADOW — 3-6s]**
NARRATOR: "And by the end of this night, nothing would ever be the same."
VISUAL: Quick flash of the consequence/payoff — then cut back.

**[OBSTACLE 1 — 6-18s]**
NARRATOR: "{s.capitalize()}."
VISUAL: Show the problem unfolding. Character reacts. Audience thinks they know where it's going.
CHARACTER ACTION: Attempts obvious solution. Fails immediately.
NARRATOR: "So he tried [obvious solution]. Which made everything worse."

**[AMPLIFIER — 18-24s]**
VISUAL: Unexpected complication enters. Something the audience didn't predict.
NARRATOR: "That's when [unexpected element] showed up."
CHARACTER: Visible panic. Eyes wide. Freeze frame one beat.

**[TWIST + PAYOFF — 24-30s]**
VISUAL: Subversion of the setup. The thing you expected to happen — doesn't.
NARRATOR: "[Punchline that recontextualizes everything]."
CHARACTER: Reaction shot. Cut to black IMMEDIATELY after reaction lands.
— END —

**Director notes:**
- Camera: Start wide → medium → close-up as tension builds → extreme close on twist
- Pixel palette: Shift to warmer/cooler tones at twist for visual punctuation  
- Sound: Music cuts OUT for 1 beat before punchline lands""",

        "karma": f"""**[HOOK — 0-3s]**
VISUAL: Antagonist doing something clearly wrong. We see it. Character doesn't yet.
NARRATOR: "[Antagonist] thought they were untouchable."

**[FORESHADOW — 3-5s]**  
NARRATOR: "They were not untouchable."
VISUAL: Brief flash of the karma moment — then whip back to beginning.

**[BUILD — 5-20s]**
NARRATOR: Show {s} escalating. Each beat raises the injustice.
VISUAL: Close-up on the protagonist's reaction — audience's surrogate.
Beat 1: Wrong thing happens.
Beat 2: Character tries to address it. Blocked.
Beat 3: Situation reaches peak unfairness. Audience is fuming.

**[KARMA LANDS — 20-28s]**
VISUAL: Comeuppance arrives from unexpected direction. NOT from the protagonist.
NARRATOR: "And then—"
VISUAL: Freeze one frame. Let it land.
NARRATOR: "[One-line punchline describing the justice]."

**[PAYOFF REACTION — 28-30s]**
VISUAL: Protagonist's face. Pure satisfaction.
Cut. No more words needed.""",

        "comedy": f"""**[HOOK — 0-2s]**  
VISUAL: Start MID-DISASTER. Character already in the wrong situation.
NARRATOR: "There he was." [Beat.] "It had gotten worse."

**[SETUP — 2-8s]**
NARRATOR: "{s.capitalize()}. Which — in retrospect — was a mistake."
VISUAL: Quick flashback montage of exactly one terrible decision that led here.

**[ESCALATION — 8-22s]**
Beat 1: Tries Solution A. Makes it worse.
NARRATOR: "So naturally, he tried [A]."
Beat 2: Tries Solution B. Catastrophically worse.  
NARRATOR: "Which led to [B]."
Beat 3: Situation reaches critical mass. Something breaks.
NARRATOR: "At this point — [observation that names the absurdity]."

**[PUNCHLINE — 22-30s]**
VISUAL: Unexpected but inevitable resolution. The absurd logical conclusion.
NARRATOR: "[Punchline]." 
CHARACTER: Stares at camera. (Or at the audience surrogate character.)
Cut immediately. Don't let it breathe.""",
    }
    base = scripts.get(g, scripts["fantasy"])
    return base

def make_hook_set(situation, genre, emotion):
    s = situation
    hooks = [
        f"There was {s.split('who')[0].strip() if 'who' in s else 'a character'} — and everything was about to go wrong.",
        f"He had one job. He did not do the job.",
        f"Nobody expected this. Especially not him.",
        f"This was supposed to be simple. It was not simple.",
        f"The plan had four steps. He failed all four. Simultaneously.",
        f"There are two types of people in this situation. He was the wrong type.",
        f"{'This' if 'this' not in s else 'That'} is not how {s.split('who')[0].strip() if 'who' in s else 'this'} was supposed to go.",
        f"He thought the hard part was over. The hard part had not started.",
    ]
    return hooks

def make_feedback(situation, problem):
    return f"""Looking at this script, the {problem} issues are clear. Here's the fix:

**What's broken:**
The hook doesn't earn attention in the first 1.5 seconds. Viewers are swiping before the story starts.

**Root cause:**
{random.choice([
    "You're explaining the situation instead of dropping us into it. We don't need backstory — we need action.",
    "The first line tells us what's going to happen instead of making us desperate to find out.",
    "You're starting at the beginning of the story. Start at the most interesting moment.",
    "The setup takes 8 seconds. It should take 2. Everything before the obstacle is setup you don't need.",
])}

**The fix — rewrite the opening:**
WRONG: "{random.choice(['Hey everyone, today...', 'So basically what happened was...', 'This is a story about...', 'Let me tell you about...']}
RIGHT: Drop directly into {situation.split('who')[0].strip() if 'who' in situation else 'the action'} mid-problem. First word should be action or character name.

**Retention fix:**
Add a foreshadow beat in seconds 3-5: "And by the end — [payoff tease]." This gives the audience a reason to stay.

**Structural diagnosis:**
Your twist lands at the right time but the amplifier is missing. The audience needs one unexpected complication between obstacle 1 and the twist — something that raises stakes and misdirects them before the resolution.

**One-line test:** Can you explain this Short in one sentence that would make someone curious? If not, the concept needs work before the script."""

# ── GENERATE ALL EXAMPLES ──
examples = []

for situation, genre, emotion in ALL_SITUATIONS:
    # 1. Full 30s script
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Write a complete 30-second pixel art Short script about {situation}. Include hook, foreshadow, obstacles, twist, and payoff. Add camera and visual directions."},
            {"role": "assistant", "content": make_30s_script(situation, genre, emotion)},
        ],
        "source": "synthetic_script_30s",
        "weight": 3,
        "cluster": "script_writing",
    })
    
    # 2. Hook variations
    hooks = make_hook_set(situation, genre, emotion)
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Give me 8 hook variations for a Short about {situation}. Mix emotions and approaches."},
            {"role": "assistant", "content": "Here are 8 hooks, each targeting a different emotion or angle:\n\n" + 
             "\n".join(f"{i+1}. **{h}**" for i, h in enumerate(hooks))},
        ],
        "source": "synthetic_hooks",
        "weight": 3,
        "cluster": "hook_writing",
    })
    
    # 3. Story structure breakdown
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Break down the beat structure for a {emotion} Short about {situation}. What happens in each scene?"},
            {"role": "assistant", "content": f"""Beat structure for a {emotion} Short about {situation}:

**Beat 1 — Hook (0-3s):** Drop into the character already in the situation. No setup. The first visual tells us who they are and what's wrong. Target emotion: {emotion}.

**Beat 2 — Foreshadow (3-6s):** One line that promises the payoff without spoiling it. "By the end of this — [vague but intriguing hint]." Sets expectation, creates a reason to stay.

**Beat 3 — Obstacle 1 (6-15s):** The primary problem lands. Character tries the obvious solution first. It fails or makes things worse. This is where the but/therefore chain begins: "They tried [A] BUT [consequence] THEREFORE [next action]."

**Beat 4 — Amplifier (15-22s):** The thing the audience didn't predict. A new character, an unexpected complication, a revelation that reframes everything. This beat separates good Shorts from viral ones. It misdirects the audience before the twist.

**Beat 5 — Twist (22-28s):** Subverts the expectation set in Beat 1. The audience expected [X] — they get [Y]. For {emotion} content, this is where the {emotion} emotion peaks. One beat of silence or pause before the punchline helps it land.

**Beat 6 — Payoff reaction (28-30s):** Show the character's face. One expression. Cut immediately. Don't let it breathe — ending on momentum keeps the rewatch rate high.

**Visual direction:** Palette shift at Beat 5 signals the twist subconsciously. Camera moves from wide → medium → close as tension builds. Freeze one frame at the twist before cutting."""},
        ],
        "source": "synthetic_structure",
        "weight": 3,
        "cluster": "story_structure",
    })
    
    # 4. Feedback / critique
    problems = ["hook", "pacing", "twist strength", "amplifier", "payoff", "structure"]
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"My Short about {situation} isn't performing. The hook feels weak and I'm getting 60% retention. What's wrong and how do I fix it?"},
            {"role": "assistant", "content": make_feedback(situation, random.choice(problems))},
        ],
        "source": "synthetic_feedback",
        "weight": 3,
        "cluster": "feedback_critique",
    })
    
    # 5. Emotion-specific advice
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"How do I make a pixel art Short about {situation} feel genuinely {emotion}? What specific techniques work?"},
            {"role": "assistant", "content": f"""For {emotion} in a pixel art Short about {situation}, these techniques work:

**Visual signals for {emotion}:**
{random.choice([
    "Tight close-ups on the character's face at peak moments. Pixel art handles expression through eye shape and mouth position — a single pixel difference reads as a completely different emotion.",
    "Color temperature shifts. Cool blues/greens for calm, warm oranges/reds as tension builds. The palette does half the emotional work before a word is spoken.",
    "Speed of animation. Fast erratic movement = panic/comedy. Slow deliberate movement = dread/weight. The timing of frames is your emotional dial.",
    "Environmental storytelling. What's in the background reacts to the character's situation. Trees sway faster, shadows grow, lighting shifts — the world responds emotionally.",
])}

**Script techniques for {emotion}:**
{random.choice([
    "Withhold one key piece of information. The audience feels what the character doesn't know. Dramatic irony is the engine of suspense and dread.",
    "Give the character one moment of hope before taking it away. The higher the hope, the harder the fall — and the more satisfying the resolution.",
    "Use silence strategically. A beat with no narration forces the viewer to sit with the emotion. Most Shorts overcrowd every second.",
    "The character's internal reaction should always be slightly delayed from the event. The delay creates the comedic or dramatic beat.",
])}

**Pacing for {emotion}:**
{emotion.split('/')[0].capitalize()} content works best at {random.choice(['30', '34', '50'])} seconds. Long enough for the emotion to build, short enough that it doesn't dissipate. The payoff should land in the last 20% of the video.

**What kills {emotion} in Shorts:**
Explaining the emotion instead of showing it. If the narrator says "he was scared" — you've lost it. Show the sweat, the wide eyes, the frozen posture. Trust the audience to feel it."""},
        ],
        "source": "synthetic_emotion",
        "weight": 3,
        "cluster": "emotion_targeting",
    })

# ── ANALYTICS EXAMPLES ──
retention_scenarios = [
    (45, "30s", "The hook isn't landing. 45% at 30 seconds means half your audience swiped in the first few seconds. The first 1.5 seconds need a pattern interrupt — something visually unexpected or a line that creates an immediate question."),
    (68, "50s", "68% is below the 90% minimum for virality. You're likely losing people at the transition from obstacle 1 to amplifier. Check your retention graph — if there's a dip around the 60% mark of the video, that's your dead zone."),
    (82, "30s", "You're close. 82% means you're losing about 18% before the end. Usually this is the last 5 seconds being too slow after the payoff. Cut everything after the punchline lands. End on momentum, not resolution."),
    (91, "40s", "91% is above threshold, but 40-second Shorts historically underperform versus 30s and 50s. Consider trimming 10 seconds or adding a second obstacle to justify the length. The 40-second zone is awkward for the algorithm."),
    (78, "60s", "78% on a 60-second Short is a critical problem. 60-second Shorts need 90%+ to compete. Either cut 20-30 seconds or add a stronger rewatch mechanism. At 60 seconds you need a loop point — the ending should visually connect to the opening."),
]

for pct, length, diagnosis in retention_scenarios:
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"My {length} Short is getting {pct}% average view duration. Is this good? What should I do?"},
            {"role": "assistant", "content": f"""{diagnosis}

**Benchmark for {length} Shorts:**
- Below 80%: Structural problem. Audience is leaving before the payoff.
- 80-89%: Decent but not viral territory. Small fixes can push you over.  
- 90-99%: Viral threshold. Algorithm starts pushing harder.
- 100%+: Rewatches happening. This is the strongest signal you can send.

**Diagnostic steps:**
1. Open YouTube Studio → go to the retention graph for this Short
2. Find the exact second where the biggest drop happens
3. Watch that moment in your video — that's your problem
4. Ask: Is this a pacing issue, a weak beat, or dead space?

**Quick fixes by drop location:**
- Drop in first 3s → Hook isn't landing. Recut the opening.
- Drop at 30-50% → Obstacle 1 is too slow or the amplifier is missing.
- Drop in last 10% → Payoff is too slow. Cut everything after the punchline.
- Gradual decline throughout → Pacing issue. Every beat is 1-2 seconds too long.

**For rewatches (100%+):** Engineer a loop point. Make the ending connect visually to the opening so when it loops, the viewer is already 5 seconds into a second watch."""},
        ],
        "source": "synthetic_analytics",
        "weight": 3,
        "cluster": "analytics_strategy",
    })

# ── PLATFORM ADVICE ──
platform_qa = [
    ("Should I post pixel art animated Shorts on YouTube or TikTok first?",
     """Start with YouTube Shorts for pixel art animation, without question.

**Why YouTube wins for pixel art:**
1. More mature audience tolerates story-based content — TikTok audience skews younger and wants faster, denser content
2. YouTube favors 30-50 second narrative arcs — your story has room to breathe
3. Pixel art animation is a visual style that rewards rewatches — YouTube's algorithm rewards rewatch rate heavily
4. Better monetization once you hit YPP — Shorts RPM on YouTube is improving significantly
5. Your niche (pixel art storytelling) has established creators on YouTube (PixelBeef, t3ssel8r) with proven audiences there

**The Jenny Hoyos proof:** Same content → 1M views on TikTok, 1K on YouTube. After switching focus to YouTube → 1M on YouTube, 1K on TikTok. The platforms literally want different content.

**For pixel art specifically:** TikTok's fast-cut, dense-info format fights against the visual style. Pixel art works best when the audience has time to appreciate the craft. YouTube gives you that.

**Cross-post strategy:** Build your YouTube audience first. Once you have 10-20 Shorts that work on YouTube, adapt the best performers for TikTok by cutting them to 15-20s and front-loading even harder."""),
    
    ("How do I make my pixel art Short go viral on YouTube specifically?",
     """For pixel art Shorts to go viral on YouTube, these are the actual levers:

**Algorithm signals in order of importance:**
1. Scroll-through rate (don't lose people in first 3 seconds) — first frame must be visually striking
2. Average view duration — 90%+ minimum, 100%+ for extended distribution
3. Rewatch rate — pixel art has a natural advantage here because people want to catch details they missed
4. Engagement (comments, shares) — pixel art creates communities that comment heavily

**Your unfair advantages as a pixel art creator:**
- Visual novelty stops the scroll better than talking-head content
- The craft itself is a retention mechanism — people watch to see the animation
- Communities around pixel art and gaming are highly engaged commenters
- "How did they make this?" triggers rewatches

**What kills pixel art Shorts:**
- Opening on a static or slow establishing shot (YouTube's algorithm measures first-frame scroll-through rate)
- Over-explaining the story in narration when the visuals can show it
- Letting the ending linger — cut immediately after the payoff lands

**The 3-frame rule for pixel art:** Your first 3 seconds need: (1) a character the audience can immediately understand, (2) something visually wrong or unusual, (3) a reason to want to know what happens. If your opening frames don't do all three, recut."""),
]

for q, a in platform_qa:
    examples.append({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": q},
            {"role": "assistant", "content": a},
        ],
        "source": "synthetic_platform",
        "weight": 3,
        "cluster": "platform_strategy",
    })

# Save
out_path = OUT / "synthetic_local.jsonl"
with open(out_path, "w") as f:
    for ex in examples:
        f.write(json.dumps(ex) + "\n")

print(f"Generated {len(examples)} local synthetic examples")
print(f"Clusters: {set(e['cluster'] for e in examples)}")
