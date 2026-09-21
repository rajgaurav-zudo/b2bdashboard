.PHONY: up down logs psql migrate test typecheck reset vm

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

# --import-mode=importlib: two dashboards may both ship tests/test_ingest.py,
# and the default import mode resolves them to the same module name and refuses
# to collect the second. This keeps a new dashboard from having to invent a
# unique basename for every test file it writes.
test:          ## always against the local database, never the linked project
	docker compose exec \
	  -e DATABASE_URL=postgresql://$${POSTGRES_USER:-b2b}:$${POSTGRES_PASSWORD:-b2b}@db:5432/$${POSTGRES_DB:-b2bdash} \
	  -e STORAGE_BACKEND=local \
	  api pytest /srv/api/tests /srv/dashboards -q --import-mode=importlib

typecheck:     ## tsc over the frontend
	docker compose exec web npx tsc -b --noEmit
