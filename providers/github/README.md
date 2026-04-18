# GitHub Provider

This provider adds read-only GitHub.com inspection skills for AtlasClaw.

Phase 1 scope:

- user-owned token only
- github.com only
- repository list
- PR checks
- workflow run list
- workflow run view
- failed workflow logs
- selected read-only REST API queries

The provider does not use `gh`. All execution goes through GitHub REST API.
