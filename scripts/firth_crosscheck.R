# scripts/firth_crosscheck.R
#
# Independent cross-check for lib/dataset2/firth_logistic.py, using
# R's `logistf` package (Heinze & Schemper's own reference
# implementation of Firth's method, and the standard R package cited
# throughout the Firth logistic-regression literature this project's
# implementation is built from). Reads the three fixture CSVs written
# by scripts/ci_export_firth_fixtures.py (ordinary / sparse /
# complete_separation -- identical data to the Python implementation's
# own internal validation suite, tests/test_firth_logistic.py, via the
# shared lib/dataset2/firth_logistic_fixtures.py generators), fits
# logistf() on each, and writes coefficients, profile-likelihood 95%
# CIs, and penalized likelihood-ratio p-values to a CSV in the SAME
# shape as python_firth_results.csv so
# scripts/ci_compare_firth_crosscheck.py can diff them directly.
#
# Run only inside the "Independent Firth Cross-Check" GitHub Actions
# job -- this sandbox has no R interpreter (checked directly, see
# tests/test_firth_logistic.py's TestIndependentImplementationCrossCheck
# skip reason).

if (!requireNamespace("logistf", quietly = TRUE)) {
  install.packages("logistf", repos = "https://cloud.r-project.org")
}
library(logistf)

fixtures_dir <- "data/exports/firth_crosscheck"
fixtures <- list(
  ordinary = c("x1", "x2"),
  sparse = c("x1_continuous", "x2_boolean"),
  complete_separation = c("x_separating", "x_noise")
)

results <- data.frame()

for (fixture_name in names(fixtures)) {
  terms <- fixtures[[fixture_name]]
  data_path <- file.path(fixtures_dir, paste0("fixture_", fixture_name, ".csv"))
  df <- read.csv(data_path)

  formula_str <- paste("y ~", paste(terms, collapse = " + "))
  fit <- logistf(as.formula(formula_str), data = df, pl = TRUE)

  # logistf's own coefficient vector includes "(Intercept)" first,
  # then each term in formula order -- matches
  # python_firth_results.csv's row order (intercept, then terms).
  coef_names <- c("intercept", terms)
  for (i in seq_along(coef_names)) {
    term_label <- coef_names[i]
    # LR test for this specific coefficient: logistf's own
    # profile-likelihood-based p-value (fit$prob), which is exactly
    # the penalized LR test this project's Python implementation also
    # uses -- not a Wald z-test, matching instruction's requirement to
    # compare LR-based significance, not just coefficients.
    row <- data.frame(
      fixture = fixture_name,
      term = term_label,
      r_coef = fit$coefficients[i],
      r_ci_lower_profile = fit$ci.lower[i],
      r_ci_upper_profile = fit$ci.upper[i],
      r_lr_pvalue = fit$prob[i],
      r_converged = fit$iter[1] < fit$maxit
    )
    results <- rbind(results, row)
  }
}

dir.create(fixtures_dir, showWarnings = FALSE, recursive = TRUE)
out_path <- file.path(fixtures_dir, "r_logistf_results.csv")
write.csv(results, out_path, row.names = FALSE)
cat("Wrote", out_path, "\n")
print(results)
