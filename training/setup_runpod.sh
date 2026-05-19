#!/bin/bash
# Works on A100 (Ampere sm_80) — auto-detects 1 or 2 GPUs
# Background it: nohup bash training/setup_runpod.sh > training.log 2>&1 &

set -e
cd "$(dirname "$0")/.."

echo "=== Step 1/4: Detecting GPU ==="
python -c "
import torch
name = torch.cuda.get_device_name(0)
cap  = torch.cuda.get_device_capability(0)
n    = torch.cuda.device_count()
print(f'GPU  : {n}x {name}')
print(f'Arch : sm_{cap[0]}{cap[1]}')
print(f'Torch: {torch.__version__}')
print(f'CUDA : {torch.version.cuda}')
"
GPU_COUNT=$(python -c "import torch; print(torch.cuda.device_count())")
GPU_CAP=$(python -c "import torch; print(torch.cuda.get_device_capability(0)[0])")
echo "GPUs: $GPU_COUNT | Compute capability major: $GPU_CAP"

echo "=== Step 2/4: Installing Axolotl ==="
pip install -q --upgrade pip wheel packaging
pip install -q "axolotl[deepspeed]"

# Blackwell (sm_12x) needs torch 2.7+ — reinstall after axolotl downgrades it
if [ "$GPU_CAP" -ge 12 ]; then
    echo "--- Blackwell detected: reinstalling torch 2.7+ for sm_120 support ---"
    pip install -q torch torchvision torchaudio --upgrade \
        --index-url https://download.pytorch.org/whl/cu128
    pip install -q bitsandbytes --upgrade
else
    echo "--- Ampere/Hopper detected: keeping installed torch ---"
fi

echo "=== Step 3/4: Installing flash-attn ==="
pip install -q flash-attn --no-build-isolation

# Verify GPU is accessible
python -c "
import torch
assert torch.cuda.is_available(), 'CUDA not available!'
n = torch.cuda.device_count()
for i in range(n):
    print(f'GPU {i}: {torch.cuda.get_device_name(i)}')
x = torch.ones(1, device='cuda')
print(f'CUDA test OK')
"

echo "=== Step 4/4: Converting dataset and starting training ==="
python training/convert_to_sharegpt.py
cp training/training_data_sharegpt.jsonl /workspace/training_data_sharegpt.jsonl

echo "Training on $GPU_COUNT GPU(s)..."
echo "Watch logs: tail -f /workspace/ytllm/training.log"

if [ "$GPU_COUNT" -gt 1 ]; then
    echo "Multi-GPU mode: $GPU_COUNT GPUs"
    accelerate launch --num_processes=$GPU_COUNT --multi_gpu \
        -m axolotl.cli.train training/axolotl_config.yml
else
    echo "Single-GPU mode"
    accelerate launch --num_processes=1 \
        -m axolotl.cli.train training/axolotl_config.yml
fi

echo ""
echo "=== Done! Adapter at /workspace/qwen3-27b-story-director/ ==="
echo "Pack: tar czf /workspace/adapter.tar.gz -C /workspace qwen3-27b-story-director"
