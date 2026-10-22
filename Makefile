.DEFAULT_GOAL := run
.PHONY: help setup setup-local hydrate-sources run job plan bundle reproduce compare check site release portable live local
OUTPUT ?= runs
SETTINGS ?=
START ?= submission
SCOPE ?= workflow
JOB ?=
REFERENCE ?= reference
BUNDLE ?= workflow.zip
PORT ?= 8765
WORKSPACE ?=
ARCHIVE ?=
PACKAGE_SOURCES ?=
export OUTPUT SETTINGS START SCOPE JOB REFERENCE BUNDLE PORT WORKSPACE ARCHIVE PACKAGE_SOURCES

help:
	@printf '%s\n' 'make run' 'make job JOB=cpue_a' 'make plan START=assessment_a2' 'make check' 'make reproduce' 'make portable ARCHIVE=release.zip OUTPUT=portable-workflow PACKAGE_SOURCES=/path/to/R-sources'

setup:
	@Rscript --vanilla scripts/setup-host.R

setup-local:
	@Rscript --vanilla scripts/setup-host.R --local

hydrate-sources:
	@Rscript --vanilla scripts/run-workflow.R hydrate

run: hydrate-sources
	@set -- run --output "$$OUTPUT" --start "$$START" --scope "$$SCOPE"; \
	if [ -n "$$SETTINGS" ]; then set -- "$$@" --settings "$$SETTINGS"; fi; \
	exec Rscript --vanilla scripts/run-workflow.R "$$@"

job: export START = $(JOB)
job: export SCOPE = job
job:
	@test -n "$$JOB" || { echo 'Use make job JOB=cpue_a' >&2; exit 1; }
	@$(MAKE) --no-print-directory --silent run

plan: hydrate-sources
	@set -- plan --output "$$OUTPUT" --start "$$START" --scope "$$SCOPE"; \
	if [ -n "$$SETTINGS" ]; then set -- "$$@" --settings "$$SETTINGS"; fi; \
	exec Rscript --vanilla scripts/run-workflow.R "$$@"

bundle:
	@Rscript --vanilla scripts/run-workflow.R bundle --output "$$OUTPUT" --bundle "$$BUNDLE"

reproduce:
	@set -- reproduce; if [ -n "$$JOB" ]; then set -- "$$@" "$$JOB"; fi; \
	exec Rscript --vanilla scripts/offline.R "$$@"

compare:
	@set -- compare --reference "$$REFERENCE" --output "$$OUTPUT"; \
	if [ -n "$$JOB" ]; then set -- "$$@" --start "$$JOB" --scope job; fi; \
	exec Rscript --vanilla scripts/run-workflow.R "$$@"

check:
	@Rscript --vanilla tests-r/test-workflow.R
	@Rscript --vanilla tests-r/test-inputs.R
	@Rscript --vanilla tests-r/test-runtime.R
	@Rscript --vanilla tests-r/test-cloud.R
	@Rscript --vanilla tests-r/test-local.R
	@Rscript --vanilla tests-r/test-release.R

site:
	@Rscript --vanilla scripts/build-site.R --output "$$OUTPUT"

release:
	@Rscript --vanilla scripts/release.R --docs docs

portable: OUTPUT = portable-workflow
portable:
	@test -n "$$ARCHIVE" && test -n "$$PACKAGE_SOURCES" || { \
	printf '%s\n' 'Use make portable ARCHIVE=release.zip OUTPUT=new-share PACKAGE_SOURCES=/path/to/R-sources' >&2; exit 1; }
	@exec Rscript --vanilla scripts/prepare-offline.R --bundle "$$ARCHIVE" --output "$$OUTPUT" --package-sources "$$PACKAGE_SOURCES"

live:
	@Rscript --vanilla scripts/run-live.R

local:
	@set -- --port "$$PORT"; if [ -n "$$WORKSPACE" ]; then set -- "$$@" --workspace "$$WORKSPACE"; fi; \
	exec sh scripts/local.sh "$$@"
