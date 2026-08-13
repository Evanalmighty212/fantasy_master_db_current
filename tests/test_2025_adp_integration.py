"""Synthetic tests for the governed 2025 ADP production handoff."""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
SCRIPT_PATH = REPO_ROOT / "scripts" / "2025_adp_integration.py"


def load_module():
    spec = importlib.util.spec_from_file_location("adp_2025_integration", SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = load_module()


def _governed_rows():
    return pd.DataFrame([
        {
            "player_id": "1", "player_name_original": "Ja'Marr Chase", "position": "WR", "team": "CIN",
            "mfl_mean_adp": 2.0, "times_drafted": 100, "draft_selection_count": 100,
            "draft_selection_denominator": 147, "draft_selection_rate": 100 / 147,
            "mfl_reconstruction_identity": "strict-147-test",
        },
        {
            "player_id": "2", "player_name_original": "Josh Allen", "position": "QB", "team": "BUF",
            "mfl_mean_adp": 6.3, "times_drafted": 44, "draft_selection_count": 44,
            "draft_selection_denominator": 147, "draft_selection_rate": 44 / 147,
            "mfl_reconstruction_identity": "strict-147-test",
        },
    ])


def _mock_loader(monkeypatch):
    calls = {}
    def load(**kwargs):
        calls.update(kwargs)
        return _governed_rows()
    monkeypatch.setattr(MOD, "_load_governed_mfl_2025_adp", load)
    return calls


def _build(monkeypatch):
    calls = _mock_loader(monkeypatch)
    rows = MOD.build_2025_adp_clean_rows(
        archive_root=Path("/explicit/archive"), cache_root=Path("/explicit/cache"),
        manifest_path=Path("/explicit/manifest.json"),
    )
    return rows, calls


def test_explicit_governed_roots_are_forwarded(monkeypatch):
    _, calls = _build(monkeypatch)
    assert calls == {
        "archive_root": Path("/explicit/archive"),
        "cache_root": Path("/explicit/cache"),
        "manifest_path": Path("/explicit/manifest.json"),
    }


def test_clean_rows_preserve_participation_and_raw_mean_pick(monkeypatch):
    rows, _ = _build(monkeypatch)
    assert set(MOD.CANONICAL_COLUMNS).issubset(rows.columns)
    chase = rows.set_index("player_name_original").loc["Ja'Marr Chase"]
    assert chase["overall_adp"] == pytest.approx(2.0)
    assert chase["draft_selection_count"] == 100
    assert chase["draft_selection_denominator"] == 147
    assert chase["draft_selection_rate"] == pytest.approx(100 / 147)
    assert chase["mfl_reconstruction_identity"] == "strict-147-test"


def test_names_source_season_and_ranks_are_canonical(monkeypatch):
    import config
    rows, _ = _build(monkeypatch)
    assert set(rows["player_name_original"]) == {"Ja'Marr Chase", "Josh Allen"}
    assert (rows["season"] == 2025).all()
    assert (rows["source"] == config.MFL_2025_ADP_SOURCE).all()
    assert list(rows.sort_values("overall_adp")["adp_rank"]) == [1, 2]


def test_absent_player_is_not_created(monkeypatch):
    rows, _ = _build(monkeypatch)
    assert len(rows) == 2
    assert "Absent Player" not in set(rows["player_name_original"])


def test_amari_cooper_exclusion_remains_narrow(monkeypatch):
    governed = _governed_rows()
    governed.loc[len(governed)] = {
        "player_id": "3", "player_name_original": "Amari Cooper", "position": "WR", "team": "FA",
        "mfl_mean_adp": 156.6, "times_drafted": 10, "draft_selection_count": 10,
        "draft_selection_denominator": 147, "draft_selection_rate": 10 / 147,
        "mfl_reconstruction_identity": "strict-147-test",
    }
    monkeypatch.setattr(MOD, "_load_governed_mfl_2025_adp", lambda **kwargs: governed)
    rows = MOD.build_2025_adp_clean_rows(archive_root=Path("a"), cache_root=Path("c"))
    assert "Amari Cooper" not in set(rows["player_name_original"])
    assert len(rows) == 2


def test_integrate_refuses_duplicate_2025_before_loading_package(tmp_path, monkeypatch):
    existing = pd.DataFrame([{"season": 2025}])
    path = tmp_path / "adp_clean.csv"
    existing.to_csv(path, index=False)
    monkeypatch.setattr(MOD, "ADP_CLEAN_PATH", path)
    monkeypatch.setattr(MOD, "_load_governed_mfl_2025_adp", lambda **kwargs: pytest.fail("must not load"))
    with pytest.raises(RuntimeError, match="already has 2025 rows"):
        MOD.integrate(archive_root=tmp_path, cache_root=tmp_path)
