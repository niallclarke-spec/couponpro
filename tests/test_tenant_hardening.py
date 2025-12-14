"""
Tenant Hardening CI Tests

Tests that enforce tenant isolation at the code level:
1. No default tenant_id in db.py function signatures
2. SQL outside db.py must pass tenant audit
3. Tenant audit script runs successfully

Run: pytest tests/test_tenant_hardening.py -v
"""

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestNoDefaultTenantId:
    """Test that db.py functions don't have default tenant_id values."""
    
    def test_no_default_tenant_id_in_db_signatures(self):
        """
        CI GATE: Ensure no function in db.py has tenant_id='entrylab' default.
        
        Rationale: Default tenant_id values can cause cross-tenant data access
        if callers forget to pass tenant_id explicitly.
        """
        db_path = Path(__file__).parent.parent / 'db.py'
        assert db_path.exists(), f"Cannot find db.py at {db_path}"
        
        content = db_path.read_text()
        
        pattern = r'def\s+\w+\s*\([^)]*tenant_id\s*=\s*[\'"][^\'"]+[\'"]'
        matches = list(re.finditer(pattern, content))
        
        if matches:
            issues = []
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                snippet = match.group()
                issues.append(f"  Line {line_num}: {snippet[:80]}...")
            
            issues_str = "\n".join(issues)
            assert False, (
                f"Found {len(matches)} function(s) with default tenant_id in db.py:\n"
                f"{issues_str}\n\n"
                f"Fix: Remove default value, make tenant_id required."
            )
    
    def test_no_tenant_id_default_anywhere_in_db(self):
        """
        Broader check: No tenant_id='entrylab' anywhere in db.py
        (catches both function signatures and variable assignments).
        """
        db_path = Path(__file__).parent.parent / 'db.py'
        content = db_path.read_text()
        
        pattern = r"tenant_id\s*=\s*['\"]entrylab['\"]"
        matches = list(re.finditer(pattern, content))
        
        if matches:
            issues = []
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                line_content = content.split('\n')[line_num - 1].strip()
                if 'def ' in line_content:
                    issues.append(f"  Line {line_num}: {line_content[:80]}...")
            
            if issues:
                issues_str = "\n".join(issues)
                assert False, (
                    f"Found tenant_id='entrylab' defaults in function signatures:\n"
                    f"{issues_str}"
                )


class TestTenantAuditCI:
    """Test that the tenant audit script passes."""
    
    def test_tenant_audit_passes(self):
        """
        CI GATE: Run the full tenant audit (all .py files).
        
        This ensures all UPDATE/DELETE queries on tenant-aware tables
        include tenant_id in the WHERE clause.
        """
        script_path = Path(__file__).parent.parent / 'scripts' / 'tenant_audit.py'
        assert script_path.exists(), f"Cannot find tenant_audit.py at {script_path}"
        
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            cwd=str(script_path.parent.parent)
        )
        
        assert result.returncode == 0, (
            f"Tenant audit failed!\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )
    
    def test_tenant_audit_db_only_passes(self):
        """
        CI GATE: Run the tenant audit in db-only mode.
        """
        script_path = Path(__file__).parent.parent / 'scripts' / 'tenant_audit.py'
        
        result = subprocess.run(
            [sys.executable, str(script_path), '--db-only'],
            capture_output=True,
            text=True,
            cwd=str(script_path.parent.parent)
        )
        
        assert result.returncode == 0, (
            f"Tenant audit (db-only) failed!\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )


class TestSqlOutsideDbPy:
    """Test that SQL outside db.py follows tenant isolation rules."""
    
    def test_no_unguarded_sql_in_schedulers(self):
        """
        Check that SQL in scheduler files includes tenant_id filtering
        for tenant-aware tables.
        """
        project_root = Path(__file__).parent.parent
        scheduler_files = [
            project_root / 'forex_scheduler.py',
            project_root / 'workers' / 'scheduler.py',
        ]
        
        tenant_aware_tables = [
            'campaigns', 'bot_usage', 'bot_users', 'broadcast_jobs',
            'forex_signals', 'forex_config', 'bot_config',
            'recent_phrases', 'telegram_subscriptions'
        ]
        
        issues = []
        
        for file_path in scheduler_files:
            if not file_path.exists():
                continue
            
            content = file_path.read_text()
            
            sql_pattern = r'cursor\.execute\s*\(\s*(?:f)?["\']([^"\']+)["\']'
            for match in re.finditer(sql_pattern, content, re.DOTALL):
                sql = match.group(1).upper()
                line_num = content[:match.start()].count('\n') + 1
                
                if 'UPDATE ' in sql or 'DELETE FROM ' in sql:
                    for table in tenant_aware_tables:
                        if table.upper() in sql:
                            if 'TENANT_ID' not in sql:
                                issues.append(
                                    f"{file_path.name}:{line_num} - "
                                    f"UPDATE/DELETE on {table} missing tenant_id"
                                )
        
        assert not issues, (
            f"Found SQL outside db.py missing tenant_id:\n" +
            "\n".join(f"  {i}" for i in issues)
        )


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
