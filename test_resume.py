"""
Resume verification test — runs on CPU with GPT-2 (tiny).
Compatible with trl >= 1.0 (uses SFTConfig instead of SFTTrainer kwargs).

Test: after epoch 1 checkpoint, does trainer resume at epoch > 1.0 or restart at 0.xx?
"""

import os, glob, json, shutil, tempfile
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from trl import SFTTrainer, SFTConfig

# ── tiny synthetic dataset (same messages format as real training data) ──────
SYNTHETIC = [
    {
        "text": (
            f"SYSTEM: You are a story director.\n"
            f"USER: Write a hook for story {i}\n"
            f"ASSISTANT: Story {i}: The hero stood at the edge. "
            f"But then the ground cracked open beneath him."
        )
    }
    for i in range(40)   # 40 examples → eff_batch=8 → 5 steps/epoch
]

CHECKPOINT_DIR = tempfile.mkdtemp(prefix="resume_test_")
print(f"📁 Checkpoint dir: {CHECKPOINT_DIR}")

# ── load GPT-2 (tiny, CPU-friendly) ──────────────────────────────────────────
print("\n⏳ Loading GPT-2 (smallest model, CPU only)...")
MODEL_NAME = "gpt2"
tokenizer  = AutoTokenizer.from_pretrained(MODEL_NAME)
tokenizer.pad_token = tokenizer.eos_token
model      = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
print("✅ GPT-2 loaded")

ds = Dataset.from_list(SYNTHETIC)
effective_batch = 2 * 4   # per_device_batch=2 × grad_accum=4
steps_per_epoch = len(ds) // effective_batch
print(f"✅ Dataset: {len(ds)} examples  →  {steps_per_epoch} steps/epoch (eff_batch={effective_batch})")

# ── shared config values (MUST be identical between epoch 1 and epoch 2) ────
SHARED = dict(
    output_dir                  = CHECKPOINT_DIR,
    per_device_train_batch_size = 2,
    gradient_accumulation_steps = 4,
    learning_rate               = 1e-4,
    logging_steps               = 1,
    save_strategy               = "epoch",
    save_total_limit            = 3,
    report_to                   = "none",
    seed                        = 42,
    dataloader_drop_last        = True,   # must match in both runs
    use_cpu                     = True,   # CPU demo
    # SFTConfig-specific
    dataset_text_field          = "text",
)

# ─────────────────────────────────────────────────────────────────────────────
# EPOCH 1
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print(f"  EPOCH 1 — will run {steps_per_epoch} steps then save checkpoint")
print("="*55)

cfg_ep1 = SFTConfig(num_train_epochs=1, **SHARED)
trainer_ep1 = SFTTrainer(
    model         = model,
    processing_class = tokenizer,
    train_dataset = ds,
    args          = cfg_ep1,
)

stats_ep1 = trainer_ep1.train()

# ── verify checkpoint saved correctly ────────────────────────────────────────
ckpts = sorted(
    glob.glob(f"{CHECKPOINT_DIR}/checkpoint-*"),
    key=lambda x: int(x.split("-")[-1])
)
assert ckpts, "❌ No checkpoint saved after epoch 1!"
latest     = ckpts[-1]
step_saved = int(latest.split("-")[-1])

with open(os.path.join(latest, "trainer_state.json")) as f:
    state = json.load(f)
saved_epoch = state["epoch"]

print(f"\n✅ Epoch 1 done.  loss={stats_ep1.training_loss:.4f}")
print(f"   Checkpoint   : {os.path.basename(latest)}")
print(f"   Step saved   : {step_saved}  (expected ~{steps_per_epoch})")
print(f"   Epoch saved  : {saved_epoch}  ← must be ~1.0 for resume to work")

# verify critical files
REQUIRED = ["trainer_state.json", "optimizer.pt", "scheduler.pt"]
all_ok = True
for fn in REQUIRED:
    path = os.path.join(latest, fn)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    ok   = size > 0
    print(f"   {'✅' if ok else '❌'}  {fn}  ({size/1024:.1f} KB)")
    if not ok:
        all_ok = False

assert all_ok, "❌ Missing checkpoint files — resume will silently restart!"
assert abs(saved_epoch - 1.0) < 0.1, f"Checkpoint epoch={saved_epoch}, expected ~1.0"

# ─────────────────────────────────────────────────────────────────────────────
# EPOCH 2 RESUME
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*55)
print("  EPOCH 2 — resuming from checkpoint")
print("  WATCH: first logged epoch should be > 1.0")
print("="*55 + "\n")

cfg_ep2 = SFTConfig(num_train_epochs=2, **SHARED)   # only change: 2 epochs total
trainer_ep2 = SFTTrainer(
    model            = model,
    processing_class = tokenizer,
    train_dataset    = ds,
    args             = cfg_ep2,
)

stats_ep2 = trainer_ep2.train(resume_from_checkpoint=latest)

# ─────────────────────────────────────────────────────────────────────────────
# VERDICT
# NOTE: after resume, trainer_ep2.state.log_history contains the FULL history
# loaded from the checkpoint file (including all epoch 1 entries).
# We must filter to only entries logged AFTER the checkpoint step.
# ─────────────────────────────────────────────────────────────────────────────
log_history = trainer_ep2.state.log_history

# entries from new run only (step > checkpoint step)
new_logs      = [l for l in log_history if "epoch" in l and l.get("step", 0) > step_saved]
first_new_log = new_logs[0] if new_logs else None
first_epoch   = first_new_log["epoch"] if first_new_log else None

print("\n" + "="*55)
print("  RESUME VERIFICATION RESULT")
print("="*55)
print(f"  Checkpoint step              : {step_saved}")
print(f"  Total log entries            : {len(log_history)}  (includes epoch 1 history loaded from checkpoint)")
print(f"  New entries (step>{step_saved})        : {len(new_logs)}")
print(f"  First NEW log entry          : {first_new_log}")
print()

if first_epoch is not None and first_epoch >= 1.0:
    print(f"  ✅ PASS — first new log epoch = {first_epoch:.3f}  (> 1.0)")
    print(f"  Epoch 1 was SKIPPED. Resume is working correctly.")
    print(f"  Your real H100 run will NOT redo epoch 1.")
elif first_epoch is not None:
    print(f"  ❌ FAIL — first new log epoch = {first_epoch:.3f}  (< 1.0 = restarted)")
    print(f"  Trainer restarted from scratch. The bug is still present.")
else:
    print("  ⚠️  Could not find any new log entries after checkpoint step")
    print(f"  All log entries: {log_history}")

print("="*55)

# cleanup temp dir
shutil.rmtree(CHECKPOINT_DIR)
print(f"\n🧹 Cleaned up temp checkpoint dir")
