"""
tests/test_no_isolated_research_dependency.py

Structural guarantee added 2026-07 after the provenance audit found a
real bug: scripts/2025_adp_integration.py read
research/diagnostics/mfl_pipeline/output/adp_all_non_keeper.csv --
an EXPLICITLY ISOLATED research artifact (see that pipeline's own
README: "never wired into the canonical ADP pipeline and not used by
anything under scripts/") -- and fed it into overall_adp for every
2025 row, instead of the real MFL AUG15 production cache.

That bug was a plain string path constant
(`MFL_RAW_PATH = REPO_ROOT / "research/diagnostics/mfl_pipeline/..."`),
NOT an import statement -- so an ast.Import-only check (the pattern
already used elsewhere in this suite, e.g.
tests/test_expected_production.py::TestNoResearchImports) would NOT
have caught it. This test scans every real STRING LITERAL used as
code (assignments, function-call arguments, f-strings, etc.) across
scripts/ and lib/, not just import statements -- while still excluding
genuine docstrings, which legitimately discuss this exact incident by
path name now (see 2025_adp_integration.py's own module docstring).
Naive `"research" not in line` string-matching would false-positive on
those docstrings -- this project already hit that mistake once (see
test_expected_production.py's own docstring) and fixes it here the
same way: parse real AST nodes, exclude docstring Expr statements by
node identity, not by guessing at line content.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_SUBSTRING = "research/diagnostics/mfl_pipeline"

PRODUCTION_FILES = sorted(
    list((REPO_ROOT / "scripts").glob("*.py"))
    + list((REPO_ROOT / "lib").rglob("*.py"))
)


def _docstring_node_ids(tree: ast.AST) -> set:
    """Identifies the AST Constant nodes that are genuine docstrings
    (the first statement of a Module/FunctionDef/AsyncFunctionDef/
    ClassDef body, when that statement is a bare string expression) --
    by node identity (id()), not by string content, so a real
    docstring can legitimately mention any path it wants."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    ids.add(id(value))
    return ids


class TestNoLiveStringReferencesIsolatedResearchPipeline:
    @pytest.mark.parametrize("path", PRODUCTION_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_no_live_code_string_references_isolated_pipeline_path(self, path):
        source = path.read_text()
        tree = ast.parse(source, filename=str(path))
        docstring_ids = _docstring_node_ids(tree)

        offending = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in docstring_ids:
                    continue  # genuine docstring prose -- allowed to discuss this by name
                if FORBIDDEN_SUBSTRING in node.value:
                    offending.append(node.value)

        assert not offending, (
            f"{path.relative_to(REPO_ROOT)} has live code referencing "
            f"{FORBIDDEN_SUBSTRING!r} outside a docstring: {offending!r} -- "
            f"that directory is an explicitly isolated research artifact and "
            f"must never feed a canonical field again (see this test module's "
            f"docstring for the 2026-07 incident this guards against)."
        )


class TestNoImportsFromIsolatedResearchPipeline:
    """Belt-and-suspenders alongside the string-literal scan above --
    catches the OTHER way a dependency could be introduced (an actual
    import statement), matching the existing
    tests/test_expected_production.py::TestNoResearchImports /
    tests/test_mfl_2025_adp_correction.py::TestNoForbiddenImports
    convention used elsewhere in this suite."""

    @pytest.mark.parametrize("path", PRODUCTION_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
    def test_no_import_of_research_diagnostics_mfl_pipeline(self, path):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "mfl_pipeline" not in alias.name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "mfl_pipeline" not in module


class TestSanityOnTheScanItself:
    """If this fails, the scan above is silently checking zero files --
    a passing test suite that scans nothing would be worse than no
    test at all."""

    def test_production_files_list_is_non_empty(self):
        assert len(PRODUCTION_FILES) > 10

    def test_2025_adp_integration_is_included_in_the_scan(self):
        relpaths = {str(p.relative_to(REPO_ROOT)) for p in PRODUCTION_FILES}
        assert "scripts/2025_adp_integration.py" in relpaths

    def test_the_forbidden_substring_check_actually_detects_a_real_violation(self):
        """Proves the scan mechanism itself works -- a synthetic
        module with a live (non-docstring) reference to the isolated
        path must be flagged."""
        source = (
            'MFL_RAW_PATH = "research/diagnostics/mfl_pipeline/output/adp_all_non_keeper.csv"\n'
        )
        tree = ast.parse(source)
        docstring_ids = _docstring_node_ids(tree)
        found = any(
            isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstring_ids and FORBIDDEN_SUBSTRING in node.value
            for node in ast.walk(tree)
        )
        assert found, "the detection logic itself failed to catch a known-bad synthetic example"

    def test_the_docstring_exclusion_actually_exempts_a_real_docstring(self):
        """Proves the exclusion mechanism doesn't just happen to never
        fire -- a synthetic module whose ONLY reference is inside its
        own docstring must NOT be flagged."""
        source = (
            '"""This module discusses research/diagnostics/mfl_pipeline by name, in prose."""\n'
            "x = 1\n"
        )
        tree = ast.parse(source)
        docstring_ids = _docstring_node_ids(tree)
        offending = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstring_ids and FORBIDDEN_SUBSTRING in node.value
        ]
        assert offending == [], "a genuine docstring mention was incorrectly flagged"
