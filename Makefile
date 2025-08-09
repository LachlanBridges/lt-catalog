SHELL := /bin/bash
IMAGE ?= library-data
DATA ?= $(PWD)/data

.PHONY: help install ingest enrich export docker-build docker-ingest docker-enrich docker-export

help:
	@echo "Targets: install, ingest, enrich, export, docker-build, docker-ingest, docker-enrich, docker-export"
	@echo "Examples:"
	@echo "  make install"
	@echo "  make ingest FILE=exports/lt-export_full.json"
	@echo "  make enrich LIMIT=200"
	@echo "  make docker-build"
	@echo "  make docker-enrich LIMIT=200"

install:
	pip install -e .

# Local runs (use variables: FILE=, DB=, LIMIT=, SINCE=, COLLECTIONS=, TAGS=, SEARCH=, FMT=json|marc)
ingest:
	python -m library_data.scripts.ingest --file $(FILE) $(if $(DB),--db $(DB),)

enrich:
	python -m library_data.scripts.enrich_levels $(if $(DB),--db $(DB),) $(if $(LIMIT),--limit $(LIMIT),)

export:
	python -m library_data.scripts.export_lt $(if $(SINCE),--since $(SINCE),) $(if $(COLLECTIONS),--collections $(COLLECTIONS),) $(if $(TAGS),--tags $(TAGS),) $(if $(SEARCH),--search $(SEARCH),) $(if $(FMT),--fmt $(FMT),)

# Docker runs (mounts $(DATA) at /app/library-data)
docker-build:
	docker build -t $(IMAGE) .

docker-ingest:
	docker run --rm -it \
	  -v "$(DATA):/app/data" \
	  -e LIBRARY_DATA_DIR=/app/data \
	  $(if $(LT_TOKEN),-e LT_TOKEN=$(LT_TOKEN),) \
	  $(IMAGE) library-data-ingest --file /app/data/$(FILE) $(if $(DB),--db $(DB),)

docker-enrich:
	docker run --rm -it \
	  -v "$(DATA):/app/data" \
	  -e LIBRARY_DATA_DIR=/app/data \
	  $(if $(LT_TOKEN),-e LT_TOKEN=$(LT_TOKEN),) \
	  $(IMAGE) library-data-enrich-levels $(if $(DB),--db $(DB),) $(if $(LIMIT),--limit $(LIMIT),)

docker-export:
	docker run --rm -it \
	  -v "$(DATA):/app/data" \
	  -e LIBRARY_DATA_DIR=/app/data \
	  $(IMAGE) library-data-export-lt $(if $(SINCE),--since $(SINCE),) $(if $(COLLECTIONS),--collections $(COLLECTIONS),) $(if $(TAGS),--tags $(TAGS),) $(if $(SEARCH),--search $(SEARCH),) $(if $(FMT),--fmt $(FMT),)
