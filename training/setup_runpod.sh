#!/bin/bash
# Works on both A100 (Ampere sm_80) and RTX PRO 6000 (Blackwell sm_120)
# Background it: nohup bash training/setup_runpod.sh > training.log 2>&1 &

set -e
cd "$(dirname "$0")/.."

echo "=== Step 1/4: Detecting GPU ==="
python -c "
import torch
name = torch.cuda.get_device_name(0)
cap  = torch.cuda.get_device_capability(0)
print(f'GPU  : {name}')
print(f'Arch : sm_{cap[0]}{cap[1]}')
print(f'Torch: {torch.__version__}')
print(f'CUDA : {torch.version.cuda}')
"
GPU_CAP=$(python -c "import torch; print(torch.cuda.get_device_capability(0)[0])")
echo "Compute capability major: $GPU_CAP"

echo "=== Step 2/4: Installing Axolotl ==="
pip install -q --upgrade pip wheel packaging
pip install -q "axolotl[deepspeed]"

# Blackwell (sm_12x) needs torch 2.7+ — axolotl's deps downgrade it to 2.5
# Reinstall the right torch AFTER axolotl so it wins
if [ "$GPU_CAP" -ge 12 ]; then
    echo "--- Blackwell detected: reinstalling torch 2.7+ for sm_120 support ---"
    pip install -q torch torchvision torchaudio --upgrade \
        --index-url https://download.pytorch.org/whl/cu128
    pip install -q bitsandbytes --upgrade
else
    echo "--- Ampere/Hopper: keeping installed torch ---"
fi

echo "=== Step 3/4: Installing flash-attn ==="
pip install -q flash-attn --no-build-isolation

# Verify torch sees the GPU correctly
python -c "
import torch
assert torch.cuda.is_available(), 'CUDA not available!'
name = torch.cuda.get_device_name(0)
cap  = torch.cuda.get_device_capability(0)
print(f'GPU ready: {name} (sm_{cap[0]}{cap[1]})')
x = torch.ones(1, device='cuda')
print(f'CUDA test: {x} — OK')
"

echo "=== Step 4/4: Converting dataset and starting training ==="
python training/convert_to_sharegpt.py
cp training/training_data_sharegpt.jsonl /workspace/training_data_sharegpt.jsonl

echo "Watch logs: tail -f /workspace/ytllm/training.log"
accelerate launch -m axolotl.cli.train training/axolotl_config.yml

echo ""
echo "=== Done! Adapter at /workspace/qwen3-27b-story-director/ ==="
echo "Pack: tar czf /workspace/adapter.tar.gz -C /workspace qwen3-27b-story-director"
