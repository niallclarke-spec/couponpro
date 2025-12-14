#!/usr/bin/env python3
"""
Metrics Endpoint CLI Helper

Fetches and displays tenant metrics from the API endpoint.
Uses Python's built-in JSON formatting (no jq dependency).

Usage:
    python scripts/get_metrics.py --tenant-id entrylab
    python scripts/get_metrics.py --tenant-id entrylab --days 30
    python scripts/get_metrics.py --tenant-id entrylab --base-url http://localhost:5000

Exit codes:
    0 = Success
    1 = Request failed or non-200 response
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error


def get_base_url():
    """Get the base URL for the API."""
    return os.environ.get('API_BASE_URL', 'http://localhost:5000')


def fetch_metrics(base_url: str, tenant_id: str, days: int = 7, auth_token: str = None) -> dict:
    """
    Fetch metrics from the API endpoint.
    
    Args:
        base_url: API base URL
        tenant_id: Tenant identifier
        days: Number of days to fetch (default 7)
        auth_token: Optional auth token
    
    Returns:
        Parsed JSON response
    
    Raises:
        Exception on request failure
    """
    url = f"{base_url}/api/metrics/tenant?days={days}"
    
    headers = {
        'Content-Type': 'application/json',
        'X-Tenant-Id': tenant_id,
    }
    
    if auth_token:
        headers['Authorization'] = f'Bearer {auth_token}'
    
    req = urllib.request.Request(url, headers=headers, method='GET')
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                raise Exception(f"HTTP {response.status}: {response.reason}")
            
            body = response.read().decode('utf-8')
            return json.loads(body)
    
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise Exception(f"Connection error: {e.reason}")


def print_metrics(metrics: dict, indent: int = 2):
    """Pretty-print metrics as formatted JSON."""
    print(json.dumps(metrics, indent=indent, sort_keys=True, default=str))


def main():
    parser = argparse.ArgumentParser(description='Fetch and display tenant metrics')
    parser.add_argument('--tenant-id', type=str, required=True,
                        help='Tenant ID to fetch metrics for')
    parser.add_argument('--days', type=int, default=7,
                        help='Number of days to fetch (default: 7)')
    parser.add_argument('--base-url', type=str, default=None,
                        help='API base URL (default: http://localhost:5000 or API_BASE_URL env)')
    parser.add_argument('--auth-token', type=str, default=None,
                        help='Authorization token (optional)')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress status messages, only output JSON')
    
    args = parser.parse_args()
    
    base_url = args.base_url or get_base_url()
    
    if not args.quiet:
        print(f"Fetching metrics for tenant: {args.tenant_id}", file=sys.stderr)
        print(f"  Days: {args.days}", file=sys.stderr)
        print(f"  URL: {base_url}/api/metrics/tenant", file=sys.stderr)
    
    try:
        metrics = fetch_metrics(
            base_url=base_url,
            tenant_id=args.tenant_id,
            days=args.days,
            auth_token=args.auth_token
        )
        
        print_metrics(metrics)
        
        if not args.quiet:
            print(f"\n✅ Successfully fetched metrics", file=sys.stderr)
        
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
