"""Upload `data/` (without the API caches) to the Hugging Face Hub as a dataset.

`data/README.md` is the dataset card. The dataset is created private; pass `--public` once
the blog post is out.
"""

import argparse
import logging

from huggingface_hub import HfApi

from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

REPO_ID = "joelniklaus/swiss-ai-research"
IGNORE = ["cache/**", "**/.DS_Store"]


def publish(public: bool) -> str:
    """Create the dataset repo if needed, set its visibility and upload the tables.

    Returns:
        The URL of the dataset.
    """
    api = HfApi()
    api.create_repo(REPO_ID, repo_type="dataset", private=not public, exist_ok=True)
    api.update_repo_settings(REPO_ID, repo_type="dataset", private=not public)
    api.upload_folder(
        folder_path=DATA,
        repo_id=REPO_ID,
        repo_type="dataset",
        ignore_patterns=IGNORE,
        commit_message="Update data tables",
    )
    return f"https://huggingface.co/datasets/{REPO_ID}"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", action="store_true", help="make the dataset public")
    args = parser.parse_args()
    log.info(f"Uploaded to {publish(args.public)} (public={args.public})")


if __name__ == "__main__":
    main()
