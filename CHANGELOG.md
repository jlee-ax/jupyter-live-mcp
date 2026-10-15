# Changelog

[English](CHANGELOG.md) | [한국어](CHANGELOG.ko.md)

## 0.1.0 — 2026-10-10

- Discover Python environments and select a custom interpreter before starting Jupyter.
- Inspect environments, create virtual environments, and install dependencies in the selected environment.
- Start JupyterLab and the MCP backend with the selected Python interpreter and verify the kernel's environment.
- Operate notebooks through Datalayer `jupyter-mcp-server==1.1.4` with the compatible `code-sandboxes==0.17.0`.
- Keep Jupyter sessions running after MCP disconnect and stop individual sessions on explicit request.
- Include Codex plugin configuration, a Jupyter workflow skill, and a GitHub Actions template.
