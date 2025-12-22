# Makefile for Social Media API
# Usage: make [target]

.DEFAULT_GOAL := help

# Variables
PYTHON := python3
PIP := pip3
PYTEST := pytest
ALEMBIC := alembic
DOCKER := docker
DOCKER_COMPOSE := docker-compose
VENV := venv
PYTHON_VERSION := 3.12

# Project directories
SRC_DIR := app
TEST_DIR := tests
SCRIPTS_DIR := scripts
DOCKER_DIR := docker
MIGRATIONS_DIR := alembic
REQUIREMENTS := requirements.txt
REQUIREMENTS_DEV := requirements-dev.txt

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

.PHONY: help install install-dev clean test test-cov lint format \
		run run-dev docker-build docker-up docker-down docker-logs \
		db-init db-reset db-migrate db-seed db-backup \
		deploy-staging deploy-production

# Help target
help: ## Show this help message
	@echo "Social Media API - Makefile Help"
	@echo "================================="
	@echo ""
	@echo "Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${YELLOW}%-25s${NC} %s\n", $$1, $$2}'
	@echo ""

# Environment Setup
setup: venv install-dev ## Setup development environment

venv: ## Create Python virtual environment
	@echo "${BLUE}Creating virtual environment...${NC}"
	@$(PYTHON) -m venv $(VENV)
	@echo "${GREEN}Virtual environment created${NC}"

activate: ## Activate virtual environment
	@echo "${YELLOW}Run: source $(VENV)/bin/activate${NC}"

# Installation
install: ## Install production dependencies
	@echo "${BLUE}Installing production dependencies...${NC}"
	@$(PIP) install -r $(REQUIREMENTS)
	@echo "${GREEN}Production dependencies installed${NC}"

install-dev: ## Install development dependencies
	@echo "${BLUE}Installing development dependencies...${NC}"
	@if [ -f "$(REQUIREMENTS_DEV)" ]; then \
		$(PIP) install -r $(REQUIREMENTS_DEV); \
	else \
		$(PIP) install -r $(REQUIREMENTS); \
		$(PIP) install pytest pytest-cov pytest-asyncio black flake8 mypy bandit safety; \
	fi
	@echo "${GREEN}Development dependencies installed${NC}"

upgrade-deps: ## Upgrade all dependencies
	@echo "${BLUE}Upgrading dependencies...${NC}"
	@$(PIP) install --upgrade pip
	@$(PIP) install --upgrade -r $(REQUIREMENTS)
	@if [ -f "$(REQUIREMENTS_DEV)" ]; then \
		$(PIP) install --upgrade -r $(REQUIREMENTS_DEV); \
	fi
	@echo "${GREEN}Dependencies upgraded${NC}"

freeze: ## Freeze dependencies to requirements.txt
	@echo "${BLUE}Freezing dependencies...${NC}"
	@$(PIP) freeze > $(REQUIREMENTS)
	@echo "${GREEN}Dependencies frozen to $(REQUIREMENTS)${NC}"

# Development
run: ## Run the application
	@echo "${BLUE}Starting application...${NC}"
	@$(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-dev: ## Run with development settings
	@echo "${BLUE}Starting application in development mode...${NC}"
	@ENVIRONMENT=development $(PYTHON) -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

run-prod: ## Run with production settings
	@echo "${BLUE}Starting application in production mode...${NC}"
	@ENVIRONMENT=production $(PYTHON) -m gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Testing
test: ## Run all tests
	@echo "${BLUE}Running tests...${NC}"
	@ENVIRONMENT=testing $(PYTEST) $(TEST_DIR) -v

test-unit: ## Run unit tests only
	@echo "${BLUE}Running unit tests...${NC}"
	@ENVIRONMENT=testing $(PYTEST) $(TEST_DIR)/unit -v

test-integration: ## Run integration tests only
	@echo "${BLUE}Running integration tests...${NC}"
	@ENVIRONMENT=testing $(PYTEST) $(TEST_DIR)/integration -v

test-file: ## Run specific test file
	@echo "${BLUE}Running tests in $(file)...${NC}"
	@ENVIRONMENT=testing $(PYTEST) $(file) -v

test-cov: ## Run tests with coverage
	@echo "${BLUE}Running tests with coverage...${NC}"
	@ENVIRONMENT=testing $(PYTEST) $(TEST_DIR) -v --cov=$(SRC_DIR) --cov-report=html --cov-report=term

test-cov-xml: ## Run tests with XML coverage report
	@echo "${BLUE}Running tests with XML coverage...${NC}"
	@ENVIRONMENT=testing $(PYTEST) $(TEST_DIR) --cov=$(SRC_DIR) --cov-report=xml

test-watch: ## Run tests in watch mode (requires pytest-watch)
	@echo "${BLUE}Running tests in watch mode...${NC}"
	@ENVIRONMENT=testing ptw --now . -- $(TEST_DIR)

# Code Quality
lint: ## Run linter (flake8)
	@echo "${BLUE}Running linter...${NC}"
	@flake8 $(SRC_DIR) $(TEST_DIR) --max-line-length=88 --exclude=$(VENV)

format: ## Format code with black
	@echo "${BLUE}Formatting code...${NC}"
	@black $(SRC_DIR) $(TEST_DIR) $(SCRIPTS_DIR)

format-check: ## Check code formatting without changes
	@echo "${BLUE}Checking code formatting...${NC}"
	@black --check $(SRC_DIR) $(TEST_DIR) $(SCRIPTS_DIR)

type-check: ## Run type checking with mypy
	@echo "${BLUE}Running type checking...${NC}"
	@mypy $(SRC_DIR) --ignore-missing-imports

security-check: ## Run security checks
	@echo "${BLUE}Running security checks...${NC}"
	@bandit -r $(SRC_DIR) -f html -o security-report.html
	@safety check

# Database
db-init: ## Initialize database
	@echo "${BLUE}Initializing database...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/db_init.py init

db-reset: ## Reset database (DANGEROUS!)
	@echo "${RED}WARNING: This will reset the database!${NC}"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		$(PYTHON) $(SCRIPTS_DIR)/db_init.py reset --confirm; \
	else \
		echo "Reset cancelled"; \
	fi

db-migrate: ## Run database migrations
	@echo "${BLUE}Running database migrations...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/migrate.py upgrade

db-migrate-create: ## Create new migration
	@echo "${BLUE}Creating new migration...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/migrate.py create "$(message)"

db-migrate-status: ## Show migration status
	@echo "${BLUE}Migration status:${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/migrate.py status

db-migrate-history: ## Show migration history
	@echo "${BLUE}Migration history:${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/migrate.py history

db-seed: ## Seed database with sample data
	@echo "${BLUE}Seeding database...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/seed_data.py all

db-seed-test: ## Seed database with test data
	@echo "${BLUE}Seeding test data...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/seed_data.py test

db-backup: ## Backup database
	@echo "${BLUE}Backing up database...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/backup_db.py backup

db-backup-list: ## List database backups
	@echo "${BLUE}Listing backups...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/backup_db.py list

db-backup-auto: ## Run automatic backup with rotation
	@echo "${BLUE}Running automatic backup...${NC}"
	@$(PYTHON) $(SCRIPTS_DIR)/backup_db.py auto --keep 7

# Docker
docker-build: ## Build Docker images
	@echo "${BLUE}Building Docker images...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml build

docker-up: ## Start Docker containers
	@echo "${BLUE}Starting Docker containers...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml up -d

docker-down: ## Stop Docker containers
	@echo "${BLUE}Stopping Docker containers...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml down

docker-down-clean: ## Stop Docker containers and remove volumes
	@echo "${BLUE}Stopping Docker containers and removing volumes...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml down -v

docker-logs: ## Show Docker container logs
	@echo "${BLUE}Showing Docker logs...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml logs -f

docker-logs-app: ## Show application container logs
	@echo "${BLUE}Showing application logs...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml logs -f fastapi-app

docker-logs-db: ## Show database container logs
	@echo "${BLUE}Showing database logs...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml logs -f postgres

docker-restart: ## Restart Docker containers
	@echo "${BLUE}Restarting Docker containers...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml restart

docker-ps: ## Show running Docker containers
	@echo "${BLUE}Running containers:${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml ps

docker-shell: ## Open shell in app container
	@echo "${BLUE}Opening shell in app container...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml exec fastapi-app /bin/bash

docker-migrate: ## Run migrations in Docker
	@echo "${BLUE}Running migrations in Docker...${NC}"
	@$(DOCKER_COMPOSE) -f $(DOCKER_DIR)/docker-compose.yml run --rm db-migrate

# Deployment
deploy-staging: ## Deploy to staging environment
	@echo "${BLUE}Deploying to staging...${NC}"
	@# Add your staging deployment commands here
	@echo "${GREEN}Deployed to staging${NC}"

deploy-production: ## Deploy to production environment
	@echo "${BLUE}Deploying to production...${NC}"
	@read -p "Are you sure you want to deploy to production? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo "Starting production deployment..."; \
		# Add your production deployment commands here \
		echo "${GREEN}Deployed to production${NC}"; \
	else \
		echo "Deployment cancelled"; \
	fi

# Documentation
docs-generate: ## Generate API documentation
	@echo "${BLUE}Generating API documentation...${NC}"
	@# Add documentation generation commands here
	@echo "${GREEN}Documentation generated${NC}"

docs-serve: ## Serve documentation locally
	@echo "${BLUE}Serving documentation...${NC}"
	@# Add documentation serving commands here
	@echo "${GREEN}Documentation served at http://localhost:8000/docs${NC}"

# Cleanup
clean: clean-pyc clean-test clean-build clean-docker ## Clean all generated files

clean-pyc: ## Remove Python cache files
	@echo "${BLUE}Cleaning Python cache files...${NC}"
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*.pyd" -delete
	@find . -type f -name ".coverage" -delete
	@find . -type f -name "coverage.xml" -delete
	@echo "${GREEN}Python cache cleaned${NC}"

clean-test: ## Remove test artifacts
	@echo "${BLUE}Cleaning test artifacts...${NC}"
	@rm -rf .pytest_cache/
	@rm -rf htmlcov/
	@rm -rf .coverage
	@rm -rf test-results/
	@rm -rf .mypy_cache/
	@rm -rf .benchmarks/
	@echo "${GREEN}Test artifacts cleaned${NC}"

clean-build: ## Remove build artifacts
	@echo "${BLUE}Cleaning build artifacts...${NC}"
	@rm -rf build/
	@rm -rf dist/
	@rm -rf *.egg-info/
	@rm -rf .eggs/
	@rm -rf pip-wheel-metadata/
	@echo "${GREEN}Build artifacts cleaned${NC}"

clean-docker: ## Remove Docker artifacts
	@echo "${BLUE}Cleaning Docker artifacts...${NC}"
	@$(DOCKER) system prune -f
	@$(DOCKER) volume prune -f
	@echo "${GREEN}Docker artifacts cleaned${NC}"

clean-data: ## Remove data files
	@echo "${BLUE}Cleaning data files...${NC}"
	@rm -rf backups/
	@rm -f *.db
	@rm -f *.sqlite
	@rm -rf uploads/
	@rm -rf static/media/
	@echo "${GREEN}Data files cleaned${NC}"

# Monitoring
monitor-logs: ## Monitor application logs
	@echo "${BLUE}Monitoring logs...${NC}"
	@tail -f logs/app.log

monitor-metrics: ## Monitor application metrics
	@echo "${BLUE}Monitoring metrics...${NC}"
	@# Add metrics monitoring commands here
	@echo "${GREEN}Metrics monitoring started${NC}"

# Health Checks
health-check: ## Run health checks
	@echo "${BLUE}Running health checks...${NC}"
	@curl -f http://localhost:8000/health || echo "${RED}Health check failed${NC}"
	@curl -f http://localhost:8000/api/docs || echo "${RED}API docs not available${NC}"
	@echo "${GREEN}Health checks completed${NC}"

# Development Workflow
dev-start: clean install-dev db-init db-migrate db-seed run-dev ## Start development environment

dev-stop: docker-down clean ## Stop development environment

dev-restart: dev-stop dev-start ## Restart development environment

# Git Hooks
install-hooks: ## Install git hooks
	@echo "${BLUE}Installing git hooks...${NC}"
	@cp scripts/git-hooks/* .git/hooks/
	@chmod +x .git/hooks/*
	@echo "${GREEN}Git hooks installed${NC}"

# Backup and Restore
backup-all: db-backup ## Backup everything
	@echo "${BLUE}Backing up everything...${NC}"
	@tar -czf backup_$(shell date +%Y%m%d_%H%M%S).tar.gz \
		--exclude=$(VENV) \
		--exclude=*.pyc \
		--exclude=__pycache__ \
		--exclude=*.db \
		--exclude=*.sqlite \
		.
	@echo "${GREEN}Full backup created${NC}"

# Utility
size: ## Show project size
	@echo "${BLUE}Project size:${NC}"
	@du -sh .
	@echo ""
	@echo "${BLUE}Directory sizes:${NC}"
	@du -sh */
	@du -sh .* 2>/dev/null | grep -v "^\.\." | grep -v "^\.$"

tree: ## Show project tree structure
	@echo "${BLUE}Project tree:${NC}"
	@tree -I "$(VENV)|__pycache__|*.pyc|*.db|*.sqlite|backups|uploads" -a

env: ## Show environment variables
	@echo "${BLUE}Environment variables:${NC}"
	@env | sort

requirements: ## Show installed packages
	@echo "${BLUE}Installed packages:${NC}"
	@$(PIP) list

version: ## Show version information
	@echo "${BLUE}Version information:${NC}"
	@echo "Python: $$($(PYTHON) --version)"
	@echo "Pip: $$($(PIP) --version)"
	@echo "Docker: $$($(DOCKER) --version 2>/dev/null || echo 'Not installed')"
	@echo "Docker Compose: $$($(DOCKER_COMPOSE) --version 2>/dev/null || echo 'Not installed')"

# Alias for common commands
up: docker-up ## Alias for docker-up
down: docker-down ## Alias for docker-down
logs: docker-logs ## Alias for docker-logs
build: docker-build ## Alias for docker-build
ps: docker-ps ## Alias for docker-ps
migrate: db-migrate ## Alias for db-migrate
seed: db-seed ## Alias for db-seed