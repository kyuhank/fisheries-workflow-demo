# Present saved results only; calculation modules are never sourced here.
report_scalar <- function(value) {
  if (is.null(value)) return("")
  if (is.numeric(value) && length(value) == 1L) {
    return(format(signif(value, 4), trim = TRUE, scientific = abs(value) > 0 && abs(value) < 0.001))
  }
  if (length(value) == 1L && !is.list(value)) return(as.character(value))
  as.character(jsonlite::toJSON(value, auto_unbox = TRUE, null = "null", digits = NA))
}

report_table <- function(rows, columns = NULL, limit = NULL) {
  cat("\n\n")
  if (!length(rows)) { cat("No saved rows are available.\n\n"); return(invisible(NULL)) }
  if (is.null(columns)) {
    fields <- unique(unlist(lapply(rows, names)))
    columns <- setNames(gsub("_", " ", fields), fields)
  }
  if (!is.null(limit)) rows <- head(rows, limit)
  values <- lapply(names(columns), function(field) {
    vapply(rows, function(row) report_scalar(row[[field]]), character(1))
  })
  frame <- as.data.frame(setNames(values, unname(columns)), check.names = FALSE,
                         stringsAsFactors = FALSE)
  cat(as.character(knitr::kable(frame, format = if (knitr::is_html_output()) "html" else "pipe",
                                row.names = FALSE)), sep = "\n")
  cat("\n\n")
}

report_fields <- function(value, fields) {
  present <- intersect(names(fields), names(value))
  if (!length(present)) return(invisible(NULL))
  report_table(lapply(present, function(field) list(item = fields[[field]], value = value[[field]])),
               c(item = "Item", value = "Value"))
}

report_has <- function(rows, field) {
  length(rows) > 0L && all(vapply(rows, function(row) {
    value <- row[[field]]
    is.numeric(value) && length(value) == 1L && is.finite(value)
  }, logical(1)))
}

report_years <- function(rows) {
  if (!report_has(rows, "year")) return("")
  years <- range(vapply(rows, function(row) row$year, numeric(1)))
  if (diff(years) == 0) as.character(years[1]) else paste(years, collapse = "–")
}

report_header <- function(title, record, rows = NULL) {
  cat("# ", title, "\n\n", sep = "")
  metadata <- character()
  if (!is.null(record$owner)) metadata <- c(metadata, paste0("**", record$owner, "**"))
  if (!is.null(record$run_id)) metadata <- c(metadata, record$run_id)
  years <- report_years(rows)
  if (nzchar(years)) metadata <- c(metadata, paste("Years", years)) else if (!is.null(record$snapshot)) {
    metadata <- c(metadata, paste("Data through", record$snapshot))
  }
  if (length(metadata)) cat(paste(metadata, collapse = " · "), "\n\n", sep = "")
  calculation <- record$execution$calculation
  if (is.list(calculation) && isTRUE(calculation$exit_code == 0)) {
    cat("Calculation finished (container exit 0).\n\n")
  }
}

report_inputs <- function(record) {
  inputs <- record$inputs
  if (!length(inputs)) return(invisible(NULL))
  rows <- lapply(names(inputs), function(key) {
    input <- inputs[[key]]
    title <- if (is.null(input$title)) gsub("_", " ", key) else input$title
    owner <- if (is.null(input$owner)) "—" else input$owner
    list(input = title, analyst = owner,
         run = if (is.null(input$run_id)) "—" else input$run_id)
  })
  cat("**Inputs used**\n")
  report_table(rows, c(input = "Input", analyst = "Analyst", run = "Produced in"))
}

report_plot <- function(series, field, label, points = character(), upper = NULL, reference = NULL) {
  panel_title <- attr(series, "panel_title")
  valid <- vapply(series, function(rows) report_has(rows, "year") && report_has(rows, field), logical(1))
  series <- series[valid]
  if (!length(series)) { cat("No saved values are available for this plot.\n\n"); return(invisible(NULL)) }
  years <- unlist(lapply(series, function(rows) vapply(rows, function(row) row$year, numeric(1))))
  values <- unlist(lapply(series, function(rows) vapply(rows, function(row) row[[field]], numeric(1))))
  scale <- if (field == "catch_t" && max(abs(c(values, upper))) >= 10000) 1000 else 1
  if (scale == 1000) label <- sub("t/y", "1,000 t/y", label, fixed = TRUE)
  values <- values / scale
  if (!is.null(upper)) upper <- upper / scale
  palette <- c("#17688a", "#b56536", "#786093", "#328363", "#a7526d", "#93761e")
  fixed <- c("Constant catch" = "#17688a", "Index rule" = "#b56536", "Buffered rule" = "#786093")
  colours <- rep(palette, length.out = length(series))
  named <- names(series) %in% names(fixed)
  colours[named] <- fixed[names(series)[named]]
  line_types <- ifelse(grepl("Nominal", names(series), fixed = TRUE), 2, 1)
  symbols <- ifelse(grepl("Nominal", names(series), fixed = TRUE), 1, 16)
  old <- par(mar = c(3.7, 4.4, if (is.null(panel_title)) 2.7 else 3.5, 0.9),
             mgp = c(2.8, 0.7, 0), las = 1, cex = 0.88,
             col.axis = "#354655", col.lab = "#243649", fg = "#8e9ba5", bty = "l")
  on.exit(par(old))
  bounds <- range(c(0, values, upper), finite = TRUE)
  if (diff(bounds) == 0) bounds <- bounds + c(0, 1)
  years <- range(years)
  if (diff(years) == 0) years <- years + c(-0.5, 0.5)
  plot(years, bounds, type = "n", xlab = "Year", ylab = label, xaxt = "n")
  ticks <- pretty(years, n = 4)
  ticks <- ticks[ticks >= years[1] & ticks <= years[2] & ticks == floor(ticks)]
  axis(1, at = ticks, labels = ticks)
  abline(h = axTicks(2), col = "#e7ebee", lwd = 0.8)
  if (!is.null(reference)) abline(h = reference / scale, col = "#89949d", lty = 3)
  for (i in seq_along(series)) {
    rows <- series[[i]]
    lines(vapply(rows, function(row) row$year, numeric(1)),
          vapply(rows, function(row) row[[field]], numeric(1)) / scale,
          type = if (names(series)[i] %in% points) "p" else "o",
          pch = symbols[i], cex = 0.5, col = colours[i], lty = line_types[i], lwd = 1.8)
  }
  if (!is.null(panel_title)) mtext(panel_title, side = 3, line = 2.6, cex = 0.95, font = 2)
  legend("top", names(series), col = colours, lty = ifelse(names(series) %in% points, NA, line_types),
         pch = symbols, lwd = 1.8, ncol = min(2, length(series)), inset = c(0, -0.20),
         bty = "n", xpd = NA, cex = 0.80)
}

report_panels <- function(code) {
  old <- par(mfrow = c(1, 2))
  on.exit(par(old))
  eval(substitute(code), parent.frame())
}

report_annual <- function(rows) {
  if (!report_has(rows, "year")) return(list())
  years <- sort(unique(vapply(rows, function(row) row$year, numeric(1))))
  lapply(years, function(year) {
    selected <- Filter(function(row) row$year == year, rows)
    list(year = year, observations = length(selected),
         hooks = sum(vapply(selected, function(row) row$hooks, numeric(1))),
         catch_n = sum(vapply(selected, function(row) row$catch_n, numeric(1))))
  })
}

report_coverage <- function(rows, catch = NULL) {
  value <- list(records = length(rows), years = report_years(rows))
  for (field in c("fleet", "stratum", "vessel")) {
    present <- unique(unlist(lapply(rows, `[[`, field)))
    if (length(present)) value[[paste0(field, "s")]] <- if (field == "fleet") paste(present, collapse = ", ") else length(present)
  }
  if (length(catch)) value$catch_years <- report_years(catch)
  fields <- c(records = "Records", years = "Years", fleets = "Fleet", strata = "Strata",
              vessels = "Vessels", catch_years = "Catch years")
  report_table(list(value), fields[names(fields) %in% names(value)])
}

report_data_plot <- function(rows, catch = NULL, field = "hooks") {
  annual <- report_annual(rows)
  if (field == "hooks") {
    annual <- lapply(annual, function(row) { row$effort <- row$hooks / 1e6; row })
    first <- list(Effort = annual)
    label <- "Effort (million hooks)"
    field <- "effort"
  } else {
    first <- list(Records = annual)
    label <- "Released records"
  }
  report_panels({
    report_plot(first, field, label)
    if (length(catch)) report_plot(list(Removals = catch), "catch_t", "Catch (t/y)") else {
      report_plot(list(Fish = annual), "catch_n", "Catch (fish)")
    }
  })
}

report_pairs_check <- function(rows) {
  years <- if (report_has(rows, "year")) vapply(rows, function(row) row$year, numeric(1)) else numeric()
  unique_years <- length(years) > 0L && !anyDuplicated(years)
  consecutive <- length(years) > 0L && all(diff(years) == 1)
  positive <- report_has(rows, "index") && all(vapply(rows, function(row) row$index > 0, logical(1)))
  catch <- report_has(rows, "catch_t") && all(vapply(rows, function(row) row$catch_t >= 0, logical(1)))
  report_table(list(list(years = if (unique_years && consecutive) "Unique, consecutive" else "Review",
                         index = if (positive) "Positive, finite" else "Review",
                         catch = if (catch) "Non-negative, finite" else "Review")),
               c(years = "Annual join", index = "Index values", catch = "Catch values"))
}

report_rate_series <- function(rows) {
  rates <- lapply(c("standardised_cpue", "nominal_cpue"), function(field) {
    lapply(rows, function(row) list(year = row$year, cpue = row[[field]]))
  })
  setNames(rates, c("Standardised", "Nominal"))
}

report_rate_plot <- function(rows, label = NULL, upper = NULL) {
  if (report_has(rows, "standardised_cpue") && report_has(rows, "nominal_cpue")) {
    rates <- report_rate_series(rows)
    if (!is.null(label)) attr(rates, "panel_title") <- label
    report_plot(rates, "cpue", "Fish per 1,000 hooks", upper = upper)
  } else {
    report_plot(setNames(list(rows), if (is.null(label)) "Saved index" else label), "index", "Relative CPUE")
  }
}

report_cpue_checks <- function(analyses, series = NULL) {
  rows <- lapply(seq_along(analyses), function(i) {
    x <- analyses[[i]]
    values <- if (!is.null(series) && length(series) >= i) series[[i]] else x$series
    list(analysis = sub("CPUE analysis ", "", names(analyses)[i], fixed = TRUE),
      used = x$sets_used, excluded = x$sets_excluded,
      converged = if (is.null(x$converged)) NULL else if (isTRUE(x$converged)) "Yes" else "No",
      dispersion = x$dispersion, score = x$score_residual,
      final_index = if (report_has(values, "index")) tail(values, 1)[[1]]$index else NULL)
  })
  columns <- c(analysis = "Analysis", used = "Rows", excluded = "Excluded", converged = "Converged",
               dispersion = "Dispersion", score = "Score residual", final_index = "Final index")
  columns <- columns[vapply(names(columns), function(field) any(vapply(rows, function(row) !is.null(row[[field]]), logical(1))), logical(1))]
  report_table(rows, columns)
}

report_cpue_note <- function(analyses, record) {
  methods <- unique(unlist(lapply(analyses, `[[`, "method")))
  if (length(methods)) cat(paste(methods, collapse = "; "), ". ", sep = "")
  cat("Nominal = 1,000 × annual fish / annual hooks; both curves use the same selected records. ")
  targets <- unique(unlist(lapply(analyses, `[[`, "standardisation")))
  if (length(targets)) cat(paste(targets, collapse = "; "), ". ", sep = "")
  thresholds <- vapply(analyses, function(x) if (is.null(x$min_hooks)) 0 else x$min_hooks, numeric(1))
  if (any(thresholds > 0)) cat("Minimum hooks: ",
    paste(paste(names(analyses), thresholds, sep = " = "), collapse = "; "), ". ", sep = "")
  cat("The relative index passed to assessment equals one in its first year.\n\n")
}

report_fit_status <- function(row) {
  required <- c("balance_check", "feasibility_check", "gradient_check", "convergence", "boundary_fit")
  recorded <- vapply(required, function(field) !is.null(row[[field]]), logical(1))
  if (!any(recorded)) return("Not recorded")
  flags <- character()
  for (field in c("balance_check", "feasibility_check", "gradient_check", "catch_check")) {
    if (!is.null(row[[field]]) && row[[field]] != "Pass") flags <- c(flags, paste(gsub("_check$", "", field), row[[field]]))
  }
  if (isTRUE(row$boundary_fit)) flags <- c(flags, "search boundary")
  if (!is.null(row$convergence) && row$convergence != 0) flags <- c(flags, paste("convergence", row$convergence))
  if (length(flags)) paste("Review:", paste(flags, collapse = "; ")) else if (all(recorded)) "Pass" else "Partial record"
}

report_assessment <- function(result, individual = FALSE) {
  if (individual) {
    rows <- result$series
    fit <- lapply(c("observed_index", "fitted_index"), function(field) {
      lapply(rows, function(row) list(year = row$year, index = row[[field]]))
    })
    names(fit) <- c("Observed CPUE", "Fitted CPUE")
    report_panels({
      report_plot(fit, "index", "Relative CPUE", points = "Observed CPUE")
      report_plot(list(Biomass = rows), "B_over_K", "Start-of-year B/K", upper = 1)
    })
    value <- result[c("r", "K", "q")]
    value$final_B_over_K <- if (length(rows)) tail(rows, 1)[[1]]$B_over_K else NULL
    report_table(list(value), c(r = "Fixed r (/y)", K = "Capacity K (t)", q = "Catchability q",
                               final_B_over_K = "Final B/K"))
    cat("**Numerical checks:** ", report_fit_status(result), ". ", sep = "")
    if (!is.null(result$balance_residual_t)) cat("Maximum balance residual ", report_scalar(result$balance_residual_t), " t", sep = "")
    if (!is.null(result$balance_tolerance_t)) cat(" (tolerance ", report_scalar(result$balance_tolerance_t), " t)", sep = "")
    if (!is.null(result$projected_gradient_logK)) cat("; projected gradient ", report_scalar(result$projected_gradient_logK), sep = "")
    if (!is.null(result$gradient_tolerance)) cat(" (tolerance ", report_scalar(result$gradient_tolerance), ")", sep = "")
    if (!is.null(result$active_bound)) cat("; active bound: ", result$active_bound, sep = "")
    cat(".\n\n")
  } else {
    report_plot(result$series, "B_over_K", "Start-of-year B/K", upper = 1)
    rows <- lapply(result$diagnostics, function(row) {
      series <- result$series[[row$case]]
      list(case = row$case, r = row$r, K = row$K,
           final_B_over_K = if (length(series)) tail(series, 1)[[1]]$B_over_K else NULL,
           checks = report_fit_status(row))
    })
    report_table(rows, c(case = "Case", r = "Fixed r (/y)", K = "Capacity K (t)",
                         final_B_over_K = "Final B/K", checks = "Numerical checks"))
  }
  cat("B/K uses each case's carrying capacity. Fitted parameters and next-year biomass pass to management trial preparation.\n\n")
}

report_mse_metrics <- function(metrics, assumptions = list()) {
  threshold <- if (is.null(assumptions$depletion_threshold)) "threshold" else report_scalar(assumptions$depletion_threshold)
  report_table(metrics, c(name = "Rule", mean_catch_t = "Mean catch (t/y)", final_B_over_K = "Final B/K",
    below_threshold_percent = paste0("Below ", threshold, " (%)"),
    catch_change_percent = "Catch change (%)", shortfall_trials = "Capped trials"))
  cat("Final B/K is the trial median; below-threshold counts trials with any low-biomass year. ",
      "Catch change includes the first change from reference catch. Capped trials had requested catch above the biomass guardrail.\n\n", sep = "")
}

report_mse <- function(result, individual = FALSE) {
  series <- if (individual) setNames(list(result$series), result$name) else result$series
  metrics <- if (individual) list(c(list(name = result$name), result$metrics)) else result$metrics
  rule_names <- vapply(metrics, function(row) row$name, character(1))
  if (all(rule_names %in% names(series))) series <- series[rule_names]
  if (individual && !is.null(result$description)) cat(result$description, "\n\n")
  models <- result$operating_models
  catches <- unlist(lapply(models, `[[`, "reference_catch_t"))
  catch_upper <- if (length(catches) && !is.null(result$assumptions$maximum_catch_multiple)) {
    max(catches) * result$assumptions$maximum_catch_multiple
  } else NULL
  report_panels({
    report_plot(series, "B_over_K", "Median end-year B/K", upper = 1,
                reference = result$assumptions$depletion_threshold)
    report_plot(series, "catch_t", "Median catch (t/y)", upper = catch_upper)
  })
  report_mse_metrics(metrics, result$assumptions)
  assumptions <- result$assumptions
  counts <- unique(unlist(lapply(metrics, `[[`, "trials")))
  if (length(counts) == 1L) cat(counts, " trials per rule; ", sep = "")
  if (!is.null(assumptions$years)) cat(assumptions$years, " future years; ", sep = "")
  if (length(models)) cat(length(models), " fitted cases; ", sep = "")
  if (length(assumptions$scenarios)) cat(length(assumptions$scenarios), " growth scenarios. ", sep = "")
  cat("All rules use the same saved errors and cases, with equal case/scenario weights. ")
  if (!is.null(assumptions$maximum_harvest_rate)) cat("Realised catch is capped at ",
    100 * assumptions$maximum_harvest_rate, "% of starting biomass. ", sep = "")
  if (!is.null(assumptions$depletion_threshold)) cat("Dotted line: B/K = ", report_scalar(assumptions$depletion_threshold), ". ", sep = "")
  cat("\n\n")
  if (length(result$boundary_cases)) cat("**Review:** assessment cases on search boundaries: ",
    paste(unlist(result$boundary_cases), collapse = ", "), ".\n\n", sep = "")
}

report_scope <- function(job, result, record) {
  public <- !is.null(record$data_source) && (!is.null(record$data_source$cpue_scope) || identical(result$data_kind, "public-wcpfc"))
  if (public && grepl("^cpue", job)) {
    # Source coverage can extend beyond this run's saved annual series.
    scope <- sub("[[:space:]]*[,;]?[[:space:]]*[0-9]{4}[[:space:]]*[–—-][[:space:]]*[0-9]{4}[[:space:]]*$",
                 "", record$data_source$cpue_scope)
    rows <- result$series
    if (!report_has(rows, "year")) rows <- unlist(rows, recursive = FALSE, use.names = FALSE)
    years <- report_years(rows)
    scope <- c(scope, years)
    cat("**Scope:** ", paste(scope[nzchar(scope)], collapse = ", "),
        "; aggregate records without vessel effects or confidence intervals.\n\n", sep = "")
  } else if (public && grepl("^mse", job)) {
    cat("**Scope:** these illustrative trials use simplified fitted cases and errors; trial fractions are not calibrated management risks.\n\n")
  } else if (public && grepl("^(assessment|prepare)", job)) {
    cat("**Scope:** selected-fleet CPUE and stock-wide catches are combined only to illustrate the workflow.\n\n")
  } else if (grepl("^(cpue|assessment|mse)", job)) {
    cat("**Scope:** illustrative results under the saved data and model assumptions.\n\n")
  }
}

report_record <- function(record) {
  report_inputs(record)
  cat("---\n\n")
  links <- if (knitr::is_html_output()) {
    c("[Saved results](report-data.json)", "[Run record](record.json)")
  } else "Saved files: `report-data.json` · `record.json`"
  for (field in c("analysis_source", "source")) {
    source <- record[[field]]
    if (!is.null(source$repository) && !is.null(source$commit)) {
      label <- if (field == "analysis_source") "Code" else "Workflow"
      links <- c(links, paste0("[", label, " ", substr(source$commit, 1, 8), "](",
        sub("/$", "", source$repository), "/commit/", source$commit, ")"))
    }
  }
  image <- record$software$container
  if (is.null(image)) image <- record$software$image
  image_url <- record$software$container_url
  if (is.null(image_url)) image_url <- record$software$package_url
  if (!is.null(image)) {
    digest <- sub(".*(?:@sha256:|^sha256:)", "", image, perl = TRUE)
    label <- paste0("Image ", substr(digest, 1, 12))
    links <- c(links, if (!is.null(image_url)) paste0("[", label, "](", image_url, ")") else label)
  }
  cat(paste(links, collapse = " · "), ".\n\n", sep = "")
  sources <- record$data_source$sources
  if (length(sources)) {
    urls <- unique(unlist(lapply(sources, `[[`, "url")))
    provider <- record$data_source$provider
    if (is.null(provider) && any(grepl("wcpfc.int", urls, fixed = TRUE))) provider <- "WCPFC/SPC public statistics"
    if (!is.null(provider)) cat("Data: ", provider, ". ", sep = "")
    if (length(urls)) cat(paste(vapply(seq_along(urls), function(i) paste0("[Source ", i, "](", urls[i], ")"), character(1)), collapse = " · "), ".", sep = "")
    cat("\n\n")
  } else if (!is.null(record$data_source$provider)) cat("Data: ", record$data_source$provider, ".\n\n", sep = "")
}

report_result_view <- function(job, result, record) {
  titles <- c(submission = "Submitted data", qc = "Data checks", database = "Database snapshot",
    extract = "Extracted analysis data", cpue_a = "CPUE analysis A", cpue_b = "CPUE analysis B", cpue_summary = "CPUE comparison",
    prepare_a = "Assessment inputs A", prepare_b = "Assessment inputs B", assessment_a1 = "Assessment A1",
    assessment_a2 = "Assessment A2", assessment_b1 = "Assessment B1", assessment_b2 = "Assessment B2",
    assessment_summary = "Assessment comparison", mse_prepare = "Management trial inputs",
    mse_constant = "Constant catch", mse_index = "Index rule", mse_buffered = "Buffered rule", mse_summary = "Management comparison")
  if (!job %in% names(titles)) stop("No saved-result presentation for job: ", job)
  title <- if (is.null(record$title)) titles[[job]] else record$title
  rows <- if (!is.null(result$sets)) result$sets else if (!is.null(result$rows) && is.list(result$rows)) result$rows else result$annual
  if (is.null(rows) && !is.null(result$series)) rows <- if (report_has(result$series, "year")) result$series else result$series[[1]]
  report_header(title, record, rows)
  if (job == "submission") {
    report_coverage(result$sets, result$catch)
    report_data_plot(result$sets, field = "hooks")
    cat("Released fish counts and fishing effort enter data checks. Annual removals in tonnes are retained separately for assessment.\n\n")
  } else if (job == "qc") {
    report_table(result$checks, c(check = "Data check", result = "Recorded result"))
    report_table(list(list(rows = result$rows, returned = length(result$returned))),
                 c(rows = "Accepted records", returned = "Returned for correction"))
    cat("Accepted records pass to the database snapshot. Released zero catches remain observations; missing or suppressed values are not treated as zeros.\n\n")
  } else if (job == "database") {
    report_table(list(result), c(rows = "Records", first_year = "First year", last_year = "Last year"))
    report_panels({
      report_plot(list(Records = result$annual), "observations", "Released records")
      report_plot(list(Removals = result$annual), "catch_t", "Catch (t/y)")
    })
    cat("The saved SQLite snapshot contains fishing records and annual removals. Extraction selects the CPUE records; removals remain a separate annual series.\n\n")
  } else if (job == "extract") {
    report_coverage(result$sets, result$catch)
    report_data_plot(result$sets, result$catch)
    cat("Selected fish counts and effort pass to CPUE; annual removals pass to assessment input preparation. The exact SQL and source-row identifiers are retained in Data.\n\n")
  } else if (job %in% c("cpue_a", "cpue_b")) {
    report_rate_plot(result$series)
    analyses <- setNames(list(result), toupper(sub("cpue_", "", job)))
    report_cpue_checks(analyses)
    report_cpue_note(analyses, record)
  } else if (job == "cpue_summary") {
    report_plot(result$series, "index", "CPUE relative to first year")
    report_cpue_checks(result$analyses, result$series)
    cat("Both indices equal one in their own first year. A and B use their recorded adjustments and effort filters; each passes independently to assessment input preparation.\n\n")
  } else if (job %in% c("prepare_a", "prepare_b")) {
    rows <- if (!is.null(result$rows)) result$rows else result$series
    cat(length(rows), " annual index/catch pairs, joined by year.\n\n", sep = "")
    report_panels({
      report_plot(list(Index = rows), "index", "Relative CPUE")
      report_plot(list(Removals = rows), "catch_t", "Catch (t/y)")
    })
    report_pairs_check(rows)
    cat("These paired annual values are the inputs to the two fixed-growth assessment cases.\n\n")
  } else if (grepl("^assessment_", job)) {
    report_assessment(result, individual = job != "assessment_summary")
  } else if (job == "mse_prepare") {
    models <- lapply(result$operating_models, function(model) { model$starting_depletion <- model$B / model$K; model })
    report_table(models, c(name = "Case", first_year = "First future year", starting_depletion = "Starting B/K", reference_catch_t = "Reference catch (t/y)"))
    assumptions <- result$assumptions
    report_table(list(assumptions), c(years = "Future years", replicates = "Trials/case/scenario", growth_cv = "Growth CV", observation_cv = "Observation CV"))
    streams <- length(result$error_streams)
    expected <- length(models) * length(assumptions$scenarios) * assumptions$replicates
    cat(streams, " saved error streams for ", length(models), " cases × ", length(assumptions$scenarios),
        " scenarios × ", assumptions$replicates, " trials", if (streams == expected) "; count matches the trial design. " else "; review the trial count. ", sep = "")
    if (!is.null(assumptions$seed)) cat("Seed: ", assumptions$seed, ". ", sep = "")
    cat("Each rule receives the same cases and errors, starting after the final historical catch.\n\n")
    if (any(vapply(models, function(model) isTRUE(model$boundary_fit), logical(1)))) cat("**Review:** one or more fitted cases are on an assessment search boundary.\n\n")
  } else {
    report_mse(result, individual = job != "mse_summary")
  }
  if (identical(result$converged, FALSE)) cat("**Review:** CPUE model did not converge.\n\n")
  report_scope(job, result, record)
  report_record(record)
}

report_full_view <- function(job, result, record) {
  titles <- c(cpue_report = "CPUE analysis", assessment_report = "Assessment results", mse_report = "Management trial results")
  if (!job %in% names(titles)) stop("No formal saved-result presentation for job: ", job)
  rows <- if (length(result$series)) result$series[[1]] else NULL
  report_header(if (is.null(record$title)) titles[[job]] else record$title, record, rows)
  if (job == "cpue_report") {
    rates <- unlist(lapply(result$series, function(rows) {
      unlist(lapply(rows, function(row) c(row$nominal_cpue, row$standardised_cpue)))
    }))
    upper <- if (length(rates)) max(rates) else NULL
    if (length(result$series) >= 2L) report_panels({
      report_rate_plot(result$series[[1]], "Analysis A", upper)
      report_rate_plot(result$series[[2]], "Analysis B", upper)
    }) else report_rate_plot(result$series[[1]])
    report_cpue_checks(result$analyses, result$series)
    report_cpue_note(result$analyses, record)
    cat("Final index is the last standardised value relative to its first year. Dispersion is Pearson residual sum of squares / residual df; score residual checks the fitted aggregate totals.\n\n")
  } else if (job == "assessment_report") {
    report_assessment(result)
    cat("Schaefer fits start biomass at K and fit K/q to annual log indices, with r fixed in each case and catches in tonnes. Numerical checks test the fit and declared biomass recurrence.\n\n")
  } else {
    report_mse(result)
    cat("Constant catch holds the reference catch; the index rule follows recent observed CPUE; the buffered rule adds its saved step, buffer and annual change limit. No assessment is refitted during the trials.\n\n")
  }
  report_scope(job, result, record)
  report_record(record)
}

render_saved_report <- function(root, job, folder) {
  if (!grepl("^[a-z][a-z0-9_]*$", job)) stop("Invalid job key")
  # A failed rerender must not leave an earlier success receipt in place.
  unlink(file.path(folder, "rendering.json"))
  require_container()
  for (package in c("jsonlite", "knitr", "rmarkdown")) {
    if (!requireNamespace(package, quietly = TRUE)) stop("Rendering requires R package: ", package)
  }
  declared <- unlist(jsonlite::fromJSON(file.path(root, "SOURCE.json"), simplifyVector = FALSE)$jobs,
                     use.names = FALSE)
  if (!job %in% declared) stop("JOB must name a job declared in SOURCE.json")
  timeout <- suppressWarnings(as.numeric(Sys.getenv("TIMEOUT", "300")))
  if (length(timeout) != 1L || !is.finite(timeout) || timeout <= 0) stop("TIMEOUT must be a positive number of seconds")
  quarto <- Sys.which("quarto")
  if (!nzchar(quarto)) stop("Quarto is required to render saved results")
  dir.create(folder, recursive = TRUE, showWarnings = FALSE)
  folder <- normalizePath(folder, mustWork = TRUE)
  data_path <- file.path(folder, "report-data.json")
  if (!file.exists(data_path)) {
    input_paths <- file.path(folder, c("result.json", "record.json"))
    if (!all(file.exists(input_paths))) stop("Provide report-data.json with exactly result and record")
    json <- vapply(input_paths, function(path) paste(readLines(path, warn = FALSE), collapse = "\n"), character(1))
    writeLines(paste0('{"result":', json[[1]], ',"record":', json[[2]], '}'), data_path, useBytes = TRUE)
  }
  payload <- jsonlite::fromJSON(data_path, simplifyVector = FALSE)
  if (!is.list(payload) || length(payload) != 2L || !setequal(names(payload), c("result", "record")) ||
      !is.list(payload$result) || !is.list(payload$record)) {
    stop("report-data.json must contain exactly the object members result and record")
  }
  sha256 <- function(path) {
    output <- system2("sha256sum", c("--", shQuote(path)), stdout = TRUE, stderr = TRUE)
    if (!is.null(attr(output, "status")) || !length(output) || !grepl("^[a-f0-9]{64} ", output[[1]])) {
      stop("Cannot calculate SHA256 for ", path)
    }
    substr(output[[1]], 1L, 64L)
  }
  original_data_hash <- sha256(data_path)
  formal <- job %in% c("cpue_report", "assessment_report", "mse_report")
  source_relative <- if (formal) file.path("jobs", job, "report.qmd") else "reports/results.qmd"
  source_path <- file.path(root, source_relative)
  if (!file.exists(source_path)) stop("Missing presentation source: ", source_relative)
  copy_source <- function(from, to) {
    if (!identical(normalizePath(from, mustWork = TRUE), normalizePath(to, mustWork = FALSE)) &&
        !file.copy(from, to, overwrite = TRUE)) stop("Cannot preserve rendering source: ", from)
  }
  copy_source(source_path, file.path(folder, "report.qmd"))
  copy_source(file.path(root, "R/render.R"), file.path(folder, "report-view.R"))
  if (!formal) {
    writeLines(job, file.path(folder, "report-job.txt"))
  }
  temporary <- tempfile("saved-result-quarto-")
  dir.create(temporary)
  variables <- c("XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME")
  previous <- Sys.getenv(variables, unset = NA_character_)
  on.exit({
    for (name in variables) {
      if (is.na(previous[[name]])) Sys.unsetenv(name) else do.call(Sys.setenv, setNames(list(previous[[name]]), name))
    }
    unlink(temporary, recursive = TRUE)
  }, add = TRUE)
  for (i in seq_along(variables)) do.call(Sys.setenv, setNames(list(file.path(temporary, as.character(i))), variables[i]))
  previous_directory <- setwd(folder)
  on.exit(setwd(previous_directory), add = TRUE)
  command <- function(arguments, log = NULL) {
    output <- system2(quarto, shQuote(arguments), stdout = TRUE, stderr = TRUE, timeout = timeout)
    if (!is.null(log)) writeLines(output, log, useBytes = TRUE)
    if (!is.null(attr(output, "status")) && attr(output, "status") != 0L) {
      stop("Quarto failed: ", paste(tail(output, 30L), collapse = "\n"))
    }
    paste(output, collapse = "\n")
  }
  version <- command("--version")
  typst_version <- command(c("typst", "--version"))
  if (!grepl("typst [0-9]+\\.[0-9]+\\.[0-9]+", typst_version, ignore.case = TRUE)) stop("Cannot verify Typst version")
  command(c("render", "report.qmd", "--to", "html", "--output", "report.html", "--no-clean"), "report-html.log")
  command(c("render", "report.qmd", "--to", "typst", "--output", "report.pdf", "--no-clean"), "report-typst.log")
  required <- c("report.html", "report.pdf", "report.qmd", "report-data.json", "report.typ")
  if (!all(file.exists(required))) stop("Quarto omitted required artifacts: ", paste(required[!file.exists(required)], collapse = ", "))
  connection <- file("report.pdf", "rb")
  signature <- readBin(connection, "raw", n = 5L)
  close(connection)
  if (!identical(rawToChar(signature), "%PDF-")) stop("Quarto did not produce a PDF document")
  if (!identical(sha256("report-data.json"), original_data_hash)) stop("Rendering changed the saved input envelope")
  markdown <- list.files(pattern = "^report.*\\.md$")
  if (!length(markdown)) stop("Quarto did not preserve generated Markdown")
  figures <- list.files("report_files", recursive = TRUE, full.names = TRUE, all.files = TRUE, no.. = TRUE)
  figures <- figures[!dir.exists(figures)]
  typst <- paste(readLines("report.typ", warn = FALSE), collapse = "\n")
  images <- regmatches(typst, gregexpr('image\\("[^"]+"', typst))[[1]]
  if (length(images) && !identical(images, character())) {
    images <- sub('^image\\("', "", sub('"$', "", images))
    if (!all(file.exists(images))) stop("Typst source references a missing retained figure")
  }
  artifacts <- unique(c(required, markdown, figures, "report-html.log", "report-typst.log",
                        "report-view.R", if (!formal) "report-job.txt"))
  hashes <- setNames(lapply(artifacts, sha256), artifacts)
  receipt <- list(engine = "Quarto", version = version, calculation = "R", quarto_executed = TRUE,
    source = source_relative, presentation_source = source_relative, execution_engine = "knitr",
    plot_generator = "R from saved results", models_refitted = FALSE, simulations_repeated = FALSE,
    formats = list("html", "typst"), view = "report.pdf", pdf_engine = "Typst", pdf_engine_version = typst_version,
    job = job, timeout_seconds = timeout, input_sha256 = list("report-data.json" = original_data_hash),
    presentation_source_sha256 = sha256(source_path),
    software = list(R = R.version.string, Quarto = version, Typst = typst_version,
      jsonlite = as.character(utils::packageVersion("jsonlite")), knitr = as.character(utils::packageVersion("knitr")),
      rmarkdown = as.character(utils::packageVersion("rmarkdown")), image = Sys.getenv("PAPER_RUNTIME_IMAGE")),
    commands = list("quarto render report.qmd --to html --output report.html --no-clean",
                    "quarto render report.qmd --to typst --output report.pdf --no-clean"),
    artifacts = unname(as.list(artifacts)), artifact_sha256 = hashes)
  jsonlite::write_json(receipt, "rendering.json", auto_unbox = TRUE, pretty = TRUE, null = "null", digits = NA)
  invisible(receipt)
}
