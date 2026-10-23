# ten_ai_base

## Development setup

Install `uv`, `task`, and `tman`, then prepare the platform-specific TEN runtime
and Python environment:

```sh
task prepare
```

The command installs TEN packages into `.ten` and creates or updates the local
`.venv` from `pyproject.toml`. Run checks through the same managed environment
with `task lint` and `task test`.

