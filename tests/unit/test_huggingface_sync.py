from orchestrator.export.huggingface import HuggingFaceSync


def test_push_uploads_or_replaces_local_daily_file():
    class FakeApi:
        def __init__(self):
            self.upload_args = None

        def upload_file(self, **kwargs):
            self.upload_args = kwargs

    api = FakeApi()
    sync = HuggingFaceSync(
        token="not-logged",
        repo_id="example/training-data",
        repo_type="dataset",
        api=api,
    )
    sync.push("training-2026-11-09.jsonl", "training-2026-11-09.jsonl")
    assert api.upload_args == {
        "path_or_fileobj": "training-2026-11-09.jsonl",
        "path_in_repo": "training-2026-11-09.jsonl",
        "repo_id": "example/training-data",
        "repo_type": "dataset",
        "commit_message": "Update training-2026-11-09.jsonl",
    }


def test_huggingface_sync_requires_repository_configuration():
    import pytest

    with pytest.raises(ValueError, match="token and repository ID"):
        HuggingFaceSync(token="", repo_id="")
