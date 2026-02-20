.PHONY: help install install-hooks test test-unit test-integration check lint lint-fix format format-check typecheck typos clean

help:
	@printf "\nDevelopment Commands:\n\n"
	@awk '/^#/{c=substr($$0,3);next}c&&/^[[:alpha:]][[:alnum:]_-]+:/{printf "  \033[36m%-20s\033[0m %s\n", substr($$1,1,index($$1,":")-1),c}1{c=0}' $(MAKEFILE_LIST)

# Install all dependencies
install:
	uv sync --all-extras

# Install pre-commit hooks
install-hooks:
	uvx pre-commit install

# Run all tests
test:
	uv run pytest --cov=qodev_gitlab_mcp --cov-report=term --cov-report=html

# Run unit tests only
test-unit:
	uv run pytest tests/unit --cov=qodev_gitlab_mcp --cov-report=term

# Run integration tests only
test-integration:
	uv run pytest tests/integration -v

# Run all checks
check: lint format-check typecheck typos

# Lint code
lint:
	uv run ruff check .

# Auto-fix lint issues
lint-fix:
	uv run ruff check --fix .

# Format code
format:
	uv run ruff format .

# Check formatting
format-check:
	uv run ruff format --check .

# Type check
typecheck:
	uv run mypy qodev_gitlab_mcp/

# Spell check
typos:
	uvx typos

# Clean generated files
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
