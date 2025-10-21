#!/usr/bin/env python3
"""Test script to debug current repository detection"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gitlab_mcp import find_git_root, parse_gitlab_remote, GitLabClient

load_dotenv()

# Test with the meinungsmonitor/app directory
test_path = os.path.expanduser("~/dev/meinungsmonitor/app")

print(f"Testing with path: {test_path}")
print(f"Path exists: {os.path.exists(test_path)}")
print()

# Test git root detection
git_root = find_git_root(test_path)
print(f"Git root found: {git_root}")
print()

if git_root:
    # Test GitLab remote parsing
    gitlab_client = GitLabClient()
    print(f"GitLab base URL: {gitlab_client.base_url}")

    project_path = parse_gitlab_remote(git_root, gitlab_client.base_url)
    print(f"Project path parsed: {project_path}")
    print()

    if project_path:
        # Try to fetch project info
        try:
            project = gitlab_client.get_project(project_path)
            print(f"✓ Project found on GitLab!")
            print(f"  ID: {project['id']}")
            print(f"  Name: {project['name']}")
            print(f"  Path with namespace: {project['path_with_namespace']}")
        except Exception as e:
            print(f"✗ Failed to fetch project from GitLab API:")
            print(f"  Error: {e}")
    else:
        print("✗ Could not parse project path from git remote")
        print("\nDebugging git config parsing:")
        git_config = Path(git_root) / ".git" / "config"
        print(f"Git config path: {git_config}")
        print(f"Git config exists: {git_config.exists()}")
        if git_config.exists():
            print("\nGit config content:")
            print(git_config.read_text())
else:
    print("✗ No git root found")
