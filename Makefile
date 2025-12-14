.PHONY: test audit lint ci

test:
	python -m pytest tests/ -v

audit:
	python scripts/tenant_audit.py

lint:
	@echo "No linter configured yet"

ci: audit test
	@echo "CI checks passed"
