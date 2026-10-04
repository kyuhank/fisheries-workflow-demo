.PHONY: run check html container
IMAGE := ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d
IMAGE_URL := https://github.com/PacificCommunity/ofp-sam-docker-images/pkgs/container/fisheries-workflow
run: container
container:
	docker pull $(IMAGE)
	mkdir -p runs
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) -v "$(CURDIR):/workspace:ro" -v "$(CURDIR)/runs:/outputs" -w /workspace $(IMAGE) python3 run.py --output /outputs
check:
	docker pull $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) --env PAPER_NATIVE_INTEGRATION=1 -v "$(CURDIR):/workspace:ro" -w /workspace $(IMAGE) sh -c 'Rscript --vanilla tests/test-r-models.R && python3 -m unittest discover -s tests -v'
html:
	docker pull $(IMAGE)
	docker run --rm --platform linux/amd64 --network none --user "$$(id -u):$$(id -g)" --env PAPER_RUNTIME_IMAGE=$(IMAGE) --env PAPER_RUNTIME_IMAGE_URL=$(IMAGE_URL) -v "$(CURDIR):/workspace" -w /workspace $(IMAGE) sh -c 'python3 scripts/build.py && python3 scripts/release.py'
