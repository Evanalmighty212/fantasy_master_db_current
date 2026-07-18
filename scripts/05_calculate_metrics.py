"lwi_component_coverage", "lwi_version", "lwi_config_fingerprint"]:
        if col not in ineligible.columns:
            ineligible[col] = None

    final = pd.concat([eligible, ineligible], ignore_index=True).sort_values(
        ["season", "overall_finish_ppr"]
    )

    print("Step 9: Writing output...")
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = MASTER_DIR / f"master_historical_db_with_lwi_{SEASONS[0]}_{SEASONS[-1]}.csv"
    final.to_csv(out_csv, index=False)
    try:
        final.to_excel(MASTER_DIR / f"master_historical_db_with_lwi_{SEASONS[0]}_{SEASONS[-1]}.xlsx", index=False)
    except Exception as e:
        print(f"  xlsx export skipped ({e})")

    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    elig_report = (
        master.groupby(["season", "lwi_eligibility_flag"]).size()
        .reset_index(name="row_count")
    )
    elig_report.to_csv(VALIDATION_DIR / "lwi_eligibility_report.csv", index=False)

    print(f"\nDone. {len(eligible)} rows scored, {len(ineligible)} rows ineligible.")
    print(f"Master DB with LWI -> {out_csv}")
    print(f"Eligibility report -> {VALIDATION_DIR / 'lwi_eligibility_report.csv'}")
    print(f"\nNOTE: Component 4 uses replacement-level rank thresholds "
          f"({REPLACEMENT_RANK_THRESHOLDS}) -- confirmed per "
          f"docs/METRIC_SPECIFICATION.md, sensitivity-tested against real "
          f"data (0.9996 rank correlation across the most divergent "
          f"candidate configurations tested).")

    return final


def main():
    calculate_lwi()


if __name__ == "__main__":
    main()
