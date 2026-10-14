"""Upload `data/` (without the API caches) to the Hugging Face Hub as a dataset.

`data/README.md` is the dataset card. A new dataset starts private. Re-uploads keep the current
visibility unless `--visibility public` or `--visibility private` is passed. An `HF_TOKEN` in `.env`
takes precedence over the token stored by `hf auth login`.
"""

import argparse
import logging

from dotenv import load_dotenv
from huggingface_hub import HfApi

from swiss_ai.paths import DATA, ROOT

log = logging.getLogger(__name__)

REPO_ID = "joelniklaus/swiss-ai-research"
IGNORE = ["cache/**", "**/.DS_Store"]


def publish(visibility: str | None = None) -> str:
    """Create the dataset repo if needed, optionally set its visibility, and upload the tables.

    Args:
        visibility: "public" or "private" to change the visibility; None keeps it as it is.

    Returns:
        The URL of the dataset.
    """
    api = HfApi()
    api.create_repo(REPO_ID, repo_type="dataset", private=True, exist_ok=True)
    if visibility is not None:
        api.update_repo_settings(
            REPO_ID, repo_type="dataset", private=visibility == "private"
        )
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
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--visibility",
        choices=["public", "private"],
        help="change the dataset visibility (default: keep it)",
    )
    args = parser.parse_args()
    log.info(f"Uploaded to {publish(args.visibility)} (visibility={args.visibility})")


if __name__ == "__main__":
    main()
