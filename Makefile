.PHONY: install prepare demo test eval api mcp

install:
	python -m pip install -e ".[all]"

prepare:
	incident-agent prepare

demo:
	incident-agent investigate 544fd51c-4edc-4780-baae-ba1d80a0acfc --dataset abnormal

test:
	pytest -q

eval:
	incident-agent evaluate

api:
	uvicorn incident_agent.api:app --host 0.0.0.0 --port 8000

mcp:
	incident-mcp
