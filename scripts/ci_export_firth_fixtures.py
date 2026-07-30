"""
scripts/ci_export_firth_fixtures.py

Exports the three shared Firth validation fixtures
(lib/dataset2/firth_logistic_fixtures.py) as CSVs an R script can read,
and runs THIS project's own Python Firth implementation
(lib/dataset2/firth_logistic.py) on each, exporting its coefficients,
profile-likelihood 95% CIs, and penalized likelihood-ratio p-values as
a comparison baseline. scripts/firth_crosscheck.R fits the SAME data
with R's `logistf` package; scripts/ci_compare_firth_crosscheck.py
then diffs the two.

Run as part of the "Independent Firth Cross-Check" GitHub Actions job
(.github/workflows/fetch_schedules_and_firth_crosscheck.yml) -- not
meant to run standalone outside CI, though it has no real external
dependency itself (pure computation on the fixtures).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
from lib.dataset2.firth_logistic import fit_firth_logistic, firth_lr_test, firth_profile_ci
from lib.dataset2.firth_logistic_fixtures import FIXTURES

OUTPUT_DIR = Path("data/exports/firth_crosscheck")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    python_rows = []

    for name, builder in FIXTURES.items():
        X, y, columns = builder()
        df = pd.DataFrame(X[:, 1:], columns=columns[1:])  # drop intercept column -- R's formula adds its own
        df["y"] = y.astype(int)
        data_path = OUTPUT_DIR / f"fixture_{name}.csv"
        df.to_csv(data_path, index=False)
        print(f"Wrote {data_path} ({len(df)} rows, columns={columns})")

        fit = fit_firth_logistic(X, y)
        for j, col in enumerate(columns):
            lower, upper, _ = firth_profile_ci(X, y, coef_index=j)
            lr_stat, p_value, _, _ = firth_lr_test(X, y, coef_index=j)
            python_rows.append(
                {
                    "fixture": name,
                    "term": col,
                    "python_coef": fit.beta[j],
                    "python_se_wald": fit.se[j],
                    "python_ci_lower_profile": lower,
                    "python_ci_upper_profile": upper,
                    "python_lr_stat": lr_stat,
                    "python_lr_pvalue": p_value,
                    "python_converged": fit.converged,
                    "python_n_iter": fit.n_iter,
                }
            )

    python_results = pd.DataFrame(python_rows)
    results_path = OUTPUT_DIR / "python_firth_results.csv"
    python_results.to_csv(results_path, index=False)
    print(f"\nWrote {results_path}")
    print(python_results.to_string())


if __name__ == "__main__":
    main()
