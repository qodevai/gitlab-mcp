# Changelog

All notable changes to the GitLab MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
