.PHONY: up down logs psql migrate test reset vm

vm:            ## start the colima VM (4 cpu / 8 GB / 60 GB)
	colima start --runtime docker --vm-type vz --cpu 4 --memory 8 --disk 60

up:            ## build and start db + api
	docker compose up -d --build
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

test:
	docker compose exec api pytest /srv/dashboards -q
