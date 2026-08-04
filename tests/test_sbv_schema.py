"""
tests/test_sbv_schema.py

Covers lib/stars_by_value/schema.py -- the data-dictionary generator
for the canonical SBV output (data/exports/
stars_by_value_player_seasons_SCHEMA.md), added 2026-07 after finding
config.SBV_OUTPUT_CSV_SCHEMA_PATH was declared and its extension
checked by validate_sbv_config(), but nothing anywhere in the
committed codebase ever actually wrote to it.

TestSchemaMatchesRealLabelRowsOutput is the most important class here:
it runs a REAL (small, synthetic) labeling.label_rows() call plus the
exact same identity-column merge 11_calculate_stars_by_value.py's
run_label_rows() performs, and proves every column in that real output
appears EXACTLY ONCE in schema.COLUMN_DOCS -- not by trusting
labeling.OUTPUT_COLUMNS alone (which schema.py already depends on) but
by exercising the real code path that produces canonical rows.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from lib.stars_by_value import labeling
from lib.stars_by_value import schema as sbv_schema


def _ep_lookup(*rows):
    cols = list((
        "prediction_season", "position", "draft_round", "expected_production",
        "positional_offset_applied", "recency_weighted", "half_life_years",
        "sample_size", "sbv_version", "fit_timestamp",
    ))
    defaults = {
        "positional_offset_applied": None, "recency_weighted": False,
        "half_life_years": None, "sample_size": 100,
        "sbv_version": config.SBV_VERSION, "fit_timestamp": pd.Timestamp.now(tz="UTC"),
    }
    full_rows = []
    for r in rows:
        row = dict(defaults)
        row.update(r)
        full_rows.append(row)
    return pd.DataFrame(full_rows, columns=cols)


def _row(**overrides):
    base = {
        "season": 2020, "player_id": "00-1", "player_name": "Test Player", "position": "WR",
        "historical_input_revision": config.HISTORICAL_INPUT_REVISION,
        "games_played": 12, "P": 300.0, "data_quality_flag": "matched_clean", "adp_round": 3,
    }
    base.update(overrides)
    return base


def _real_canonical_shaped_output():
    """Reproduces the EXACT column-shaping run_label_rows() performs
    in scripts/11_calculate_stars_by_value.py: label_rows()'s own
    output columns, left-merged onto the identity columns
    (season, player_id, player_name, position, historical input revision)
    from the source rows.
    Returns (canonical_df, audit_df) -- label_rows() now returns both
    (Option 3A, 2026-07). None of these 3 fixture rows have a
    provenance requiring an audit row, so audit_df is empty here."""
    lookup = _ep_lookup(
        {"prediction_season": 2020, "position": "WR", "draft_round": 3, "expected_production": 100.0},
    )
    rows = pd.DataFrame([
        _row(season=2020, player_id="00-a", position="WR", P=300.0),  # adp_scored
        _row(season=2005, player_id="00-b", position="WR"),  # out_of_scope
        _row(season=2020, player_id="00-c", position="WR", P=0.0),  # below_production_gate
    ])
    result, audit_df = labeling.label_rows(rows, lookup)
    canonical_df = rows[["season", "player_id", "player_name", "position", "historical_input_revision"]].merge(
        result, on=["season", "player_id"], how="inner",
    )
    return canonical_df, audit_df


class TestSchemaColumnsWellFormed:
    def test_column_docs_have_unique_names(self):
        names = [c["name"] for c in sbv_schema.COLUMN_DOCS]
        assert len(names) == len(set(names))

    def test_every_entry_has_required_keys(self):
        required_keys = {
            "name", "dtype", "nullable", "enum_values", "description",
            "populated_when", "null_when", "safe_for_modeling", "provenance_notes",
        }
        for col in sbv_schema.COLUMN_DOCS:
            assert required_keys <= set(col.keys()), f"{col.get('name')} missing keys"

    def test_dtype_and_description_fields_are_non_empty_strings(self):
        for col in sbv_schema.COLUMN_DOCS:
            assert isinstance(col["dtype"], str) and col["dtype"]
            assert isinstance(col["description"], str) and col["description"]
            assert isinstance(col["populated_when"], str) and col["populated_when"]
            assert isinstance(col["null_when"], str) and col["null_when"]
            assert isinstance(col["safe_for_modeling"], str) and col["safe_for_modeling"]

    def test_expected_columns_is_derived_from_labeling_output_columns(self):
        """EXPECTED_COLUMNS must not be an independently hand-maintained
        list -- it has to be built FROM labeling.OUTPUT_COLUMNS, the
        real committed source of truth, or it can drift silently."""
        for col in labeling.OUTPUT_COLUMNS:
            assert col in sbv_schema.EXPECTED_COLUMNS

    def test_column_docs_names_match_expected_columns_exactly(self):
        documented = {c["name"] for c in sbv_schema.COLUMN_DOCS}
        assert documented == set(sbv_schema.EXPECTED_COLUMNS)


class TestValidateSchemaMatchesColumns:
    def test_passes_for_the_real_expected_columns(self):
        sbv_schema.validate_schema_matches_columns(list(sbv_schema.EXPECTED_COLUMNS))  # must not raise

    def test_raises_when_a_documented_column_is_missing_from_output(self):
        actual = [c for c in sbv_schema.EXPECTED_COLUMNS if c != "star_by_value_score"]
        with pytest.raises(RuntimeError, match="MISSING from real output"):
            sbv_schema.validate_schema_matches_columns(actual)
        with pytest.raises(RuntimeError, match="star_by_value_score"):
            sbv_schema.validate_schema_matches_columns(actual)

    def test_raises_when_output_has_an_undocumented_extra_column(self):
        actual = list(sbv_schema.EXPECTED_COLUMNS) + ["some_new_column_nobody_documented"]
        with pytest.raises(RuntimeError, match="UNDOCUMENTED in schema.py"):
            sbv_schema.validate_schema_matches_columns(actual)
        with pytest.raises(RuntimeError, match="some_new_column_nobody_documented"):
            sbv_schema.validate_schema_matches_columns(actual)

    def test_raises_for_both_problems_at_once(self):
        actual = [c for c in sbv_schema.EXPECTED_COLUMNS if c != "position"] + ["mystery_column"]
        with pytest.raises(RuntimeError) as exc_info:
            sbv_schema.validate_schema_matches_columns(actual)
        message = str(exc_info.value)
        assert "position" in message
        assert "mystery_column" in message


class TestSchemaMatchesRealLabelRowsOutput:
    """The critical, explicitly-requested guarantee: every column the
    REAL canonical output shape produces (via an actual label_rows()
    call plus the real identity-column merge) appears exactly once in
    the documented schema -- not derived from OUTPUT_COLUMNS a second
    time, but from independently exercising the real code path."""

    def test_every_real_output_column_is_documented_exactly_once(self):
        real_df, _audit_df = _real_canonical_shaped_output()
        documented_names = [c["name"] for c in sbv_schema.COLUMN_DOCS]

        for col in real_df.columns:
            assert documented_names.count(col) == 1, (
                f"{col!r} appears {documented_names.count(col)} times in COLUMN_DOCS, expected exactly 1"
            )

    def test_no_documented_column_is_absent_from_real_output(self):
        real_df, _audit_df = _real_canonical_shaped_output()
        real_columns = set(real_df.columns)
        documented_names = {c["name"] for c in sbv_schema.COLUMN_DOCS}
        assert documented_names == real_columns

    def test_validate_schema_matches_columns_accepts_the_real_output(self):
        real_df, _audit_df = _real_canonical_shaped_output()
        sbv_schema.validate_schema_matches_columns(real_df.columns.tolist())  # must not raise


class TestRunLabelRowsMergeShapeUnchanged:
    """Structural pin on 11_calculate_stars_by_value.py's run_label_rows()
    -- if its identity-column merge ever changes, this test (and the
    schema derived from it) needs a matching update, not a silent drift."""

    def test_run_label_rows_merges_exactly_the_expected_identity_columns(self):
        import inspect
        import importlib.util
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "11_calculate_stars_by_value.py"
        spec = importlib.util.spec_from_file_location("calc_sbv_schema_check", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        source = inspect.getsource(mod.run_label_rows)
        assert '["season", "player_id", "player_name", "position", "historical_input_revision"]' in source


class TestRenderSchemaMarkdownContent:
    def test_every_column_name_appears_in_rendered_markdown(self):
        md = sbv_schema.render_schema_markdown()
        for col in sbv_schema.COLUMN_DOCS:
            assert f"`{col['name']}`" in md

    def test_all_statuses_and_provenance_types_appear(self):
        md = sbv_schema.render_schema_markdown()
        for status in config.SBV_STATUSES:
            assert status in md
        for provenance in config.SBV_PROVENANCE_TYPES:
            assert provenance in md

    def test_star_by_value_status_and_provenance_type_are_covered(self):
        md = sbv_schema.render_schema_markdown()
        assert "## `star_by_value_status`" in md
        assert "## `star_by_value_provenance_type`" in md

    def test_score_and_label_nullable_behavior_is_documented(self):
        md = sbv_schema.render_schema_markdown()
        assert "## `star_by_value_score`" in md
        assert "## `star_by_value_label`" in md
        assert "adp_scored" in md
        assert "minimal_market_cost_scored" in md
        assert "IS NOT NULL" in md  # the documented downstream-modeling filter

    def test_production_gate_threshold_distinguished_from_star_threshold(self):
        md = sbv_schema.render_schema_markdown()
        assert "## `star_by_value_production_gate_threshold`" in md
        assert "## `star_by_value_threshold`" in md
        assert "FIRST bar" in md or "production gate" in md
        assert "FINAL Star cutoff" in md or "final Star" in md.lower()

    def test_evidence_notes_spec_gap_is_disclosed_not_hidden(self):
        md = sbv_schema.render_schema_markdown()
        assert "star_by_value_evidence_notes" in md
        assert "Known gaps" in md
        # Must NOT render it as if it were a real, documented column
        assert "## `star_by_value_evidence_notes`" not in md


class TestWriteCanonicalOutputWritesSchema:
    """Integration-level: exercises the real
    11_calculate_stars_by_value.py write path with monkeypatched
    output paths, proving all three artifacts land and that a schema
    drift blocks writing anything at all."""

    def _load_module(self):
        import importlib.util
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "11_calculate_stars_by_value.py"
        spec = importlib.util.spec_from_file_location("calc_sbv_write_check", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_writes_parquet_csv_schema_and_audit_together(self, tmp_path, monkeypatch):
        mod = self._load_module()
        monkeypatch.setattr(mod.config, "SBV_OUTPUT_PARQUET_PATH", "out.parquet")
        monkeypatch.setattr(mod.config, "SBV_OUTPUT_CSV_EXPORT_PATH", "out.csv")
        monkeypatch.setattr(mod.config, "SBV_OUTPUT_CSV_SCHEMA_PATH", "out_SCHEMA.md")
        monkeypatch.setattr(mod.config, "SBV_EVIDENCE_AUDIT_PATH", "out_evidence_audit.csv")
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

        real_df, audit_df = _real_canonical_shaped_output()
        mod.write_canonical_output(real_df, audit_df)

        assert (tmp_path / "out.parquet").exists()
        assert (tmp_path / "out.csv").exists()
        assert (tmp_path / "out_SCHEMA.md").exists()
        assert (tmp_path / "out_evidence_audit.csv").exists()
        assert "star_by_value_status" in (tmp_path / "out_SCHEMA.md").read_text()

    def test_schema_drift_blocks_writing_any_file(self, tmp_path, monkeypatch):
        mod = self._load_module()
        monkeypatch.setattr(mod.config, "SBV_OUTPUT_PARQUET_PATH", "out.parquet")
        monkeypatch.setattr(mod.config, "SBV_OUTPUT_CSV_EXPORT_PATH", "out.csv")
        monkeypatch.setattr(mod.config, "SBV_OUTPUT_CSV_SCHEMA_PATH", "out_SCHEMA.md")
        monkeypatch.setattr(mod.config, "SBV_EVIDENCE_AUDIT_PATH", "out_evidence_audit.csv")
        monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

        real_df, audit_df = _real_canonical_shaped_output()
        bad_df = real_df.copy()
        bad_df["a_totally_new_undocumented_column"] = 1

        with pytest.raises(RuntimeError, match="UNDOCUMENTED in schema.py"):
            mod.write_canonical_output(bad_df, audit_df)

        assert not (tmp_path / "out.parquet").exists()
        assert not (tmp_path / "out.csv").exists()
        assert not (tmp_path / "out_SCHEMA.md").exists()
        assert not (tmp_path / "out_evidence_audit.csv").exists()

        assert not (tmp_path / "out.parquet").exists()
        assert not (tmp_path / "out.csv").exists()
        assert not (tmp_path / "out_SCHEMA.md").exists()
