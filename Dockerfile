FROM ghcr.io/pacificcommunity/cpue-workshop@sha256:17b03d6e06da229b17524997d8a3fc8eb5f8f25233894b5ab99f89109b3890c5
WORKDIR /workspace
COPY workflow/ workflow/
COPY cloud/ cloud/
COPY data/ data/
COPY tests/ tests/
COPY scripts/generate-data.py scripts/generate-data.py
COPY run.py verify.py build-info.json ./
CMD ["python", "run.py", "--output", "/outputs"]
