.PHONY: up down logs psql migrate test typecheck reset vm supabase-link supabase-push migrate-remote psql-remote

vm:            ## start the colima VM (4 cpu / 8 GB / 60 GB)
	colima start --runtime docker --vm-type vz --cpu 4 --memory 8 --disk 60

up:            ## build and start db + api + web
	docker compose up -d --build
	@echo "app  http://localhost:$${WEB_PORT:-5173}"
	@echo "api  http://localhost:$${API_PORT:-8000}/docs"

down:
	docker compose down

reset:         ## drop the database volume and start clean
	docker compose down -v && docker compose up -d --build

logs:
	docker compose logs -f api

psql:
	docker compose exec db psql -U $${POSTGRES_USER:-b2b} -d $${POSTGRES_DB:-b2bdash}

migrate:       ## apply core + every dashboard migration
	docker compose exec api python -m app.migrate

test:          ## always against the local database, never the linked project
	docker compose exec \
	  -e DATABASE_URL=postgresql://$${POSTGRES_USER:-b2b}:$${POSTGRES_PASSWORD:-b2b}@db:5432/$${POSTGRES_DB:-b2bdash} \
	  -e STORAGE_BACKEND=local \
	  api pytest /srv/api/tests /srv/dashboards -q

typecheck:     ## tsc over the frontend
	docker compose exec web npx tsc -b --noEmit

# --- Supabase ----------------------------------------------------------------
# Secrets come from .env, which is gitignored. Passing them as command-line flags
# would put them in the process table, so they go through the environment and are
# never echoed.

supabase-link: ## authenticate the CLI and link the remote project
	@set -a; . ./.env; set +a; \
	if [ -z "$$SUPABASE_ACCESS_TOKEN" ]; then \
	  echo "SUPABASE_ACCESS_TOKEN is not set in .env."; \
	  echo "Create one at https://supabase.com/dashboard/account/tokens"; \
	  echo "(or just run: supabase login)"; exit 1; \
	fi; \
	if [ -z "$$SUPABASE_DB_PASSWORD" ]; then \
	  echo "SUPABASE_DB_PASSWORD is not set in .env (Settings > Database)."; exit 1; \
	fi; \
	supabase login --token "$$SUPABASE_ACCESS_TOKEN" --name b2bdash >/dev/null && \
	supabase link --project-ref "$$SUPABASE_PROJECT_REF"

supabase-push: ## apply supabase/migrations to the linked project
	@set -a; . ./.env; set +a; supabase db push

migrate-remote: ## apply core + dashboard migrations to the Supabase project
	@set -a; . ./.env; set +a; \
	if [ -z "$$SUPABASE_DATABASE_URL" ]; then echo "SUPABASE_DATABASE_URL is not set in .env"; exit 1; fi; \
	docker compose run --rm -e DATABASE_URL="$$SUPABASE_DATABASE_URL" api python -m app.migrate

psql-remote:   ## psql against the Supabase project
	@set -a; . ./.env; set +a; \
	docker compose exec -e PGPASSWORD="$$SUPABASE_DB_PASSWORD" -e PGCONNECT_TIMEOUT=15 db \
	  psql -h aws-0-ap-northeast-2.pooler.supabase.com -p 6543 \
	       -U "postgres.$$SUPABASE_PROJECT_REF" -d postgres
