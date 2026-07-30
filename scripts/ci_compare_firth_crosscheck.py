"""
scripts/ci_compare_firth_crosscheck.py

Diffs data/exports/firth_crosscheck/python_firth_results.csv (this
project's own Firth implementation) against r_logistf_results.csv (R's
logistf, the independent reference implementation) across all three
fixtures (ordinary / sparse / complete_separation), reporting real,
per-term differences in coefficients, profile-likelihood CI bounds,
and LR-test p-values -- not just "did both run."

Run as the final step of the "Independent Firth Cross-Check" GitHub
Actions job, after ci_export_firth_fixtures.py and firth_crosscheck.R.
"""

import sys
from pathlib import Path

import pandas as pd

DIR = Path("data/exports/firth_crosscheck")

# Disagreement thresholds -- deliberately loose on coefficients/CIs
# (Firth implementations can differ slightly in convergence tolerance
# and step-halving details) but tight enough that a real algorithmic
# discrepancy would fail this, not just floating-point noise.
COEF_TOLERANCE = 0.05
CI_TOLERANCE = 0.10
PVALUE_TOLERANCE = 0.02


def main():
    py = pd.read_csv(DIR / "python_firth_results.csv")
    r = pd.read_csv(DIR / "r_logistf_results.csv")

    merged = py.merge(r, on=["fixture", "term"], how="outer", indicator=True)
    missing = merged[merged["_merge"] != "both"]
    if len(missing):
        print("WARNING: fixture/term rows present in only one implementation's output:")
        print(missing[["fixture", "term", "_merge"]].to_string())

    merged = merged[merged["_merge"] == "both"].copy()
    merged["coef_diff"] = (merged["python_coef"] - merged["r_coef"]).abs()
    merged["ci_lower_diff"] = (merged["python_ci_lower_profile"] - merged["r_ci_lower_profile"]).abs()
    merged["ci_upper_diff"] = (merged["python_ci_upper_profile"] - merged["r_ci_upper_profile"]).abs()
    merged["pvalue_diff"] = (merged["python_lr_pvalue"] - merged["r_lr_pvalue"]).abs()

    merged["coef_agree"] = merged["coef_diff"] <= COEF_TOLERANCE
    merged["ci_agree"] = (merged["ci_lower_diff"] <= CI_TOLERANCE) & (merged["ci_upper_diff"] <= CI_TOLERANCE)
    merged["pvalue_agree"] = merged["pvalue_diff"] <= PVALUE_TOLERANCE

    cols = [
        "fixture", "term", "python_coef", "r_coef", "coef_diff", "coef_agree",
        "python_ci_lower_profile", "r_ci_lower_profile", "ci_lower_diff",
        "python_ci_upper_profile", "r_ci_upper_profile", "ci_upper_diff", "ci_agree",
        "python_lr_pvalue", "r_lr_pvalue", "pvalue_diff", "pvalue_agree",
    ]
    report = merged[cols].sort_values(["fixture", "term"])
    report_path = DIR / "firth_crosscheck_comparison.csv"
    report.to_csv(report_path, index=False)

    print(report.to_string())
    print(f"\nWrote {report_path}")

    n_total = len(report)
    n_coef_disagree = (~report["coef_agree"]).sum()
    n_ci_disagree = (~report["ci_agree"]).sum()
    n_pvalue_disagree = (~report["pvalue_agree"]).sum()
    print(f"\n{n_total} term comparisons across {report['fixture'].nunique()} fixtures")
    print(f"Coefficient disagreements (>{COEF_TOLERANCE}): {n_coef_disagree}")
    print(f"CI disagreements (>{CI_TOLERANCE}): {n_ci_disagree}")
    print(f"LR p-value disagreements (>{PVALUE_TOLERANCE}): {n_pvalue_disagree}")

    if n_coef_disagree or n_ci_disagree or n_pvalue_disagree:
        print("\nRESULT: Python implementation and R logistf DISAGREE on at least one term -- investigate before trusting adjusted Star results.")
        sys.exit(1)
    else:
        print("\nRESULT: Python implementation and R logistf agree within tolerance on every term across all three fixtures.")


if __name__ == "__main__":
    main()
