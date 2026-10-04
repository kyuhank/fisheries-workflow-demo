FROM ghcr.io/pacificcommunity/fisheries-workflow@sha256:9dea950a713b87daad728517138bcb664a151f0f5b44a1d5370623734a5bca9d
WORKDIR /workspace
COPY jobs/ jobs/
COPY workflow/ workflow/
COPY cloud/ cloud/
COPY data/ data/
COPY tests/ tests/
COPY scripts/generate-data.R scripts/import-r-data.py scripts/
COPY run.py verify.py build-info.json README.md ADAPT.md LICENSE THIRD_PARTY.md Makefile Dockerfile ./
CMD ["make", "--no-print-directory", "--silent", "inside-run", "OUTPUT=/outputs"]
