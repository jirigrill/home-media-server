# Home Media Server Makefile
# Provides convenient commands for managing the Docker Compose stack

.PHONY: help up down restart logs status pull build clean network backup restore dev test lint format

# Default target
help: ## Show this help message
	@echo "Home Media Server Management Commands"
	@echo "=================================="
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Stack Management
up: ## Start the entire media server stack
	@echo "Starting media server stack..."
	docker-compose up -d

down: ## Stop the entire media server stack
	@echo "Stopping media server stack..."
	docker-compose down

restart: ## Restart the entire media server stack
	@echo "Restarting media server stack..."
	docker-compose down && docker-compose up -d

# Service Management
up-%: ## Start a specific service (e.g., make up-jellyfin)
	@echo "Starting $* service..."
	docker-compose up -d $*

down-%: ## Stop a specific service (e.g., make down-jellyfin)
	@echo "Stopping $* service..."
	docker-compose stop $*

restart-%: ## Restart a specific service (e.g., make restart-jellyfin)
	@echo "Restarting $* service..."
	docker-compose restart $*

# Monitoring
logs: ## Show logs for all services
	docker-compose logs -f

logs-%: ## Show logs for a specific service (e.g., make logs-deleterr)
	docker-compose logs -f $*

status: ## Show status of all services
	@echo "Service Status:"
	@echo "=============="
	docker-compose ps

# Updates and Maintenance
pull: ## Pull latest Docker images
	@echo "Pulling latest images..."
	docker-compose pull

build: ## Build custom services (deleterr)
	@echo "Building custom services..."
	docker-compose build

update: pull ## Update all services (pull + restart)
	@echo "Updating and restarting services..."
	docker-compose up -d

# Development
dev: ## Start stack in development mode with build
	@echo "Starting in development mode..."
	docker-compose up -d --build

# Deleterr Development
deleterr-dev: ## Enter deleterr development environment
	@echo "Entering deleterr directory..."
	@echo "Available commands:"
	@echo "  uv pip install -e \".[dev]\" - Install dev dependencies"
	@echo "  pytest                     - Run tests"
	@echo "  pytest --cov=.            - Run tests with coverage"
	@echo "  black .                   - Format code"
	@echo "  flake8                    - Lint code"
	@echo "  mypy .                    - Type checking"
	cd deleterr

deleterr-test: ## Run deleterr tests
	cd deleterr && uv run pytest

deleterr-test-cov: ## Run deleterr tests with coverage
	cd deleterr && uv run pytest --cov=. --cov-report=html

deleterr-format: ## Format deleterr code
	cd deleterr && uv run black .

deleterr-lint: ## Lint deleterr code
	cd deleterr && uv run flake8

deleterr-typecheck: ## Type check deleterr code
	cd deleterr && uv run mypy .

deleterr-check: deleterr-format deleterr-lint deleterr-typecheck deleterr-test ## Run all deleterr quality checks

# Network and Setup
network: ## Create the required external network
	@echo "Creating media_server network..."
	docker network create media_server || echo "Network already exists"

# Cleanup
clean: ## Remove unused Docker resources
	@echo "Cleaning up unused Docker resources..."
	docker system prune -f

clean-all: ## Remove all containers, images, and volumes (DESTRUCTIVE)
	@echo "WARNING: This will remove all containers, images, and volumes!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		docker system prune -a -f --volumes; \
	fi

# Backup and Restore
backup: ## Backup configuration data
	@echo "Creating backup of configuration data..."
	@mkdir -p backups
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	echo "Backing up to backups/media_server_backup_$$timestamp.tar.gz"; \
	docker run --rm -v media_server_qbittorrent_data:/data/qbittorrent \
		-v media_server_jellyfin_data:/data/jellyfin \
		-v media_server_prowlarr_data:/data/prowlarr \
		-v media_server_sonarr_data:/data/sonarr \
		-v media_server_radarr_data:/data/radarr \
		-v media_server_bazarr_data:/data/bazarr \
		-v media_server_huntarr_data:/data/huntarr \
		-v media_server_cleanuparr_data:/data/cleanuparr \
		-v media_server_deleterr_data:/data/deleterr \
		-v $$(pwd)/backups:/backup \
		alpine:latest \
		tar czf /backup/media_server_backup_$$timestamp.tar.gz -C /data .

restore: ## Restore configuration data from backup
	@echo "Available backups:"
	@ls -la backups/media_server_backup_*.tar.gz 2>/dev/null || echo "No backups found"
	@echo "To restore, run: make restore-backup BACKUP=filename.tar.gz"

restore-backup: ## Restore from specific backup file (use BACKUP=filename)
	@if [ -z "$(BACKUP)" ]; then \
		echo "Error: Please specify BACKUP=filename.tar.gz"; \
		exit 1; \
	fi
	@echo "Restoring from $(BACKUP)..."
	@echo "WARNING: This will overwrite current configuration!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down; \
		docker run --rm -v media_server_qbittorrent_data:/data/qbittorrent \
			-v media_server_jellyfin_data:/data/jellyfin \
			-v media_server_prowlarr_data:/data/prowlarr \
			-v media_server_sonarr_data:/data/sonarr \
			-v media_server_radarr_data:/data/radarr \
			-v media_server_bazarr_data:/data/bazarr \
			-v media_server_huntarr_data:/data/huntarr \
			-v media_server_cleanuparr_data:/data/cleanuparr \
			-v media_server_deleterr_data:/data/deleterr \
			-v $$(pwd)/backups:/backup \
			alpine:latest \
			tar xzf /backup/$(BACKUP) -C /data; \
		echo "Backup restored. Starting services..."; \
		docker-compose up -d; \
	fi

# Health Checks
health: ## Check health of all services
	@echo "Service Health Check:"
	@echo "==================="
	@services="jellyfin qbittorrent prowlarr sonarr radarr bazarr huntarr cleanuparr deleterr"; \
	for service in $$services; do \
		echo -n "$$service: "; \
		if docker-compose ps $$service | grep -q "Up"; then \
			echo "✓ Running"; \
		else \
			echo "✗ Stopped"; \
		fi; \
	done

# Environment
init-env: ## Create .env file from .env.example
	@if [ ! -f .env ]; then \
		echo "Creating .env file from .env.example..."; \
		cp .env.example .env; \
		echo "✅ .env file created. Please edit it with your actual values."; \
	else \
		echo "⚠️  .env file already exists. Use 'make reset-env' to overwrite."; \
	fi

reset-env: ## Reset .env file from .env.example (overwrites existing)
	@echo "Resetting .env file from .env.example..."
	cp .env.example .env
	@echo "✅ .env file reset. Please edit it with your actual values."

check-env: ## Check if .env file exists and has required variables
	@echo "Checking environment configuration..."
	@if [ ! -f .env ]; then \
		echo "❌ .env file not found!"; \
		echo "Run 'make init-env' to create from .env.example"; \
		exit 1; \
	else \
		echo "✅ .env file found"; \
	fi
	@required_vars="SONARR_API_KEY RADARR_API_KEY DOWNLOADS_PATH SHOWS_PATH MOVIES_PATH PUID PGID TZ"; \
	missing_vars=""; \
	for var in $$required_vars; do \
		if ! grep -q "^$$var=" .env; then \
			missing_vars="$$missing_vars $$var"; \
		fi; \
	done; \
	if [ -n "$$missing_vars" ]; then \
		echo "❌ Missing required variables:$$missing_vars"; \
		echo "See .env.example for reference"; \
		exit 1; \
	else \
		echo "✅ All required variables found"; \
	fi

# Quick start sequence
setup: network check-env ## Initial setup (create network and check environment)
	@echo "✅ Setup complete! Run 'make up' to start the stack."

quick-start: setup up ## Complete setup and start services
	@echo "🚀 Media server is starting up!"
	@echo "Services will be available at:"
	@echo "  Jellyfin:     http://localhost:$$(grep JELLYFIN_PORT .env | cut -d= -f2)"
	@echo "  qBittorrent:  http://localhost:$$(grep QBITTORRENT_UI_PORT .env | cut -d= -f2)"
	@echo "  Prowlarr:     http://localhost:$$(grep PROWLARR_PORT .env | cut -d= -f2)"
	@echo "  Sonarr:       http://localhost:$$(grep SONARR_PORT .env | cut -d= -f2)"
	@echo "  Radarr:       http://localhost:$$(grep RADARR_PORT .env | cut -d= -f2)"
	@echo "  Bazarr:       http://localhost:$$(grep BAZARR_PORT .env | cut -d= -f2)"
	@echo "  Huntarr:      http://localhost:$$(grep HUNTARR_PORT .env | cut -d= -f2)"
	@echo "  Cleanuparr:   http://localhost:$$(grep CLEANUPARR_PORT .env | cut -d= -f2)"
	@echo "  Deleterr:     http://localhost:$$(grep DELETERR_PORT .env | cut -d= -f2)"