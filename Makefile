.PHONY: help build up down logs shell test clean migrate seed rebuild clear-timeslots clear-timeslots-script

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build Docker images
	docker-compose build

rebuild: ## Rebuild images (no cache) and recreate web/worker
	docker-compose build --no-cache web worker
	docker-compose up -d --force-recreate web worker

clear-timeslots: ## Truncate all timeslots (and related via CASCADE)
	docker-compose exec db psql -U postgres -d turnos -c "TRUNCATE TABLE timeslots RESTART IDENTITY CASCADE;"

clear-timeslots-script: ## Delete all timeslots and subscriptions via app script
	docker-compose exec web python scripts/clear_timeslots.py

up: ## Start all services
	docker-compose up -d

up-dev: ## Start all services including MailHog for development
	docker-compose --profile dev up -d

down: ## Stop all services
	docker-compose down

logs: ## Show logs for all services
	docker-compose logs -f

logs-web: ## Show logs for web service
	docker-compose logs -f web

logs-worker: ## Show logs for worker service
	docker-compose logs -f worker

shell: ## Open shell in web container
	docker-compose exec web bash

shell-db: ## Open PostgreSQL shell
	docker-compose exec db psql -U postgres -d turnos

test: ## Run tests
	docker-compose exec web python -m pytest

migrate: ## Run database migrations
	docker-compose exec web flask db upgrade

migrate-create: ## Create new migration (usage: make migrate-create MESSAGE="description")
	docker-compose exec web flask db migrate -m "$(MESSAGE)"

seed: ## Seed database with initial data
	docker-compose exec web python scripts/seed_data.py

test-email: ## Send test email (usage: make test-email EMAIL=test@example.com)
	docker-compose exec worker python scripts/test_email.py $(EMAIL)

clean: ## Clean up Docker resources
	docker-compose down -v
	docker system prune -f

prod-up: ## Start production environment
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

prod-down: ## Stop production environment
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml down

backup-db: ## Backup database
	docker-compose exec db pg_dump -U postgres turnos > backup_$(shell date +%Y%m%d_%H%M%S).sql

restore-db: ## Restore database (usage: make restore-db FILE=backup.sql)
	docker-compose exec -T db psql -U postgres turnos < $(FILE)

health: ## Check health of all services
	@echo "Checking service health..."
	@docker-compose ps
	@echo ""
	@echo "Web service health:"
	@curl -f http://localhost:8000/ > /dev/null 2>&1 && echo "✅ Web service is healthy" || echo "❌ Web service is unhealthy"
	@echo ""
	@echo "MailHog UI (if running): http://localhost:8025"
