# 0.1.0 Verification Record

[English](VERIFICATION.md) | [한국어](VERIFICATION.ko.md)

- Code and package verification date: 2026-10-10
- Runtime environment: macOS, Python 3.12

## Check results

| Check | Result |
| --- | --- |
| All tests | 18 passed in 53.51s; no failures or skipped tests |
| Ruff linting and formatting | Passed |
| basedpyright | 0 errors, 0 warnings |
| Wheel and source distribution builds | Passed |
| Wheel installed in a separate uv tool environment | CLI environment inspection returned `ready=true` |
| MCP initialization with the installed wheel | 7 management tools, `selection_required` state; Jupyter not started |
| Server and session control tests in a fresh analysis environment | 6 passed |

## Session and notebook execution

Notebooks were created in `teaching-env` and `research-env`, with code cells inserted, executed, and read through MCP. Outputs confirmed the selected environment's `sys.prefix` and the result `42`.

Session initialization checks the kernel's `sys.executable` and `sys.prefix` against the selected environment. If verification fails, the MCP backend and Jupyter session are stopped and an error is returned.

Verified behaviors:

- Preserve the virtual environment identity when the Python executable is a symbolic link, and check required package versions
- Refuse to overwrite an existing environment path
- Reject unauthenticated Jupyter access
- Reject Python replacement in an active session
- Clean up the session if backend startup fails
- Keep Jupyter running after MCP disconnect and stop it on explicit request

## Dependency compatibility

`code-sandboxes 1.10.0` did not recognize the `jupyter` backend name used by Datalayer `jupyter-mcp-server 1.1.4`. Execution was verified after pinning the dependency to `code-sandboxes==0.17.0` in environment checks and installation requirements.

## Installation from GitHub

The source at [commit 7d4f4c0](https://github.com/jlee-ax/jupyter-live-mcp/commit/7d4f4c06f98d0358177510799626a2f00b065773) was installed in a separate uv tool environment. Environment inspection with the installed CLI returned `ready=true`.

## Codex CLI verification (2026-10-15)

The source at [commit 99fb018](https://github.com/jlee-ax/jupyter-live-mcp/commit/99fb018628523ca9b21531c7498c96ad31915222) was installed and manually registered as an MCP server. In Codex CLI, the discovered environments were listed and the project's `.venv` was selected. The Jupyter server and kernel were confirmed to run in that environment, and JupyterLab was opened in a browser.

The [screen recording](docs/assets/codex-install-and-start.gif) was captured in a JupyterLab terminal. Browser authentication used a local verification helper.

## Reproduce integration tests

Run these commands from the repository root on macOS. Install the Jupyter dependencies in the development environment and set `JUPYTER_LIVE_TEST_PYTHON` to include the session lifecycle test.

```sh
uv sync --group dev --python 3.12
uv pip install --python .venv/bin/python \
  'jupyterlab>=4,<5' \
  'jupyter-collaboration>=4,<5' \
  'ipykernel>=6,<8' \
  'jupyter-mcp-server==1.1.4' \
  'code-sandboxes==0.17.0'
JUPYTER_LIVE_TEST_PYTHON="$PWD/.venv/bin/python" \
  uv run --no-sync pytest -m integration
```

## Validation scope

| Target | Status |
| --- | --- |
| CLI, MCP, and Jupyter execution on macOS with Python 3.12 | Verified |
| Manual MCP registration, environment selection, and Jupyter startup in Codex CLI | Verified on 2026-10-15 |
| Windows and Linux execution | Not verified |
| Codex plugin installation and UI for selecting an environment | Not verified |
| GitHub Actions execution | Not verified; configuration is provided as a template in `ci/github-actions.yml` |
