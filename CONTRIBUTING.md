# Contributing to llm-cost-router

Thanks for contributing! This project is an LLM gateway with semantic caching
and cost/latency metrics, so routing and caching behavior affect both spend
and correctness.

## Getting started

```sh
make install     # install dev + runtime dependencies
make dev         # run the router locally (see Makefile targets)
```

## Before you open a PR

- Run the tests: `make test` (or `pytest`).
- Run `pre-commit run --all-files` (ruff + formatting hooks).
- If you change cache keys, similarity thresholds, or routing logic, add tests
  that pin the intended behavior (including edge cases around duplicate
  prompts).
- Never commit real API keys or provider credentials — use environment
  variables or a secret manager.

## Commits

Use conventional-commits style, e.g. `feat(cache): ...`,
`fix(routing): ...`, `docs(metrics): ...`.

## Reaching out

Open an issue to discuss bugs, feature ideas, or large changes before
submitting a PR.
