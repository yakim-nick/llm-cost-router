.PHONY: install dev test lint docker format

install:
	pip install -r requirements.txt

dev:
	uvicorn src.main:app --reload --port 8000

test:
	pytest tests/ -v

lint:
	ruff check .

docker:
	docker compose up --build

format:
	ruff format .
