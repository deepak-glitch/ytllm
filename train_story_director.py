"""
train_story_director.py — Fine-tune Story Director LLM
=======================================================
Fine-tunes Qwen3 on your viral short-form video dataset using QLoRA.
Run each cell in Colab Pro (A100 GPU required).

BEFORE RUNNING:
  1. Runtime → Change runtime type → A100 GPU + High RAM
  2. Fill in the ── FILL IN YOUR DETAILS ── section below
  3. Run cells top to bottom
"""

# ══════════════════════════════════════════════════════════════════════════════
# ── FILL IN YOUR DETAILS ──────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

MODEL_SIZE        = "7B"          # "7B" (1 hr) or "27B" (5 hrs) — start with 7B
HF_USERNAME       = "Deepak0070"  # your HuggingFace username
HF_TOKEN          = ""            # get from huggingface.co/settings/tokens → Write access
MODEL_REPO_NAME   = "story-director-v1"  # what to call it on HuggingFace

DATASET_PATH      = "/content/drive/MyDrive/ytllm_v2/training_data_v9.jsonl"
CHECKPOINT_DIR    = "/content/drive/MyDrive/ytllm_v2/model_checkpoints"
OUTPUT_DIR        = "/content/drive/MyDrive/ytllm_v2/story-director-final"

NUM_EPOCHS        = 1             # 1 = good starting point; try 2 if output feels shallow
MAX_SEQ_LENGTH    = 2048
ENABLE_THINKING   = False         # False = faster, direct output (recommended for JSON)

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
# Injected into every training example — teaches the model exactly who it is
SYSTEM_PROMPT = (
    "You are the Story Director for a 3D pixel art YouTube Shorts channel. "
    "You write viral short-form video scripts using the Hook → Foreshadow → "
    "Obstacle → Amplifier → Twist → Payoff framework. "
    "Rules you never break:\n"
    "- Hook lands in 1.5-3 seconds — it must create instant curiosity or stakes\n"
    "- Foreshadow is always 2 lines, under 3 seconds\n"
    "- Use but/therefore storytelling — never and/then\n"
    "- 90%+ retention is the minimum; 100%+ means rewatches = algorithm's strongest signal\n"
    "- Sweet spots: 30 seconds or 50 seconds — never 20 or 40, they underperform\n"
    "- 5th grade reading level or below for all narration\n"
    "- End IMMEDIATELY after the payoff — never let it breathe\n"
    "- Every scene must earn its place or it gets cut\n"
    "You speak from real creator experience — direct, no fluff, no filler."
)

# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 1: CHECK GPU ─────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════
"""
Run this first. Make sure you see A100 with 40GB.
If you see T4 or L4, go Runtime → Change runtime type → A100.
"""

import subprocess, os, sys
result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                         "--format=csv,noheader"], capture_output=True, text=True)
gpu_info = result.stdout.strip()
print(f"GPU: {gpu_info}")

import psutil
ram_gb = psutil.virtual_memory().total / 1e9
print(f"RAM: {ram_gb:.0f} GB")

if "A100" not in gpu_info:
    print("\n⚠️  WARNING: You don't have an A100!")
    print("   Go to Runtime → Change runtime type → A100")
    print("   27B model WILL crash on anything smaller.")
    if MODEL_SIZE == "27B":
        print("   Switch MODEL_SIZE to '7B' or upgrade to A100 first.")
else:
    vram = int(gpu_info.split(",")[1].strip().split()[0])
    print(f"\n✅ A100 detected ({vram} MiB VRAM)")
    if MODEL_SIZE == "27B" and vram < 35000:
        print("⚠️  Less than 40GB VRAM — switch to 7B or you'll OOM")
    else:
        print(f"✅ {MODEL_SIZE} model will fit fine")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 2: INSTALL ───────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "unsloth"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
    "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git",
    "trl", "peft", "accelerate", "bitsandbytes", "datasets",
    "huggingface_hub", "transformers"], check=True)
print("✅ All packages installed")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 3: LOAD MODEL ────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from unsloth import FastLanguageModel
import torch

MODEL_MAP = {
    "7B":  "unsloth/Qwen3-7B-bnb-4bit",
    "27B": "unsloth/Qwen3.6-27B",        # no bnb-4bit yet, quantizes on load (~10 min)
}
BATCH_MAP = {
    "7B":  (2, 4),   # (per_device_batch, grad_accumulation) → effective batch 8
    "27B": (1, 8),   # smaller batch for bigger model → effective batch 8
}

model_name = MODEL_MAP[MODEL_SIZE]
batch_size, grad_accum = BATCH_MAP[MODEL_SIZE]

print(f"Loading {MODEL_SIZE} model: {model_name}")
print("This takes 2-10 minutes depending on model size...")

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name     = model_name,
    max_seq_length = MAX_SEQ_LENGTH,
    dtype          = None,
    load_in_4bit   = True,
)

import torch
used_gb = torch.cuda.memory_allocated() / 1e9
total_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"\n✅ Model loaded")
print(f"   VRAM used: {used_gb:.1f} GB / {total_gb:.0f} GB")
print(f"   VRAM free: {total_gb - used_gb:.1f} GB (for training overhead)")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 4: ATTACH LORA ADAPTERS ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

model = FastLanguageModel.get_peft_model(
    model,
    r                          = 16,   # adapter rank: 16 = good balance
    target_modules             = ["q_proj", "k_proj", "v_proj", "o_proj",
                                  "gate_proj", "up_proj", "down_proj"],
    lora_alpha                 = 16,
    lora_dropout               = 0,
    bias                       = "none",
    use_gradient_checkpointing = "unsloth",  # saves ~30% VRAM
    random_state               = 42,
)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total     = sum(p.numel() for p in model.parameters())
print(f"✅ LoRA adapters attached")
print(f"   Trainable params: {trainable/1e6:.1f}M / {total/1e6:.0f}M "
      f"({100*trainable/total:.2f}%) — only these get updated")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 5: LOAD + FORMAT DATASET ────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from datasets import load_dataset
from unsloth.chat_templates import get_chat_template

tokenizer = get_chat_template(tokenizer, chat_template="qwen-3")

print(f"Loading dataset from: {DATASET_PATH}")
dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
print(f"Raw examples: {len(dataset):,}")

def format_example(example):
    """Convert messages array → single training string in Qwen3 chat format.
    Replaces the generic system prompt with the pixel-art Story Director prompt."""
    try:
        msgs = example["messages"]

        # Replace system message with the specific Story Director prompt
        upgraded = []
        has_system = any(m["role"] == "system" for m in msgs)
        if not has_system:
            upgraded.append({"role": "system", "content": SYSTEM_PROMPT})
        for m in msgs:
            if m["role"] == "system":
                upgraded.append({"role": "system", "content": SYSTEM_PROMPT})
            else:
                upgraded.append(m)

        text = tokenizer.apply_chat_template(
            upgraded,
            tokenize              = False,
            add_generation_prompt = False,
            enable_thinking       = ENABLE_THINKING,
        )
        return {"text": text, "valid": True}
    except Exception:
        return {"text": "", "valid": False}

dataset = dataset.map(format_example, num_proc=4)
dataset = dataset.filter(lambda x: x["valid"] and len(x["text"]) > 50)
dataset = dataset.remove_columns([c for c in dataset.column_names if c != "text"])

print(f"Formatted examples: {len(dataset):,}")
print(f"\n--- SAMPLE (first 600 chars) ---")
print(dataset[0]["text"][:600])
print("...")

# Token length distribution
import random
sample = random.sample(range(len(dataset)), min(500, len(dataset)))
lengths = [len(tokenizer(dataset[i]["text"])["input_ids"]) for i in sample]
avg_len = sum(lengths) / len(lengths)
max_len = max(lengths)
print(f"\n📊 Token lengths (sample of {len(sample)}):")
print(f"   Average: {avg_len:.0f} tokens")
print(f"   Max:     {max_len} tokens")
if max_len > MAX_SEQ_LENGTH:
    print(f"   ⚠️  Some examples exceed {MAX_SEQ_LENGTH} tokens — they'll be truncated")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 6: TRAIN ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from trl import SFTTrainer
from transformers import TrainingArguments
import math, time

os.makedirs(CHECKPOINT_DIR, exist_ok=True)

steps_per_epoch = math.ceil(len(dataset) / (batch_size * grad_accum))
total_steps     = steps_per_epoch * NUM_EPOCHS
est_minutes     = total_steps * (0.5 if MODEL_SIZE == "7B" else 1.5) / 60

print(f"🚀 Training config:")
print(f"   Model:             {MODEL_SIZE}")
print(f"   Examples:          {len(dataset):,}")
print(f"   Epochs:            {NUM_EPOCHS}")
print(f"   Steps per epoch:   {steps_per_epoch:,}")
print(f"   Total steps:       {total_steps:,}")
print(f"   Effective batch:   {batch_size * grad_accum}")
print(f"   Estimated time:    ~{est_minutes:.0f} minutes")
print()

trainer = SFTTrainer(
    model              = model,
    tokenizer          = tokenizer,
    train_dataset      = dataset,
    dataset_text_field = "text",
    max_seq_length     = MAX_SEQ_LENGTH,
    dataset_num_proc   = 4,
    args = TrainingArguments(
        per_device_train_batch_size  = batch_size,
        gradient_accumulation_steps  = grad_accum,
        num_train_epochs             = NUM_EPOCHS,
        warmup_ratio                 = 0.05,
        learning_rate                = 2e-4,
        fp16                         = not torch.cuda.is_bf16_supported(),
        bf16                         = torch.cuda.is_bf16_supported(),
        logging_steps                = 25,
        optim                        = "adamw_8bit",
        weight_decay                 = 0.01,
        lr_scheduler_type            = "cosine",
        seed                         = 42,
        output_dir                   = CHECKPOINT_DIR,
        save_strategy                = "steps",
        save_steps                   = 500,
        save_total_limit             = 2,        # keep only last 2 checkpoints on Drive
        report_to                    = "none",
    ),
)

start = time.time()
trainer_stats = trainer.train()
elapsed = (time.time() - start) / 60

print(f"\n✅ Training complete in {elapsed:.1f} minutes")
print(f"   Final loss: {trainer_stats.metrics.get('train_loss', 'N/A'):.4f}")
print(f"   Loss < 1.2 = good    |    Loss < 1.0 = great    |    Loss < 0.8 = excellent")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 7: TEST THE MODEL ────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

FastLanguageModel.for_inference(model)

TEST_PROMPTS = [
    "Write a viral 30-second pixel art story about a knight who discovers his sword is cursed.",
    "Give me the hook for a short about a chef who realizes mid-service that the secret ingredient is missing.",
    "What makes a YouTube Short go viral in the first 3 seconds?",
]

print("=" * 60)
print("🧪 MODEL TEST")
print("=" * 60)

for i, prompt in enumerate(TEST_PROMPTS, 1):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    formatted = tokenizer.apply_chat_template(
        messages,
        tokenize              = False,
        add_generation_prompt = True,
        enable_thinking       = ENABLE_THINKING,
    )
    inputs = tokenizer(formatted, return_tensors="pt").to("cuda")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens = 400,
            temperature    = 0.8,
            top_p          = 0.9,
            do_sample      = True,
            pad_token_id   = tokenizer.eos_token_id,
        )

    response = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True
    ).strip()

    print(f"\n[Test {i}] {prompt}")
    print("-" * 40)
    print(response[:500])
    print()


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 8: SAVE + PUSH TO HUGGINGFACE ───────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from huggingface_hub import login

if not HF_TOKEN:
    print("⚠️  No HF_TOKEN set — skipping HuggingFace push")
    print("   Set HF_TOKEN at the top of this script and re-run this cell.")
    print(f"   Saving locally to {OUTPUT_DIR} instead...")
    model.save_pretrained_merged(OUTPUT_DIR, tokenizer, save_method="merged_16bit")
    print(f"✅ Saved to Drive: {OUTPUT_DIR}")
else:
    login(token=HF_TOKEN)
    repo_id = f"{HF_USERNAME}/{MODEL_REPO_NAME}"
    print(f"Pushing to huggingface.co/{repo_id} ...")
    print("(This takes 10-20 min for 27B — don't close Colab)")

    model.push_to_hub_merged(
        repo_id,
        tokenizer,
        save_method  = "merged_16bit",
        token        = HF_TOKEN,
    )

    # Also save locally to Drive as backup
    model.save_pretrained_merged(OUTPUT_DIR, tokenizer, save_method="merged_16bit")

    print(f"\n✅ Model live at: huggingface.co/{repo_id}")
    print(f"✅ Backup saved:  {OUTPUT_DIR}")
    print()
    print("Test it instantly:")
    print(f"  from transformers import pipeline")
    print(f"  pipe = pipeline('text-generation', model='{repo_id}')")
