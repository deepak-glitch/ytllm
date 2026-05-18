#!/bin/bash
# One-command setup for Vast.ai single RTX PRO 6000 96GB (or A100 80GB)
# Run inside tmux: tmux new -s train && bash setup_runpod.sh
# Assumes: PyTorch 2.x + CUDA 12.x image

set -e

echo "=== Step 1/4: Installing Axolotl ==="
pip install -q axolotl[flash-attn,deepspeed]

echo "=== Step 2/4: Cloning repo ==="
cd /workspace
if [ ! -d ytllm ]; then
  git clone https://github.com/deepak-glitch/ytllm.git
fi
cd ytllm
git pull

echo "=== Step 3/4: Converting dataset to ShareGPT format ==="
python training/convert_to_sharegpt.py
cp training/training_data_sharegpt.jsonl /workspace/training_data_sharegpt.jsonl

echo "=== Step 4/4: Starting QLoRA fine-tune ==="
echo "Logs: tail -f training.log  (in another tmux pane)"
accelerate launch -m axolotl.cli.train training/axolotl_config.yml 2>&1 | tee training.log

echo ""
echo "=== Done! ==="
echo "Adapter saved to: /workspace/qwen3-27b-story-director/"
echo "Pack and download: tar czf adapter.tar.gz /workspace/qwen3-27b-story-director/"
