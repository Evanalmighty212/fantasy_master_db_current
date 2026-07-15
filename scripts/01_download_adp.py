import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import json
import time

import pandas as pd
import requests

from config import SEASONS, SCORING_FORMATS, TEAMS, TOP_N_ADP

BASE_URL = "https://fantasyfootballcalculator.com/api/v1/adp/ppr"

RAW_DIR = Path("data/raw/adp")
OUT_DIR = Path("data/processed")


def download_adp():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_rows = []
    failures = []

    for year in SEASONS:
        for scoring in SCORING_FORMATS:
            print(f"Downloading ADP: {year} {scoring}")

            try:
                response = requests.get(
                    BASE_URL,
                    params={"year": year, "teams": TEAMS},
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                raw_path = RAW_DIR / f"ffc_adp_{year}_{scoring}.json"
                raw_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

                players = data.get("players", [])

                if not players:
                    failures.append({
                        "season": year,
                        "scoring_format": scoring,
                        "reason": "No players returned",
                    })
                    continue

                for p in players:
                    all_rows.append({
                        "season": year,
                        "scoring_format": scoring,
                        "teams": TEAMS,
                        "source": "FantasyFootballCalculator",
                        "player_name": p.get("name"),
                        "position": p.get("position"),
                        "team": p.get("team"),
                        "adp": p.get("adp"),
                        "adp_formatted": p.get("adp_formatted"),
                        "times_drafted": p.get("times_drafted"),
                        "high": p.get("high"),
                        "low": p.get("low"),
                        "stdev": p.get("stdev"),
                        "bye": p.get("bye"),
                    })

            except Exception as e:
                failures.append({
                    "season": year,
                    "scoring_format": scoring,
                    "reason": repr(e),
                })

            time.sleep(0.5)

    df = pd.DataFrame(all_rows)

    if not df.empty:
        df = df.sort_values(["season", "scoring_format", "adp"], na_position="last")
        df["adp_rank_within_season_format"] = (
            df.groupby(["season", "scoring_format"])["adp"]
            .rank(method="first", ascending=True)
            .astype("Int64")
        )
        top250 = df[df["adp_rank_within_season_format"] <= TOP_N_ADP].copy()
    else:
        top250 = df

    df.to_csv(OUT_DIR / "adp_all_downloaded_rows.csv", index=False)
    top250.to_csv(OUT_DIR / "adp_top250_first_pass.csv", index=False)
    pd.DataFrame(failures).to_csv(OUT_DIR / "adp_download_failures.csv", index=False)

    print("\nDone.")
    print(f"Total ADP rows downloaded: {len(df)}")
    print(f"Top-250 rows: {len(top250)}")
    print(f"Failures: {len(failures)}")

    return df, top250


def main():
    download_adp()


if __name__ == "__main__":
    main()
