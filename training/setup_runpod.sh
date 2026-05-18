#!/bin/bash
# One-command setup for Vast.ai 8x A100 PCIE 80GB pod
# Run: bash setup_runpod.sh
# Assumes: PyTorch 2.x image (e.g. runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel)

set -e

echo "=== Step 1/5: Installing Axolotl + Unsloth ==="
pip install -q axolotl[flash-attn,deepspeed]
pip install -q unsloth

echo "=== Step 2/5: Configuring accelerate for 8 GPUs ==="
mkdir -p ~/.cache/huggingface/accelerate
cat > ~/.cache/huggingface/accelerate/default_config.yaml <<EOF
compute_environment: LOCAL_MACHINE
distributed_type: MULTI_GPU
downcast_bf16: 'no'
gpu_ids: all
machine_rank: 0
main_training_function: main
mixed_precision: bf16
num_machines: 1
num_processes: 8
rdzv_backend: static
same_network: true
tpu_env: []
tpu_use_cluster: false
tpu_use_sudo: false
use_cpu: false
EOF

echo "=== Step 3/5: Cloning repo ==="
cd /workspace
if [ ! -d ytllm ]; then
  git clone https://github.com/deepak-glitch/ytllm.git
fi
cd ytllm
git pull

echo "=== Step 4/5: Converting dataset to ShareGPT format ==="
python training/convert_to_sharegpt.py
cp training/training_data_sharegpt.jsonl /workspace/training_data_sharegpt.jsonl

echo "=== Step 5/5: Starting QLoRA fine-tune on 8 GPUs ==="
# Watch logs: tail -f training.log  (in another tmux pane)
accelerate launch --num_processes=8 --multi_gpu \
  -m axolotl.cli.train training/axolotl_config.yml 2>&1 | tee training.log

echo "=== Done. Adapter saved to /workspace/qwen3-27b-story-director/ ==="
echo "Download with: tar czf adapter.tar.gz /workspace/qwen3-27b-story-director/"
