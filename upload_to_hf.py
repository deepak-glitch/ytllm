"""
Upload training_data_v6.jsonl to HuggingFace as a private dataset.

One-time setup on your laptop:
  pip install huggingface_hub
  huggingface-cli login        # paste a token from https://huggingface.co/settings/tokens

Run:
  python3 upload_to_hf.py

The dataset lives at:
  https://huggingface.co/datasets/Deepak0070/ytllm-story-director

Add later versions by changing FILES below; each file is just uploaded
into the same repo, so v6/v7/... coexist.
"""
from huggingface_hub import HfApi

REPO_ID = "Deepak0070/ytllm-story-director"
FILES = [
    "training_data_v6.jsonl",
]

api = HfApi()
api.create_repo(REPO_ID, repo_type="dataset", private=True, exist_ok=True)
for f in FILES:
    print(f"Uploading {f} ...")
    api.upload_file(
        path_or_fileobj=f,
        path_in_repo=f,
        repo_id=REPO_ID,
        repo_type="dataset",
    )
print(f"\nDone. https://huggingface.co/datasets/{REPO_ID}")
