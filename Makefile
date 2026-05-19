.PHONY: up down logs ps psql redis-cli backend-shell test sim seed clean

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps

psql:
	docker compose exec postgres psql -U agentmint -d agentmint

redis-cli:
	docker compose exec redis redis-cli

backend-shell:
	docker compose exec backend bash

backend-restart:
	docker compose restart backend

test:
	docker compose exec backend pytest -v

sim:
	@test -n "$$CONNECTOR_TOKEN" || (echo "Set CONNECTOR_TOKEN first (see /my/agents/[id] in web UI)"; exit 1)
	python scripts/connector-sim.py

clean:
	docker compose down -v
	rm -rf web/.next web/node_modules backend/__pycache__
