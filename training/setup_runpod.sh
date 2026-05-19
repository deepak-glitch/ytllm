#!/bin/bash
# Run from inside /workspace/ytllm after cloning the repo.
# Background it: nohup bash training/setup_runpod.sh > training.log 2>&1 &

set -e

cd "$(dirname "$0")/.."   # always run from repo root

echo "=== Step 1/3: Installing Axolotl + dependencies ==="
pip install -q --upgrade pip
pip install -q "axolotl[flash-attn,deepspeed]"

echo "=== Step 2/3: Converting dataset to ShareGPT format ==="
python training/convert_to_sharegpt.py
cp training/training_data_sharegpt.jsonl /workspace/training_data_sharegpt.jsonl

echo "=== Step 3/3: Starting QLoRA fine-tune ==="
echo "Watch logs anytime with: tail -f /workspace/ytllm/training.log"
accelerate launch -m axolotl.cli.train training/axolotl_config.yml

echo ""
echo "=== Done! Adapter saved to /workspace/qwen3-27b-story-director/ ==="
echo "Pack for download: tar czf /workspace/adapter.tar.gz -C /workspace qwen3-27b-story-director"
