import pytest

from swiss_ai import awards


@pytest.mark.parametrize(
    ("notes", "track"),
    [
        ("Outstanding Paper", "main"),
        ("Datasets & Benchmarks track", "datasets_benchmarks"),
        ("ICML Position Track award", "position"),
        ("Best demo paper (demo track)", "demo"),
        ("Best industry paper (industry track)", "industry"),
    ],
)
def test_track(notes: str, track: str) -> None:
    assert awards.track(notes) == track


def test_awards_csv_is_reproducible(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(awards, "AWARDS", tmp_path)
    awards.main()
    df = awards.pd.read_csv(tmp_path / "awards.csv", keep_default_na=False)
    assert len(df) > 600
    assert set(df.track) >= {"main", "demo", "industry"}
    assert (tmp_path / "swiss_first_authors.csv").exists()
