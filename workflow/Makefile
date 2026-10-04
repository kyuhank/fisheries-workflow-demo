.PHONY: info calculate report quarto-version
.SILENT:

info:
	exec Rscript --vanilla workflow/r_driver.R --info

calculate:
	exec Rscript --vanilla workflow/r_driver.R

report:
	cd "$$PAPER_REPORT_DIR" && exec quarto render report.qmd --to html --output report.html

quarto-version:
	exec quarto --version
