import pytest

from swiss_ai import publish


class FakeApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def create_repo(self, repo_id: str, **kwargs: object) -> None:
        self.calls.append(("create_repo", {"repo_id": repo_id, **kwargs}))

    def update_repo_settings(self, repo_id: str, **kwargs: object) -> None:
        self.calls.append(("update_repo_settings", {"repo_id": repo_id, **kwargs}))

    def upload_folder(self, **kwargs: object) -> None:
        self.calls.append(("upload_folder", kwargs))


@pytest.mark.parametrize("public", [False, True])
def test_publish_sets_visibility_and_skips_cache(
    monkeypatch: pytest.MonkeyPatch, public: bool
) -> None:
    api = FakeApi()
    monkeypatch.setattr(publish, "HfApi", lambda: api)
    url = publish.publish(public)
    assert url.endswith(publish.REPO_ID)
    calls = dict(api.calls)
    assert calls["create_repo"]["private"] is (not public)
    assert calls["update_repo_settings"]["private"] is (not public)
    assert "cache/**" in calls["upload_folder"]["ignore_patterns"]
    assert calls["upload_folder"]["repo_type"] == "dataset"
