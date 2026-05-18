#!/bin/bash
# One-command setup for RunPod / Vast.ai A100 80GB pod
# Run: bash setup_runpod.sh
# Assumes: PyTorch 2.x image (e.g. runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel)

set -e

echo "=== Installing Axolotl + Unsloth ==="
pip install -q axolotl[flash-attn,deepspeed]
pip install -q unsloth

echo "=== Cloning repo ==="
cd /workspace
git clone https://github.com/deepak-glitch/ytllm.git
cd ytllm

echo "=== Converting dataset to ShareGPT format ==="
python training/convert_to_sharegpt.py
cp training/training_data_sharegpt.jsonl /workspace/training_data_sharegpt.jsonl

echo "=== Starting QLoRA fine-tune ==="
# Logs every 10 steps. Checkpoints at /workspace/qwen3-27b-story-director/
accelerate launch -m axolotl.cli.train training/axolotl_config.yml

echo "=== Done. Adapter saved to /workspace/qwen3-27b-story-director/ ==="
