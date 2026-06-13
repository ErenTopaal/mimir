.PHONY: help dev-backend dev-frontend test lint build clean

BACKEND_DIR := backend
FRONTEND_DIR := frontend
BUN := $(HOME)/.bun/bin/bun

help:
	@echo "AvaxBench development commands"
	@echo ""
	@echo "  make test          Run backend integration tests"
	@echo "  make test-cov      Run backend tests with short tracebacks"
	@echo "  make lint          Lint backend (ruff) and frontend (biome)"
	@echo "  make build         Build frontend static output"
	@echo "  make dev-backend   Start backend development server"
	@echo "  make dev-frontend  Start frontend development server"
	@echo "  make clean         Remove build artifacts"

test:
	cd $(BACKEND_DIR) && uv run pytest tests/ -v

test-cov:
	cd $(BACKEND_DIR) && uv run pytest tests/ -v --tb=short

lint:
	cd $(BACKEND_DIR) && uv run ruff check .
	cd $(FRONTEND_DIR) && $(BUN) run lint

build:
	cd $(FRONTEND_DIR) && $(BUN) run build

dev-backend:
	cd $(BACKEND_DIR) && uv run python -m api

dev-frontend:
	cd $(FRONTEND_DIR) && $(BUN) run dev

clean:
	rm -rf $(FRONTEND_DIR)/.next
	rm -rf $(BACKEND_DIR)/__pycache__
	find $(BACKEND_DIR) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
