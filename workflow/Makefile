.PHONY: info calculate report report-markdown quarto-version typst-version
.SILENT:

info:
	exec Rscript --vanilla workflow/r_driver.R --info

calculate:
	exec Rscript --vanilla workflow/r_driver.R

report:
	cd "$$PAPER_REPORT_DIR" && exec quarto render report.qmd --to all

report-markdown:
	cd "$$PAPER_REPORT_DIR" && exec quarto pandoc report-pdf-body.html --from html --to markdown+pipe_tables-raw_html-native_divs-native_spans --wrap none --output report-body.md

quarto-version:
	exec quarto --version

typst-version:
	exec quarto typst --version
