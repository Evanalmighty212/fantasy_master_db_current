"""
run_pipeline.py

Runs the Fantasy Research Engine pipeline end-to-end, in order:

  01_download_adp.py         - pull raw ADP from current source(s)
  02_clean_adp.py             - normalize/dedupe ADP into one clean table   [not yet built]
  03_download_stats.py       - pull nflverse weekly data, build season PPR results
  04_build_master_dataset.py - join ADP + results into master DB            [not yet built]
  05_calculate_metrics.py    - compute League Winner Index + other metrics  [not yet built]
  06_generate_rankings.py    - produce ranking/analysis outputs             [not yet built]
  07_export_excel.py         - package everything into the final workbook   [not yet built]

Steps marked [not yet built] are stubs (see docs/VERSION_1_SCOPE.md for
what they need to do) and are skipped automatically until implemented.
"""

import importlib
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PIPELINE_STEPS = [
    "01_download_adp",
    "02_clean_adp",
    "03_download_stats",
    "04_build_master_dataset",
    "05_calculate_metrics",
    "06_generate_rankings",
    "07_export_excel",
]


def run_step(module_name):
    print(f"\n=== {module_name} ===")
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        print(f"  SKIPPED (import failed): {e}")
        return

    try:
        module.main()
    except NotImplementedError as e:
        print(f"  SKIPPED (not yet implemented): {e}")


def main():
    print("Fantasy Master Database Pipeline")
    for step in PIPELINE_STEPS:
        run_step(step)
    print("\nDone.")


if __name__ == "__main__":
    main()
