# Decalove — the commands you actually run, in one place.
#
#   make            what this file offers
#   make up         build and start the whole stack in Docker
#   make check      everything CI would ask of a change, in the order it fails fastest
#
# Running the stack is deploy.sh's job and stays there: it is the thing that knows about
# COMPOSE_FILE, the health wait and which ports were really published. These targets are
# a shorter way to call it, plus the test and lint entry points it has no business
# owning. Anything that needs a flag deploy.sh already has is `./deploy.sh` with it.

API  := api
WEB  := frontend

# dash on Ubuntu, bash on macOS -- recipes stay POSIX so it does not matter which.
SHELL := /bin/sh

# Nothing here produces a file named after its target.
.PHONY: help up up-gpu up-no-web restart down logs ps env \
        check test test-api test-web lint build-web clean-web install

.DEFAULT_GOAL := help

help: ## Show this help
	@printf 'Decalove\n\n'
	@grep -hE '^[a-z][a-z-]*:.*## ' $(MAKEFILE_LIST) \
		| sort \
		| awk -F':[^#]*## ' '{ printf "  %-12s %s\n", $$1, $$2 }'
	@printf '\nConfiguration is api/.env (see api/.env.example). `make env` creates it.\n'
	@printf 'Local SDXL needs `make up-gpu`: the default images carry no PyTorch.\n'

# -- the stack ------------------------------------------------------------------------

up: ## Build and start everything (game on :3000, API on :8000)
	./deploy.sh

up-gpu: ## ...with local SDXL on the GPU (the only path that installs PyTorch)
	./deploy.sh --gpu

up-no-web: ## API and workers only, for shipping the Ren'Py build instead
	./deploy.sh --no-web

restart: ## Restart without rebuilding images
	./deploy.sh --no-build

down: ## Stop everything, keeping saves and generated art
	./deploy.sh down

logs: ## Follow logs; make logs s=worker-story for one service
	./deploy.sh logs $(s)

ps: ## What is running
	./deploy.sh ps

env: $(API)/.env ## Create api/.env from the example if it does not exist

$(API)/.env:
	cp $(API)/.env.example $@
	@printf 'created %s -- add OPENROUTER_API_KEY to have the model write the story.\n' "$@"

# -- verification ---------------------------------------------------------------------

check: test-api lint test-web build-web ## Everything AGENTS.md asks for before handing work back
	@git diff --check
	@printf '\nall checks passed.\n'

test: test-api test-web ## Both test suites

test-api: ## API tests (offline providers; MongoDB/MinIO tests skip when absent)
	cd $(API) && .venv/bin/python -m pytest -q

test-web: ## Client tests
	cd $(WEB) && npm test

lint: ## Lint the client
	cd $(WEB) && npm run lint

build-web: ## Production build of the client
	cd $(WEB) && npm run build

install: ## Install both dependency sets for local (non-Docker) development
	cd $(API) && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd $(WEB) && npm install
	@printf '\nSDXL extras are deliberately not installed: see api/requirements-sdxl.txt.\n'

clean-web: ## Remove the client build output
	rm -rf $(WEB)/dist
