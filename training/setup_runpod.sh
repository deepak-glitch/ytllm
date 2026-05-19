#!/bin/bash
# Run from inside /workspace/ytllm after cloning the repo.
# Background it: nohup bash training/setup_runpod.sh > training.log 2>&1 &

set -e

cd "$(dirname "$0")/.."   # always run from repo root

echo "=== Step 1/4: Verifying torch ==="
python -c "import torch; print(f'torch {torch.__version__}, CUDA {torch.version.cuda}, GPU: {torch.cuda.get_device_name(0)}')"

echo "=== Step 2/4: Installing Axolotl (without flash-attn) ==="
pip install -q --upgrade pip wheel packaging
pip install -q "axolotl[deepspeed]"

echo "=== Step 3/4: Installing flash-attn separately (with --no-build-isolation) ==="
pip install -q flash-attn --no-build-isolation

echo "=== Step 4/4: Converting dataset and starting training ==="
python training/convert_to_sharegpt.py
cp training/training_data_sharegpt.jsonl /workspace/training_data_sharegpt.jsonl

echo "Watch logs anytime with: tail -f /workspace/ytllm/training.log"
accelerate launch -m axolotl.cli.train training/axolotl_config.yml

echo ""
echo "=== Done! Adapter saved to /workspace/qwen3-27b-story-director/ ==="
echo "Pack for download: tar czf /workspace/adapter.tar.gz -C /workspace qwen3-27b-story-director"
