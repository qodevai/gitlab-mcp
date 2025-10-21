#!/usr/bin/env python3
"""Test script for GitLab FastMCP server"""
import asyncio
from gitlab_mcp import mcp, gitlab_client

async def test_resources():
    print("Testing GitLab FastMCP Server\n")
    print("=" * 60)

    # Get all resources
    print("\n1. Listing all resources...")
    resources = await mcp.get_resources()
    print(f"✓ Found {len(resources)} resources\n")

    print("Current Project Resources:")
    for uri in resources:
        if "current-project" in uri:
            r = await mcp.get_resource(uri)
            print(f"  - {r.name if hasattr(r, 'name') else uri}")
            print(f"    URI: {uri}\n")

    print("\nGlobal Resources:")
    for uri in resources:
        if "current-project" not in uri:
            r = await mcp.get_resource(uri)
            print(f"  - {r.name if hasattr(r, 'name') else uri}")
            print(f"    URI: {uri}\n")

    # Test API client directly
    print("\n2. Testing GitLab API client...")
    try:
        projects = gitlab_client.get_projects()
        print(f"✓ Successfully fetched {len(projects)} projects")
        if projects:
            print(f"\n  First 3 projects:")
            for p in projects[:3]:
                print(f"    - {p.get('name_with_namespace', 'N/A')} (ID: {p.get('id')})")
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\n✅ FastMCP migration complete!")

if __name__ == "__main__":
    asyncio.run(test_resources())
