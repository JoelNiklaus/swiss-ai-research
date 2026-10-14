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


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> FakeApi:
    fake = FakeApi()
    monkeypatch.setattr(publish, "HfApi", lambda: fake)
    return fake


@pytest.mark.parametrize(
    ("visibility", "private"), [("public", False), ("private", True)]
)
def test_publish_sets_requested_visibility(
    api: FakeApi, visibility: str, private: bool
) -> None:
    url = publish.publish(visibility)
    assert url.endswith(publish.REPO_ID)
    calls = dict(api.calls)
    assert calls["update_repo_settings"]["private"] is private
    assert "cache/**" in calls["upload_folder"]["ignore_patterns"]
    assert calls["upload_folder"]["repo_type"] == "dataset"


def test_publish_keeps_visibility_by_default(api: FakeApi) -> None:
    publish.publish()
    assert "update_repo_settings" not in [name for name, _ in api.calls]
    # A new repo starts private; exist_ok leaves an existing repo's visibility alone.
    create = dict(api.calls)["create_repo"]
    assert create["private"] is True
    assert create["exist_ok"] is True
