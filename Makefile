.PHONY: install lint format typecheck test test-unit test-integration eval eval-offline playground server tf-fmt tf-validate

install:
	uv sync --extra dev

lint:
	uv run ruff check app tests
	uv run ruff format --check app tests

format:
	uv run ruff check --fix app tests
	uv run ruff format app tests

typecheck:
	uv run mypy app

test:
	uv run pytest tests/unit tests/integration

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

eval:
	uv run adk eval ./app tests/eval/evalsets/golden_advertiser_copilot.evalset.json \
		--config_file_path=tests/eval/eval_config.json \
		--print_detailed_results

eval-offline:
	uv run python tests/eval/run_offline_eval.py

playground:
	uv run adk web . --port 8080

server:
	uv run uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8080 --reload

tf-fmt:
	terraform fmt -check -recursive deployment/terraform

tf-validate:
	cd deployment/terraform/single-project && terraform init -backend=false && terraform validate
	cd deployment/terraform/cicd && terraform init -backend=false && terraform validate
