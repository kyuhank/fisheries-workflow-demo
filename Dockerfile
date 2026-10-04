FROM ghcr.io/pacificcommunity/fisheries-workflow@sha256:53549c0f7b159968fcb5c8861fff7f8d88572d0cf8764237e983f69bbd4581cc
WORKDIR /workspace
COPY jobs/ jobs/
COPY workflow/ workflow/
COPY cloud/ cloud/
COPY data/ data/
COPY tests/ tests/
COPY scripts/generate-data.py scripts/generate-data.py
COPY run.py verify.py build-info.json README.md ADAPT.md LICENSE THIRD_PARTY.md Makefile Dockerfile ./
CMD ["python", "run.py", "--output", "/outputs"]
