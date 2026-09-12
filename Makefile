.PHONY: run check html container
run:
	python3 run.py
check:
	python3 -m unittest discover -s tests -v
html:
	python3 scripts/build.py
container:
	docker build -t fisheries-workflow .
	mkdir -p runs
	docker run --rm --network none --user "$$(id -u):$$(id -g)" -v "$(CURDIR)/runs:/outputs" fisheries-workflow
