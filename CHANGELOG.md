# Changelog

## 0.1.0 — Unreleased

- Pinned selected-environment `code-sandboxes` to `0.17.0` for compatibility with Datalayer `1.1.4`; environment inspection rejects incompatible versions before startup.

- Added an MCP controller that offers Python environment selection before Jupyter startup.
- Added discovery of project virtualenvs, activated environments and Conda environments, plus explicit interpreter selection.
- Added explicit environment creation and dependency installation, selected-kernel verification and preserved-session management.
- Added Codex compatibility plugin metadata, a Jupyter workflow skill and a local-source marketplace declaration.
- Added separate quality/build and Linux integration CI jobs. GitHub publication and CI execution remain pending.
