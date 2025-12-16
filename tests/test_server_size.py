#!/usr/bin/env python3
"""
Test to verify server.py refactoring constraints.
Ensures server.py remains thin and uses the dispatcher pattern.
"""
import os
import sys

def test_server_line_count():
    """Verify server.py is <= 450 lines"""
    server_path = os.path.join(os.path.dirname(__file__), '..', 'server.py')
    with open(server_path, 'r') as f:
        lines = f.readlines()
    line_count = len(lines)
    assert line_count <= 450, f"server.py has {line_count} lines, max is 450"
    print(f"✓ server.py has {line_count} lines (max 450)")

def test_no_legacy_dispatch_comments():
    """Verify old dispatch patterns are removed"""
    server_path = os.path.join(os.path.dirname(__file__), '..', 'server.py')
    with open(server_path, 'r') as f:
        content = f.read()
    
    forbidden_patterns = [
        "Dispatch to coupon domain",
        "Dispatch to forex domain",
        "Dispatch to subscription domain",
    ]
    
    for pattern in forbidden_patterns:
        assert pattern not in content, f"server.py still contains '{pattern}'"
    print("✓ No legacy dispatch comments found")

def test_no_excessive_elif_chains():
    """Verify there are no long elif chains for path dispatch"""
    server_path = os.path.join(os.path.dirname(__file__), '..', 'server.py')
    with open(server_path, 'r') as f:
        content = f.read()
    
    elif_count = content.count('elif parsed_path.path ==')
    assert elif_count <= 5, f"server.py has {elif_count} 'elif parsed_path.path ==' patterns (max 5)"
    print(f"✓ Found {elif_count} elif dispatch patterns (max 5)")

def test_dispatcher_imported():
    """Verify dispatcher is imported and used"""
    server_path = os.path.join(os.path.dirname(__file__), '..', 'server.py')
    with open(server_path, 'r') as f:
        content = f.read()
    
    assert 'from api.dispatch import dispatch_request' in content, "Missing dispatch_request import"
    assert 'dispatch_request(' in content, "dispatch_request not used"
    print("✓ Dispatcher is imported and used")

def test_pages_module_exists():
    """Verify handlers/pages.py exists and has required functions"""
    pages_path = os.path.join(os.path.dirname(__file__), '..', 'handlers', 'pages.py')
    assert os.path.exists(pages_path), "handlers/pages.py not found"
    
    with open(pages_path, 'r') as f:
        content = f.read()
    
    required_funcs = ['serve_login', 'serve_admin', 'serve_app', 'serve_setup', 'serve_coupon', 'serve_campaign']
    for func in required_funcs:
        assert f'def {func}(' in content, f"Missing function {func} in handlers/pages.py"
    print("✓ handlers/pages.py has all required page functions")

def test_dispatch_module_exists():
    """Verify api/dispatch.py exists and has dispatch_request"""
    dispatch_path = os.path.join(os.path.dirname(__file__), '..', 'api', 'dispatch.py')
    assert os.path.exists(dispatch_path), "api/dispatch.py not found"
    
    with open(dispatch_path, 'r') as f:
        content = f.read()
    
    assert 'def dispatch_request(' in content, "Missing dispatch_request function"
    print("✓ api/dispatch.py exists with dispatch_request function")

if __name__ == '__main__':
    test_server_line_count()
    test_no_legacy_dispatch_comments()
    test_no_excessive_elif_chains()
    test_dispatcher_imported()
    test_pages_module_exists()
    test_dispatch_module_exists()
    print("\n✅ All server refactoring tests passed!")
