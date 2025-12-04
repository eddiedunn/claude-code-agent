.PHONY: help install install-commands test test-verbose test-watch lint lint-fix format check clean docs docs-serve docs-build docs-sync-sdk run-example grind grind-dag grind-dag-parallel sonar-scan

# Default target
.DEFAULT_GOAL := help

# Setup and installation
install:
	@echo "Installing dependencies with uv..."
	uv sync

install-dev:
	@echo "Installing with dev dependencies..."
	uv sync --dev

install-commands:
	@echo "Installing slash commands globally..."
	@mkdir -p ~/.claude/commands
	@cp .claude/commands/generate-tasks.md ~/.claude/commands/
	@echo "Installed /generate-tasks to ~/.claude/commands/"
	@echo "This command is now available in all Claude Code sessions."

# Testing
test:
	@echo "Running tests..."
	uv run pytest

test-verbose:
	@echo "Running tests with verbose output..."
	uv run pytest -v

test-file:
	@echo "Run a specific test file: make test-file FILE=tests/test_engine.py"
	@test -n "$(FILE)" || (echo "Error: FILE not specified" && exit 1)
	uv run pytest $(FILE) -v

test-watch:
	@echo "Running tests in watch mode..."
	uv run pytest-watch

test-cov:
	@echo "Running tests with coverage..."
	uv run pytest --cov=grind --cov-report=html --cov-report=term

test-cov-xml:
	@echo "Running tests with XML coverage for SonarQube..."
	uv run pytest --cov=grind --cov-report=xml:coverage.xml -v

# Linting and formatting
lint:
	@echo "Running ruff checks..."
	uv run ruff check .

lint-fix:
	@echo "Running ruff with auto-fix..."
	uv run ruff check --fix .

format:
	@echo "Formatting code with ruff..."
	uv run ruff format .

format-check:
	@echo "Checking code formatting..."
	uv run ruff format --check .

# Comprehensive check before commit
check: format lint test
	@echo "All checks passed!"

# Documentation commands
docs-serve:
	@echo "Starting MkDocs development server..."
	uv run mkdocs serve

docs-build:
	@echo "Building documentation..."
	uv run mkdocs build

docs-sync-sdk:
	@echo "Syncing SDK documentation from Anthropic..."
	uv run python scripts/sync-sdk-docs.py

docs: docs-sync-sdk docs-serve

# Run grind with interactive mode
grind:
	@test -n "$(TASKS)" || (echo "Usage: make grind TASKS=path/to/tasks.yaml" && exit 1)
	@test -f "$(TASKS)" || (echo "Error: $(TASKS) not found" && exit 1)
	uv run grind batch "$(TASKS)" --interactive --verbose

# Run grind in DAG mode (respects task dependencies)
grind-dag:
	@test -n "$(TASKS)" || (echo "Usage: make grind-dag TASKS=path/to/tasks.yaml" && exit 1)
	@test -f "$(TASKS)" || (echo "Error: $(TASKS) not found" && exit 1)
	uv run grind dag "$(TASKS)" --verbose

# Run grind in DAG mode with parallel execution
grind-dag-parallel:
	@test -n "$(TASKS)" || (echo "Usage: make grind-dag-parallel TASKS=path/to/tasks.yaml [PARALLEL=3]" && exit 1)
	@test -f "$(TASKS)" || (echo "Error: $(TASKS) not found" && exit 1)
	$(eval PARALLEL ?= 3)
	uv run grind dag "$(TASKS)" --parallel $(PARALLEL) --verbose

# Run examples
run-example:
	@echo "Running single task example..."
	uv run grind run --task "Echo hello world" --verify "echo 'Hello World'" --max-iter 1

run-example-batch:
	@echo "Running batch example..."
	@test -f examples/example-tasks.yaml || (echo "Error: examples/example-tasks.yaml not found" && exit 1)
	uv run grind batch examples/example-tasks.yaml

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf site/
	rm -rf .pytest_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf dist/
	rm -rf build/
	rm -rf *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*~" -delete

clean-all: clean
	@echo "Removing uv lock and cache..."
	rm -rf .venv/
	rm -rf uv.lock

# Build and distribution
build:
	@echo "Building package..."
	uv build

# SonarQube Analysis
sonar-scan:
	@echo "Running SonarQube baseline scan..."
	@echo "Step 1: Retrieving SonarQube token..."
	@TOKEN=$$(secret-manager show -o sonarqube/your-project/scan-token 2>/dev/null); \
	if [ -z "$$TOKEN" ]; then \
		echo "Error: No Project SonarQube token found"; \
		echo "Run: secret-manager show sonarqube/your-project/scan-token"; \
		exit 1; \
	fi; \
	echo "Step 2: Running tests with coverage..."; \
	uv run pytest --cov=grind --cov-report=xml:coverage.xml -q || true; \
	if [ ! -f coverage.xml ]; then \
		echo "Warning: coverage.xml not generated, proceeding without coverage"; \
	fi; \
	echo "Step 3: Running sonar-scanner..."; \
	sonar-scanner \
		-Dsonar.projectKey=grind-loop \
		-Dsonar.projectName=grind-loop \
		-Dsonar.sources=. \
		-Dsonar.exclusions="**/*test*/**,**/tests/**,**/__pycache__/**,**/venv/**,**/.venv/**,**/node_modules/**,**/tools/**,**/site/**,**/docs/**" \
		-Dsonar.python.coverage.reportPaths=coverage.xml \
		-Dsonar.host.url=http://192.168.x.x:9200 \
		-Dsonar.token="$$TOKEN"; \
	echo ""; \
	echo "Analysis complete! View results at:"; \
	echo "http://192.168.x.x:9200/dashboard?id=grind-loop"

# Help
help:
	@echo "Grind Loop - Available Make Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          - Install dependencies with uv"
	@echo "  make install-dev      - Install with dev dependencies"
	@echo "  make install-commands - Install slash commands globally (~/.claude/commands)"
	@echo ""
	@echo "Testing:"
	@echo "  make test          - Run all tests"
	@echo "  make test-verbose  - Run tests with verbose output"
	@echo "  make test-file     - Run specific test file (use FILE=path/to/test.py)"
	@echo "  make test-cov      - Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          - Run ruff linting checks"
	@echo "  make lint-fix      - Run ruff and auto-fix issues"
	@echo "  make format        - Format code with ruff"
	@echo "  make format-check  - Check code formatting without changes"
	@echo "  make check         - Run format + lint + test (pre-commit check)"
	@echo "  make sonar-scan    - Run SonarQube scan with coverage (Project)"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs          - Sync SDK docs and start dev server"
	@echo "  make docs-serve    - Start MkDocs development server"
	@echo "  make docs-build    - Build static documentation site"
	@echo "  make docs-sync-sdk - Sync SDK docs from Anthropic"
	@echo ""
	@echo "Grind:"
	@echo "  make grind TASKS=path/to/tasks.yaml              - Run batch with interactive + verbose"
	@echo "  make grind-dag TASKS=path/to/tasks.yaml          - Run DAG mode (respects dependencies)"
	@echo "  make grind-dag-parallel TASKS=path/to/tasks.yaml - Run DAG with parallel execution (default: 3)"
	@echo "  make grind-dag-parallel TASKS=tasks.yaml PARALLEL=5 - Run DAG with 5 parallel workers"
	@echo ""
	@echo "Examples:"
	@echo "  make run-example       - Run simple grind example"
	@echo "  make run-example-batch - Run batch processing example"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         - Remove build artifacts and cache"
	@echo "  make clean-all     - Remove everything including venv"
	@echo ""
	@echo "Build:"
	@echo "  make build         - Build package for distribution"
