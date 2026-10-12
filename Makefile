.DEFAULT_GOAL := run
.PHONY: hydrate-sources run container job reproduce compare check html inside-run inside-job inside-reproduce inside-compare inside-check inside-synthetic-check inside-public-check inside-public-source-check inside-public-baseline-check inside-public-update-check inside-public-reproduction-check inside-component-check inside-html inside-live

IMAGE := ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d
IMAGE_URL := https://github.com/PacificCommunity/ofp-sam-docker-images/pkgs/container/fisheries-workflow
PAPER_SOURCE_MODE ?= multi-repository
PAPER_DATA_MODE ?= public
PAPER_TEST_EVIDENCE ?=
export PAPER_SOURCE_MODE PAPER_DATA_MODE PAPER_TEST_EVIDENCE
OUTPUT ?= runs
SETTINGS ?=
JOB ?=
START ?= submission
SCOPE ?= workflow
REFERENCE ?= reference
RESULT ?= reproduced
REPRO_SETTINGS := $(or $(SETTINGS),settings.json)

export OUTPUT
export SETTINGS
export START
export SCOPE
export JOB
export REFERENCE
export RESULT

job inside-job: export START = $(JOB)
job inside-job: export SCOPE = job
reproduce inside-reproduce: export OUTPUT = $(RESULT)
reproduce inside-reproduce: export SETTINGS = $(REPRO_SETTINGS)
reproduce inside-reproduce: export START = $(or $(JOB),submission)
reproduce inside-reproduce: export SCOPE = $(if $(JOB),job,workflow)

hydrate-sources:
	@if [ "$$PAPER_SOURCE_MODE" != monorepo ]; then python3 scripts/hydrate-sources.py --if-needed; fi

run container job reproduce: hydrate-sources
	@if [ "$$SCOPE" = job ] && [ -z "$$START" ]; then echo 'Use make job JOB=cpue_a' >&2; exit 1; fi
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || docker pull --platform linux/amd64 $(IMAGE)
	@set -e; mkdir -p "$$OUTPUT"; \
	output=$$(cd "$$OUTPUT" && pwd); \
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" \
		--env PAPER_SOURCE_MODE --env PAPER_DATA_MODE --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) \
		--env SETTINGS --env START --env SCOPE \
		-v "$(CURDIR):/workspace:ro" -v "$$output:/outputs" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-run OUTPUT=/outputs

compare: hydrate-sources
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || docker pull --platform linux/amd64 $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" \
		--env PAPER_SOURCE_MODE --env PAPER_DATA_MODE --env REFERENCE --env RESULT --env JOB \
		-v "$(CURDIR):/workspace:ro" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-compare

check: hydrate-sources
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || docker pull --platform linux/amd64 $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" \
		--env PAPER_SOURCE_MODE --env PAPER_DATA_MODE --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) \
		--env PAPER_NATIVE_INTEGRATION=1 -v "$(CURDIR):/workspace:ro" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-check

html: hydrate-sources
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || docker pull --platform linux/amd64 $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" \
		--env PAPER_SOURCE_MODE --env PAPER_DATA_MODE --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) \
		-v "$(CURDIR):/workspace" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-html

inside-run inside-job inside-reproduce:
	@set -- --output "$$OUTPUT" --from "$$START" --scope "$$SCOPE"; \
	if [ -n "$$SETTINGS" ]; then set -- "$$@" --settings "$$SETTINGS"; fi; \
	if [ -n "$$PAPER_TEST_EVIDENCE" ]; then exec python3 -m tests.native_evidence "$$@"; fi; \
	exec python3 run.py "$$@"

inside-compare:
	@set -- "$$REFERENCE" "$$RESULT"; \
	if [ -n "$$JOB" ]; then set -- "$$@" --job "$$JOB"; fi; \
	exec python3 verify.py "$$@"

inside-check:
	@command -v make && make --version | head -n 1
	@Rscript --vanilla tests/test-r-models.R
	@$(MAKE) --no-print-directory --silent inside-synthetic-check
	@$(MAKE) --no-print-directory --silent inside-public-check
	@$(MAKE) --no-print-directory --silent inside-component-check

# Legacy fixtures retain their declared synthetic defaults in a fresh process.
inside-synthetic-check:
	@PAPER_SOURCE_MODE=monorepo PAPER_DATA_MODE=synthetic python3 -m unittest discover -s tests -v

inside-public-check:
	@PAPER_SOURCE_MODE=monorepo PAPER_DATA_MODE=public python3 -m unittest discover -s tests -p 'test_public*.py' -v

# Finite native batches for a registered Local run with an outer wall limit.
# Reference paths, when supplied, must be verified current-source checkpoints.
inside-public-source-check:
	@PAPER_DATA_MODE=public python3 -m unittest tests.test_public_data -v

inside-public-baseline-check:
	@PAPER_DATA_MODE=public python3 -m unittest -v \
		tests.test_public_integration.PublicNativeIntegrationTest.test_1_default_public_workflow_has_22_jobs_and_actual_fixed_support \
		tests.test_public_integration.PublicNativeIntegrationTest.test_2_2022_data_update_matches_a_fresh_full_workflow

inside-public-update-check:
	@PAPER_DATA_MODE=public python3 -m unittest tests.test_public_integration.PublicReaderUpdateIntegrationTest -v

inside-public-reproduction-check:
	@PAPER_DATA_MODE=public python3 -m unittest -v \
		tests.test_public_integration.PublicNativeIntegrationTest.test_4_download_reproduces_the_explicit_22_job_public_workflow \
		tests.test_public_integration.PublicNativeIntegrationTest.test_5_derived_public_input_fixture_is_frozen_for_single_job_reproduction

# Exercise the actual pinned repositories as well as the local source tree.
# Missing or incompatible pins fail this gate; monorepo success cannot replace it.
inside-component-check:
	@PAPER_SOURCE_MODE=multi-repository PAPER_DATA_MODE=synthetic python3 -m unittest -v \
		tests.test_native_integration.NativeIntegrationTest.test_1_fresh_R_results_and_genuine_Quarto_custody \
		tests.test_native_integration.NativeIntegrationTest.test_6_download_reproduces_actual_results_inside_same_container
	@PAPER_SOURCE_MODE=multi-repository PAPER_DATA_MODE=public python3 -m unittest tests.test_public_integration -v

inside-html:
	@python3 scripts/build.py
	@python3 scripts/release.py

inside-live:
	@exec python3 cloud/run.py
