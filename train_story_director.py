"""
train_story_director.py — Fine-tune Qwen3.6-27B Story Director
===============================================================
Model  : Qwen3.6-27B (QLoRA 4-bit)
GPU    : H100 80GB  (~2 hours)
Target : Viral pixel art YouTube Shorts story generation

BEFORE RUNNING:
  1. Runtime → Change runtime type → H100 GPU + High RAM
  2. Fill in HF_TOKEN and DATASET_PATH below
  3. Run All (Ctrl+F9)
"""

# ══════════════════════════════════════════════════════════════════════════════
# ── FILL IN YOUR DETAILS ──────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

HF_TOKEN        = ""                    # huggingface.co/settings/tokens → New token → Write
HF_USERNAME     = "Deepak0070"
MODEL_REPO_NAME = "story-director-27b-v1"

# Primary dataset (required)
DATASET_PATH    = "/content/drive/MyDrive/ytllm_v2/training_data_v9.jsonl"
# Second dataset — training_data_v9.jsonl is already the full combined dataset, so skip
DATASET_PATH_2  = ""

CHECKPOINT_DIR  = "/content/drive/MyDrive/ytllm_v2/checkpoints_27b"
OUTPUT_DIR      = "/content/drive/MyDrive/ytllm_v2/story-director-27b-final"

# ── EPOCH GUIDE ───────────────────────────────────────────────────────────────
# After epoch 1 check the final loss printed at the end of training:
#   loss > 1.2  → needs more training → set 2
#   loss 0.9-1.2 → solid → 1 is fine, 2 is safe
#   loss < 0.9  → already great → stay at 1 (risk of overfitting at 2)
NUM_EPOCHS      = 2       # 2 = deeper learning on H100 (~4 hrs, worth it)
MAX_SEQ_LENGTH  = 2048
ENABLE_THINKING = False   # False = direct output, no chain-of-thought (recommended)

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
# Injected into every single training example automatically
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

import subprocess, os, sys, time, math, random

result = subprocess.run(
    ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
    capture_output=True, text=True
)
gpu_info = result.stdout.strip()
print(f"GPU : {gpu_info}")

import psutil
print(f"RAM : {psutil.virtual_memory().total / 1e9:.0f} GB")

vram_mib = int(gpu_info.split(",")[1].strip().split()[0])
vram_gb  = vram_mib / 1024

if "H100" in gpu_info:
    print(f"\n🚀 H100 detected ({vram_gb:.0f} GB) — perfect, you're good to go")
elif "A100" in gpu_info and vram_gb >= 38:
    print(f"\n✅ A100 detected ({vram_gb:.0f} GB) — will work, slightly slower than H100")
else:
    print(f"\n❌ WRONG GPU: {gpu_info.split(',')[0].strip()} ({vram_gb:.0f} GB)")
    print("   27B needs at least 40GB VRAM.")
    print("   Go to Runtime → Change runtime type → H100 GPU")
    raise SystemExit("Switch to H100 before continuing.")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 2: INSTALL ───────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

print("Installing packages...")
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "unsloth"], check=True)
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
    "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git",
    "trl", "peft", "accelerate", "bitsandbytes",
    "datasets", "huggingface_hub", "transformers"], check=True)
print("✅ All packages installed")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 3: LOAD MODEL ────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from unsloth import FastLanguageModel
import torch

MODEL_NAME = "unsloth/Qwen3.6-27B"   # quantizes to 4-bit on load (~10 min first time)
BATCH_SIZE = 2                         # H100 80GB can handle batch=2 for 27B
GRAD_ACCUM = 4                         # effective batch = 2 × 4 = 8

print(f"Loading {MODEL_NAME} ...")
print("First load quantizes the model — takes ~10 min. Subsequent runs are faster.")

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name     = MODEL_NAME,
    max_seq_length = MAX_SEQ_LENGTH,
    dtype          = None,       # auto-detect: bf16 on H100
    load_in_4bit   = True,       # QLoRA — keeps base model frozen in 4-bit
)

used_gb  = torch.cuda.memory_allocated() / 1e9
total_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"\n✅ Model loaded")
print(f"   VRAM used : {used_gb:.1f} GB / {total_gb:.0f} GB")
print(f"   VRAM free : {total_gb - used_gb:.1f} GB  (for training overhead)")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 4: ATTACH LORA ADAPTERS ─────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

# r=64 → richest adapters, H100 80GB handles this comfortably
model = FastLanguageModel.get_peft_model(
    model,
    r                          = 64,
    target_modules             = ["q_proj", "k_proj", "v_proj", "o_proj",
                                  "gate_proj", "up_proj", "down_proj"],
    lora_alpha                 = 64,
    lora_dropout               = 0,
    bias                       = "none",
    use_gradient_checkpointing = "unsloth",   # cuts VRAM ~30%
    random_state               = 42,
)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total     = sum(p.numel() for p in model.parameters())
print(f"✅ LoRA adapters attached")
print(f"   Trainable : {trainable/1e6:.1f}M params / {total/1e6:.0f}M total "
      f"({100*trainable/total:.2f}%) — only these get updated during training")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 5: LOAD + FORMAT DATASET ────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from datasets import load_dataset
from unsloth.chat_templates import get_chat_template

tokenizer = get_chat_template(tokenizer, chat_template="qwen-3")

# ── Load + auto-merge datasets ────────────────────────────────────────────────
import os
from datasets import concatenate_datasets

print(f"Loading dataset 1: {DATASET_PATH}")
dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
print(f"  → {len(dataset):,} examples")

if DATASET_PATH_2 and os.path.exists(DATASET_PATH_2):
    print(f"Loading dataset 2: {DATASET_PATH_2}")
    dataset2 = load_dataset("json", data_files=DATASET_PATH_2, split="train")
    print(f"  → {len(dataset2):,} examples")
    # Deduplicate by merging and removing identical rows
    combined = concatenate_datasets([dataset, dataset2])
    # Simple dedup: drop exact duplicate messages arrays by hashing content
    seen = set()
    def mark_unique(example):
        key = str(example.get("messages", ""))[:200]  # first 200 chars as fingerprint
        if key in seen:
            return {"__dup__": True}
        seen.add(key)
        return {"__dup__": False}
    combined = combined.map(mark_unique)
    before = len(combined)
    combined = combined.filter(lambda x: not x["__dup__"])
    combined = combined.remove_columns(["__dup__"])
    dataset = combined
    print(f"Merged: {before:,} total → {len(dataset):,} after dedup "
          f"({before - len(dataset):,} duplicates removed)")
else:
    if DATASET_PATH_2:
        print(f"⚠️  Dataset 2 not found at {DATASET_PATH_2} — training on dataset 1 only")
    print(f"Total examples: {len(dataset):,}")

print(f"\nFinal dataset size: {len(dataset):,} examples")

def format_example(example):
    """Format one training example.
    - Applies Qwen3 chat template
    - Injects the Story Director system prompt into every example
      (replaces any existing generic system message)
    """
    try:
        msgs = example["messages"]

        # Build upgraded message list with Story Director system prompt
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

print("Formatting examples and injecting system prompt...")
dataset = dataset.map(format_example, num_proc=4)
dataset = dataset.filter(lambda x: x["valid"] and len(x["text"]) > 50)
dataset = dataset.remove_columns([c for c in dataset.column_names if c != "text"])
print(f"Formatted examples: {len(dataset):,}")

# Show one formatted example so you can confirm it looks right
print(f"\n{'─'*60}")
print("SAMPLE TRAINING EXAMPLE (first 800 chars):")
print(f"{'─'*60}")
print(dataset[0]["text"][:800])
print("...")

# Token length stats
sample_idx = random.sample(range(len(dataset)), min(500, len(dataset)))
lengths    = [len(tokenizer(dataset[i]["text"])["input_ids"]) for i in sample_idx]
print(f"\n📊 Token length stats (sample of {len(sample_idx)}):")
print(f"   Average : {sum(lengths)/len(lengths):.0f} tokens")
print(f"   Max     : {max(lengths)} tokens")
print(f"   Seq len : {MAX_SEQ_LENGTH} tokens (examples longer than this get truncated)")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 6: TRAIN ─────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from trl import SFTTrainer
from transformers import TrainingArguments

os.makedirs(CHECKPOINT_DIR, exist_ok=True)

steps_per_epoch = math.ceil(len(dataset) / (BATCH_SIZE * GRAD_ACCUM))
total_steps     = steps_per_epoch * NUM_EPOCHS
est_minutes     = total_steps * 0.8 / 60   # ~0.8s/step on H100 for 27B

print(f"🚀 Training — Qwen3.6-27B on H100")
print(f"{'─'*40}")
print(f"   Examples        : {len(dataset):,}")
print(f"   Epochs          : {NUM_EPOCHS}")
print(f"   Batch size      : {BATCH_SIZE} × {GRAD_ACCUM} grad accum = {BATCH_SIZE*GRAD_ACCUM} effective")
print(f"   Steps per epoch : {steps_per_epoch:,}")
print(f"   Total steps     : {total_steps:,}")
print(f"   LoRA rank       : 32")
print(f"   Estimated time  : ~{est_minutes:.0f} minutes (~{est_minutes/60:.1f} hrs)")
print(f"{'─'*40}")
print()

trainer = SFTTrainer(
    model              = model,
    tokenizer          = tokenizer,
    train_dataset      = dataset,
    dataset_text_field = "text",
    max_seq_length     = MAX_SEQ_LENGTH,
    dataset_num_proc   = 4,
    args = TrainingArguments(
        per_device_train_batch_size = BATCH_SIZE,
        gradient_accumulation_steps = GRAD_ACCUM,
        num_train_epochs            = NUM_EPOCHS,
        warmup_ratio                = 0.05,
        learning_rate               = 1e-4,   # lower than default for 2 epochs (avoids overshoot)
        bf16                        = True,     # H100 supports bf16 natively
        fp16                        = False,
        logging_steps               = 25,
        optim                       = "adamw_8bit",
        weight_decay                = 0.01,
        lr_scheduler_type           = "cosine",
        seed                        = 42,
        output_dir                  = CHECKPOINT_DIR,
        save_strategy               = "steps",
        save_steps                  = 200,       # checkpoint every 200 steps
        save_total_limit            = 3,         # keep last 3 on Drive
        report_to                   = "none",
    ),
)

t_start      = time.time()
trainer_stats = trainer.train()
elapsed_min  = (time.time() - t_start) / 60
final_loss   = trainer_stats.metrics.get("train_loss", 0)

print(f"\n✅ Training complete — {elapsed_min:.1f} minutes")
print(f"   Final loss : {final_loss:.4f}")
print(f"   < 1.2 = good  |  < 1.0 = great  |  < 0.8 = excellent")


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 7: TEST THE MODEL ────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

FastLanguageModel.for_inference(model)

TEST_PROMPTS = [
    "Write a viral 30-second pixel art story about a knight who discovers his sword is cursed.",
    "Give me the hook for a short about a chef who realizes mid-service that the secret ingredient is missing.",
    "What's the most common reason a YouTube Short dies in the first 3 seconds?",
]

print("=" * 60)
print("🧪 MODEL OUTPUT TEST")
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
            max_new_tokens = 500,
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
    print("─" * 50)
    print(response[:600])
    print()


# ══════════════════════════════════════════════════════════════════════════════
# ── CELL 8: SAVE + PUSH TO HUGGINGFACE ───────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

from huggingface_hub import login

os.makedirs(OUTPUT_DIR, exist_ok=True)

if not HF_TOKEN:
    print("⚠️  HF_TOKEN not set — saving to Drive only (no HuggingFace push)")
    print(f"   Set HF_TOKEN at the top and re-run this cell to push later.")
    print(f"\nSaving merged model to Drive...")
    model.save_pretrained_merged(OUTPUT_DIR, tokenizer, save_method="merged_16bit")
    print(f"✅ Saved: {OUTPUT_DIR}")
else:
    login(token=HF_TOKEN)
    repo_id = f"{HF_USERNAME}/{MODEL_REPO_NAME}"

    print(f"Pushing to huggingface.co/{repo_id}")
    print("27B merged model = ~54 GB upload — takes 15-30 min, don't close Colab")

    model.push_to_hub_merged(
        repo_id,
        tokenizer,
        save_method = "merged_16bit",
        token       = HF_TOKEN,
    )

    # Drive backup
    print(f"\nSaving backup to Drive: {OUTPUT_DIR}")
    model.save_pretrained_merged(OUTPUT_DIR, tokenizer, save_method="merged_16bit")

    print(f"\n✅ Model live  : huggingface.co/{repo_id}")
    print(f"✅ Drive backup: {OUTPUT_DIR}")
    print()
    print("Load it anywhere with:")
    print(f"  from transformers import pipeline")
    print(f"  pipe = pipeline('text-generation', model='{repo_id}')")
    print(f"  pipe([{{'role':'user','content':'Write me a 30s pixel art hook'}}])")
