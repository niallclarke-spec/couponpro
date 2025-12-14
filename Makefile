.PHONY: test audit lint ci smoke check-db

test:
	python -m pytest tests/ -v

audit:
	python scripts/tenant_audit.py

smoke:
	python scripts/smoke_tenant_isolation.py

check-db:
	@python -c "import os; import sys; sys.exit(0 if os.environ.get('DATABASE_URL') else 1)" 2>/dev/null || echo "DATABASE_URL not set"

lint:
	@echo "No linter configured yet"

ci: audit test
ifeq ($(CI),true)
ifdef DATABASE_URL
	@echo "CI mode with DATABASE_URL: running smoke test"
	$(MAKE) smoke
else
	@echo "CI mode without DATABASE_URL: smoke test will fail appropriately"
	$(MAKE) smoke
endif
else
	@echo "Local mode: skipping smoke test in CI target"
endif
	@echo "CI checks passed"

cold-import:
	@python -c "import forex_scheduler; import scheduler.runner; import core.runtime; import strategies; import bots.strategies; print('Cold import OK')"
