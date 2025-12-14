.PHONY: test audit lint ci smoke

test:
	python -m pytest tests/ -v

audit:
	python scripts/tenant_audit.py

smoke:
	python scripts/smoke_tenant_isolation.py

lint:
	@echo "No linter configured yet"

ci: audit test
ifdef DATABASE_URL
	$(MAKE) smoke
endif
	@echo "CI checks passed"
