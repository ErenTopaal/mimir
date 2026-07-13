.PHONY: build up down logs lint migrate dev

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

lint:
	uv run ruff check .

migrate:
	docker compose exec backend alembic upgrade head

dev:
	docker compose -f compose.yml -f compose.dev.yml up -d
