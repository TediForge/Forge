"""One-way upload of locally exported training JSONL files."""

from pathlib import Path
from typing import Any


class HuggingFaceSync:
    def __init__(
        self,
        token: str,
        repo_id: str,
        repo_type: str = "dataset",
        api: Any | None = None,
    ) -> None:
        if not token or not repo_id:
            raise ValueError("Hugging Face token and repository ID are required")
        if repo_type not in {"dataset", "model", "space"}:
            raise ValueError("Unsupported Hugging Face repository type")
        if api is None:
            from huggingface_hub import HfApi

            api = HfApi(token=token)
        self.api = api
        self.repo_id = repo_id
        self.repo_type = repo_type

    def push(self, local_path: str | Path, path_in_repo: str) -> None:
        self.api.upload_file(
            path_or_fileobj=str(local_path),
            path_in_repo=path_in_repo,
            repo_id=self.repo_id,
            repo_type=self.repo_type,
            commit_message=f"Update {path_in_repo}",
        )
