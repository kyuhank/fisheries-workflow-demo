.DEFAULT_GOAL := run
.PHONY: hydrate-sources run container job reproduce compare check html inside-run inside-job inside-reproduce inside-compare inside-check inside-html inside-live

IMAGE := ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d
IMAGE_URL := https://github.com/PacificCommunity/ofp-sam-docker-images/pkgs/container/fisheries-workflow
PAPER_SOURCE_MODE ?= multi-repository
export PAPER_SOURCE_MODE
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
		--env PAPER_SOURCE_MODE --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) \
		--env SETTINGS --env START --env SCOPE \
		-v "$(CURDIR):/workspace:ro" -v "$$output:/outputs" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-run OUTPUT=/outputs

compare: hydrate-sources
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || docker pull --platform linux/amd64 $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" \
		--env PAPER_SOURCE_MODE --env REFERENCE --env RESULT --env JOB \
		-v "$(CURDIR):/workspace:ro" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-compare

check: hydrate-sources
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || docker pull --platform linux/amd64 $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" \
		--env PAPER_SOURCE_MODE --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) \
		--env PAPER_NATIVE_INTEGRATION=1 -v "$(CURDIR):/workspace:ro" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-check

html: hydrate-sources
	@docker image inspect $(IMAGE) >/dev/null 2>&1 || docker pull --platform linux/amd64 $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" \
		--env PAPER_SOURCE_MODE --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) \
		-v "$(CURDIR):/workspace" -w /workspace \
		$(IMAGE) make --no-print-directory --silent inside-html

inside-run inside-job inside-reproduce:
	@set -- --output "$$OUTPUT" --from "$$START" --scope "$$SCOPE"; \
	if [ -n "$$SETTINGS" ]; then set -- "$$@" --settings "$$SETTINGS"; fi; \
	exec python3 run.py "$$@"

inside-compare:
	@set -- "$$REFERENCE" "$$RESULT"; \
	if [ -n "$$JOB" ]; then set -- "$$@" --job "$$JOB"; fi; \
	exec python3 verify.py "$$@"

inside-check:
	@command -v make && make --version | head -n 1
	@Rscript --vanilla tests/test-r-models.R
	@PAPER_SOURCE_MODE=monorepo python3 -m unittest discover -s tests -v

inside-html:
	@python3 scripts/build.py
	@python3 scripts/release.py

inside-live:
	@exec python3 cloud/run.py
