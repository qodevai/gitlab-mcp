#!/usr/bin/env python3
"""Simple test script for GitLab MCP server"""
import asyncio
import json
from gitlab_mcp import create_server

async def test_server():
    print("Creating server...")
    server = create_server()

    print("\n1. Testing list_resources...")
    try:
        resources = await server._list_resources_handler()
        print(f"✓ Found {len(resources)} resources")
        print("\nFirst 5 resources:")
        for r in resources[:5]:
            print(f"  - {r.name}")
            print(f"    URI: {r.uri}")
            print(f"    Description: {r.description}\n")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n2. Testing read_resource for gitlab://projects/...")
    try:
        result = await server._read_resource_handler(uri="gitlab://projects/")
        data = json.loads(result)
        print(f"✓ Successfully read gitlab://projects/")
        print(f"  Found {len(data)} projects")
        if data:
            print(f"\n  First 3 projects:")
            for p in data[:3]:
                print(f"    - {p.get('name_with_namespace', 'N/A')}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n3. Testing read_resource for a specific project...")
    try:
        result = await server._read_resource_handler(uri="gitlab://projects/")
        projects = json.loads(result)
        if projects:
            project_id = projects[0]['id']
            result = await server._read_resource_handler(uri=f"gitlab://projects/{project_id}")
            project_data = json.loads(result)
            print(f"✓ Successfully read project {project_id}")
            print(f"  Name: {project_data.get('name', 'N/A')}")
            print(f"  Description: {project_data.get('description', 'N/A')}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_server())
