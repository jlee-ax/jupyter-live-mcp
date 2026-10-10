---
name: jupyter
description: Start Jupyter Live when the user requests /jupyter live or a live Jupyter notebook session, choosing their Python environment before startup and operating notebooks through MCP.
---

# Jupyter Live

Use the `jupyterLive` MCP controller to prepare a live notebook session. Its private tool environment is separate from the Python environment used for Jupyter and notebook execution.

## Select before startup

1. Establish the requested project directory and call `discover_environments` with `project`.
2. Show available Python paths and names, then ask the user which Python to use. Always obtain an explicit choice before `start_session`; an already stated Python choice remains valid and does not need another question. Allow a custom Python executable path.
3. Call `inspect_environment` with `python_path`. If dependencies are missing or incompatible, explain the result. Create a venv with `create_environment` only when the user requests it, using `base_python` and a new `target_path`. Install packages with `install_dependencies` only when explicitly authorized; installation can change packages in the selected environment.
4. Call `start_session` with `project` and the chosen `python_path`. Refresh the tool list after success. Call `session_info` for the resulting environment, kernel and browser details.

Do not select a fixed environment name or silently fall back to another interpreter. The controller verifies that the selected Python and prefix match the running kernel. If selection or preparation fails, report the concrete error and resolve that environment's problem before continuing.

## Browser integration

`session_info` returns a nonsecret `url` and a local `token_file` path. Opening JupyterLab is optional and depends on the host's available browser integration. Use the host's credential-aware local browser workflow when available. Never display, log or save the token contents or an authenticated URL in conversation, notebook source, evidence or versioned files. If secure browser handoff is unavailable, report that limitation while keeping MCP available.

## Notebook operations

- Discover notebooks with `list_files` and `list_notebooks`, and inspect available kernels with `list_kernels` when needed.
- Activate the chosen notebook with `use_notebook` before cell operations. Read the target cell or surrounding structure before every mutation.
- Announce whether the work edits an existing cell or creates a new independent cell. Prefer surgical edits and preserve neighboring cells, metadata and unrelated outputs.
- Use code cells by default. Create Markdown cells only when the user asks. Include concise comments for analytical assumptions and non-obvious intent.
- Use MCP for cell reads, edits, execution and output inspection. Do not rewrite notebook JSON with file helpers.
- Before executing code with upstream dependencies, inspect whether required variables already exist. Run only the affected cell and the smallest necessary dependency chain, respecting the user's execution instructions.
- Read affected cells and outputs back after mutation or execution. Preserve the active kernel for the user's next step.

## Session lifecycle

Do not restart, replace or stop a kernel or Jupyter session unless explicitly requested, or a confirmed runtime failure requires repair. Explain the repair before disrupting shared state. Closing the controller connection preserves the Jupyter process and kernel; this is expected.

Use `stop_session` for an explicit request to stop the connected session. To find a session left after disconnection, use `jupyter-live-mcp sessions`. Stop only the requested session with `jupyter-live-mcp stop --state-dir` and its exact listed `state_dir`.
