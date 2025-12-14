"""
CI/Test Gate: Tenant Isolation Audit

This test ensures tenant_audit.py passes as part of the test suite.
If any UPDATE/DELETE queries on tenant-aware tables are missing tenant_id
filtering, this test will fail and block the build.

Run: pytest tests/test_tenant_audit_gate.py -v
"""

import subprocess
import sys
from pathlib import Path


def test_tenant_audit_passes():
    """
    Execute tenant_audit.py and fail if any isolation issues are found.
    
    This is a CI gate that prevents deploying code with tenant isolation leaks.
    """
    script_path = Path(__file__).parent.parent / "scripts" / "tenant_audit.py"
    
    assert script_path.exists(), f"Audit script not found at {script_path}"
    
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        cwd=script_path.parent.parent
    )
    
    if result.returncode != 0:
        print("\n" + "=" * 60)
        print("TENANT ISOLATION AUDIT FAILED")
        print("=" * 60)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print("=" * 60)
        raise AssertionError(
            "Tenant isolation audit failed! "
            "UPDATE/DELETE queries are missing tenant_id filtering. "
            "See output above for details."
        )
    
    print(result.stdout)
