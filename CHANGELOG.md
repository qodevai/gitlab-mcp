# Changelog

All notable changes to the GitLab MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-20

### Fixed
- **Import side effects** - Removed eager server imports from `__init__.py` that required `GITLAB_TOKEN` at import time, even when importing from submodules
- **Lazy client initialization** - Server now uses `GitLabClient(lazy=True)` so the MCP server can start and show help without requiring `GITLAB_TOKEN` at import time

### Changed
- **CI publish gating** - Publish workflow now requires lint, typecheck, and test to pass before publishing to PyPI
- **Improved documentation and packaging** - Rewrote README with full tools/resources reference, added `py.typed` marker for PEP 561 type stub support, updated LICENSE copyright

## [0.1.0] - 2026-02-20

### Changed
- **Renamed package** from `gitlab-mcp` to `qodev-gitlab-mcp` for public PyPI
- **Renamed dependency** from `gitlab-client` to `qodev-gitlab-api`
- **Renamed import** from `gitlab_mcp` to `qodev_gitlab_mcp`
- **Renamed console script** from `gitlab-mcp` to `qodev-gitlab-mcp`
- **Moved to GitHub** at `qodevai/gitlab-mcp`
- **Publishing** via GitHub Actions with Trusted Publishers (OIDC) to public PyPI
- **Version reset** to 0.1.0 for initial public release

- **Issue Management Support** - Create, view, update, and comment on GitLab issues
  - `get_issues()` method in GitLabClient - List issues with filters (state, labels, assignees, milestone)
  - `get_issue()` method in GitLabClient - Get specific issue by IID
  - `create_issue()` method in GitLabClient - Create new issues with labels and assignees
  - `update_issue()` method in GitLabClient - Update issue title, description, labels, assignees, state
  - `close_issue()` method in GitLabClient - Close issues (convenience wrapper)
  - `get_issue_notes()` method in GitLabClient - Get comments/notes on issues
  - `create_issue_note()` method in GitLabClient - Add comments to issues
  - `gitlab://projects/{project_id}/issues/` MCP resource - List open issues
  - `gitlab://projects/{project_id}/issues/{issue_iid}` MCP resource - Get specific issue
  - `gitlab://projects/{project_id}/issues/{issue_iid}/notes` MCP resource - Get issue comments
  - `create_issue()` MCP tool - Create issues with support for `project_id="current"`
  - `update_issue()` MCP tool - Update issues with support for `project_id="current"`
  - `close_issue()` MCP tool - Close issues with support for `project_id="current"`
  - `comment_on_issue()` MCP tool - Comment on issues with support for `project_id="current"`
  - Supports `project_id="current"` for current repository
  - Granular resources for minimal token usage
  - Full Markdown support in issue descriptions and comments
  - Comprehensive error handling with helpful suggestions

- **Optional Comment When Closing MRs** - Add comment parameter to `close_merge_request` tool
  - Optional `comment` parameter allows leaving a comment when closing an MR in a single operation
  - Similar to GitHub CLI: `gh pr close --comment "reason"`
  - Common use case: "Superseded by !123", "No longer needed", etc.
  - Handles partial failures gracefully: if close succeeds but comment fails, returns success with warning
  - Fully backward compatible: existing calls without comment parameter work identically
  - Supports Markdown formatting in comments

### Fixed
- **Non-resolvable discussions incorrectly counted as unresolved** - Fixed `filter_actionable_discussions` to only count discussions with `resolvable: true` as unresolved. Individual note comments (like summary comments) have `resolvable: false` and can never be resolved, so they should not block MR merging or appear in unresolved counts.
- **MR Squash Settings Not Applied** - Workaround for GitLab API bug that ignores project squash settings
  - GitLab API doesn't respect project's "Squash commits" setting when creating MRs via API
  - See upstream bug: https://gitlab.com/gitlab-org/gitlab/-/issues/385301
  - `create_merge_request` now fetches project settings and applies squash default automatically
  - Supports all project squash options: "never", "default_off" (Allow), "default_on" (Encourage), "always" (Require)
  - TODO: Remove workaround when GitLab fixes upstream bug

- **"current" Resolution Broken** - Fix missing subprocess import that broke all "current" placeholder usage
  - Commit a27a226 refactored `find_git_root()` and `parse_gitlab_remote()` to use subprocess.run() but forgot to import subprocess
  - This caused `NameError: name 'subprocess' is not defined` for all tools using `project_id="current"` or `mr_iid="current"`
  - Added subprocess to module-level imports and removed redundant local import from `get_current_branch()`

- **Artifact Query Parameters Now Work** - Fixed `?lines=N`, `?offset=M`, and `?lines=all` query params for artifact resources
  - Previously, query parameters were silently ignored (MCP includes them in path segment)
  - Now parses query params from artifact_path to enable line range selection
  - Added truncation hint when output is limited: suggests `?lines=all` or `download_artifact` tool
  - Example: `gitlab://projects/current/jobs/123/artifacts/logs.txt?lines=50` now returns last 50 lines

- **Document Missing MCP Resources** - Added 3 undocumented resources to server instructions
  - `gitlab://projects/{project_id}/pipelines/{pipeline_id}` - Get specific pipeline details
  - `gitlab://projects/{project_id}/pipelines/{pipeline_id}/jobs` - Get jobs for a specific pipeline
  - `gitlab://projects/{project_id}/jobs/{job_id}/log` - Full job output/trace
  - These resources existed in code but were not documented, causing Claude to fall back to curl commands

### Added
- **Download Artifact Tool** - Download artifacts to local filesystem for shell analysis
  - `download_artifact(project_id, job_id, artifact_path, destination=None)` MCP tool
  - Downloads complete file (no truncation) unlike the resource which defaults to last 10 lines
  - Default destination: temp file with auto-generated name
  - Returns file path for use with shell tools (grep, wc, head, tail, awk, etc.)
  - Supports `project_id="current"` for current repository
  - Use case: Large log files that need regex search or line counting

- **CI/CD Variable Read Access** - Allow MCP clients to list and inspect CI/CD variables
  - `list_project_variables()` method in GitLabClient - List all variables (metadata only)
  - `_sanitize_variable()` helper method - Strips sensitive values from API responses
  - `gitlab://projects/{project_id}/variables/` MCP resource - List all CI/CD variables
  - `gitlab://projects/{project_id}/variables/{key}` MCP resource - Get specific variable metadata
  - Supports `project_id="current"` for current repository
  - **Security**: Values are NEVER exposed - only metadata (key, type, protected, masked, environment_scope, description)
  - Use cases: Check if variable exists, verify configuration, audit variable setup
  - To update values, use `set_project_ci_variable()` tool

- **Merge Request Status Resource** - Lightweight merge readiness check for token optimization
  - `gitlab://projects/{project_id}/merge-requests/{mr_iid}/status` MCP resource
  - Single call replaces 3-4 separate fetches (pipeline + discussions + approvals)
  - Returns `ready_to_merge` boolean and `blockers` array for quick decision making
  - Includes failed job IDs for easy log access
  - Includes unresolved discussion IDs for quick navigation
  - Supports `project_id="current"` and `mr_iid="current"`
  - **Token savings**: 85-90% reduction (500-800 tokens vs 5,500 tokens for separate calls)
  - Answers common questions: "Is this MR ready to merge?", "What's blocking my MR?"

- **Discussion Thread Interactions** - Reply to and manage discussion threads on merge requests
  - `reply_to_discussion()` method in GitLabClient - Reply to existing discussion threads
  - `resolve_discussion()` method in GitLabClient - Resolve or unresolve discussion threads
  - `reply_to_discussion()` MCP tool - Reply to discussions with support for `project_id="current"` and `mr_iid="current"`
  - `resolve_discussion_thread()` MCP tool - Resolve/unresolve discussions with support for `project_id="current"` and `mr_iid="current"`
  - Full Markdown support in replies
  - Comprehensive error handling for invalid discussion IDs and permissions

- **Release Management** - Full support for creating and managing GitLab releases
  - `get_releases()` method in GitLabClient - List all releases for a project (sorted by release date, newest first)
  - `get_release()` method in GitLabClient - Get specific release by tag name
  - `create_release()` method in GitLabClient - Create new releases with tags, descriptions, milestones, and asset links
  - `update_release()` method in GitLabClient - Update existing releases (name, description, milestones, release date)
  - `delete_release()` method in GitLabClient - Delete releases (preserves associated tags)
  - `gitlab://projects/{project_id}/releases/` MCP resource - List all releases (supports `project_id="current"`)
  - `gitlab://projects/{project_id}/releases/{tag_name}` MCP resource - Get specific release by tag
  - `create_release()` MCP tool - Create releases with support for `project_id="current"`
  - Auto-detection of `ref` from current branch if not provided
  - Comprehensive error handling with helpful suggestions for common issues (tag doesn't exist, permissions, etc.)
  - Full support for release options: name, description, ref, milestones, release date, asset links

- **Create Merge Request Tool** - Create new merge requests programmatically
  - `create_merge_request()` method in GitLabClient
  - MCP tool with support for `project_id="current"`
  - Auto-detection of source branch from current git branch if not provided
  - Defaults target branch to "main"
  - Full support for MR options: description, assignees, reviewers, labels, squash, auto-remove source branch
  - Comprehensive error handling with helpful suggestions for common issues (duplicate MR, invalid branches, etc.)

### Changed
- **Optimized Pipeline Monitoring** - Reduced token consumption and improved workflow guidance
  - **Code change**: `get_pipelines()` now returns only 3 most recent pipelines by default (down from 10,000 max)
    - **Token reduction: 95-98%** (from 1,000-3,000 tokens → 50-100 tokens)
    - Most users only need the latest 1-3 pipelines for status checks
    - Added optional `per_page` and `max_pages` parameters for flexibility when more pipelines are needed
    - Maintains optimized defaults while allowing customization via method parameters
  - **Server instructions**: Added "Common Workflows" section with prescriptive guidance
    - Emphasizes `wait_for_pipeline` tool as PRIMARY METHOD for pipeline monitoring
    - Clear "DO/DON'T" examples to prevent inefficient manual polling patterns
    - Decision tree: "When to use what" for common pipeline-related queries
    - Token cost estimates for each workflow pattern
  - **Resource descriptions**: Updated with token costs and cross-references
    - Pipelines resource notes it returns last 3 pipelines (50-100 tokens)
    - Points users to `wait_for_pipeline` tool for monitoring scenarios
  - **Expected impact**: 70-95% token reduction for pipeline operations
    - Addresses 681 pipeline resource accesses (84% of all usage)
    - Guides Claude toward efficient patterns instead of manual polling loops

- **Git Worktree Support** - "current" placeholders now work in git worktrees
  - Replaced manual `.git/config` parsing with git commands
  - `find_git_root()` now uses `git rev-parse --show-toplevel` (handles worktrees automatically)
  - `parse_gitlab_remote()` now uses `git remote get-url origin` (handles worktrees automatically)
  - **Benefits**:
    - Users can work in git worktrees and use `project_id="current"` and `mr_iid="current"`
    - Simpler, more reliable implementation (delegates complexity to git)
    - Works with submodules and other git edge cases
    - Reduces code complexity (~25% less code)
  - Fully backward compatible with normal repositories

## [1.0.0] - 2025-01-21

### Added - Production Release

#### Core Features
- **MR Discussions Support** - View and track discussion threads on merge requests
  - Current branch MR discussions resource
  - Per-MR discussions endpoint
  - Unresolved discussion tracking
  - Discussion summary with counts

- **Complete MR Overview** - Single endpoint with all MR information
  - MR metadata (title, description, status, branches)
  - Discussion summary (total, resolved, unresolved)
  - Changes summary (list of modified files)
  - Commit history with details
  - Pipeline status
  - Approval status

- **MR Changes/Diff** - View code changes in merge requests
  - File-level changes
  - New, renamed, and deleted file indicators
  - Full diff support

- **Additional API Methods**
  - `get_mr_discussions()` - Fetch discussion threads
  - `get_mr_changes()` - Get diff/changes
  - `get_mr_commits()` - Get commit history
  - `get_mr_approvals()` - Get approval status

#### Production Hardening
- **Comprehensive Logging** - Structured logging throughout the application
  - Log levels: DEBUG, INFO, WARNING, ERROR
  - Contextual error messages
  - API call logging with timing

- **Error Handling** - Robust error handling and recovery
  - Specific exception types (HTTPStatusError, RequestError)
  - Helpful error messages for users
  - Graceful degradation for optional features
  - Connection validation on startup

- **Security Improvements**
  - Token validation on startup
  - URL validation
  - Removed hardcoded credentials from version control
  - Environment variable configuration

- **Safety Limits** - Protection against API abuse
  - Pagination max_pages limit (default: 100)
  - Per-page result limits (respects GitLab max of 100)
  - Timeout protection
  - Warning logs when hitting limits

#### Documentation
- Comprehensive README.md with:
  - Installation instructions
  - Configuration guide
  - Usage examples
  - Troubleshooting section
  - Security best practices
  - API reference
- Environment template (.env.example)
- This CHANGELOG.md
- MIT License

#### Repository Setup
- Git repository initialization
- .gitignore for sensitive files
- Properly pinned dependencies (~= instead of >=)
- Package metadata (version, authors, keywords)

### Changed
- **Version** - Bumped to 1.0.0 (production-ready)
- **Dependencies** - Pinned with compatible release ranges
  - httpx~=0.27.0 (was >=0.27.0)
  - fastmcp~=1.0.0 (was >=1.0.0)
  - Added python-dotenv~=1.0.0
- **Error Responses** - Now return structured error objects with context
- **Pagination** - Added safety limits and better logging

### Fixed
- Silent exception handling - All errors now logged with context
- Infinite pagination loops - Added max_pages limit
- Token security - Removed from version control
- Missing validation - Added startup checks for token and URL

### Removed
- Obsolete test files (gitlab_mcp_fixed.py, debug_context.py)
- Broad exception catching without logging
- Hardcoded configuration values

## [0.1.0] - 2024-10-21

### Added - Initial Development Version
- Basic GitLab API integration
- Current project detection
- Merge request resources
- Pipeline resources
- Project information resources
- MCP Inspector support
- Basic error handling

### Known Issues (Fixed in 1.0.0)
- No logging infrastructure
- Silent exception handling
- No input validation
- Hardcoded test credentials
- No documentation

---

## Release Guidelines

### Version Number Format
- **Major (X.0.0)** - Breaking API changes, major new features
- **Minor (1.X.0)** - New features, backward compatible
- **Patch (1.0.X)** - Bug fixes, minor improvements

### Change Categories
- **Added** - New features
- **Changed** - Changes in existing functionality
- **Deprecated** - Soon-to-be removed features
- **Removed** - Removed features
- **Fixed** - Bug fixes
- **Security** - Security improvements
