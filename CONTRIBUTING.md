# Contributing

Thank you for your interest in contributing!

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Install the package with dev extras:

    ```bash
    pip install -e '.[dev]'
    ```

    This is required — `caloron` pulls in `typer` as a runtime dep,
    and the CLI smoke test suite imports it. Skipping this step
    silently skips `tests/test_cli_smoke.py` with a diagnostic
    message; CI does this automatically.

4. Set `GITEA_TOKEN` in your environment (any non-empty string works
   for running tests; a real token is only needed for live sprint
   runs):

    ```bash
    export GITEA_TOKEN=fake-token-for-tests-only
    ```

    The orchestrator raises at import time if this is unset — see
    `orchestrator/validation.py` for the rationale (#18).

5. Run the tests:

    ```bash
    pytest tests/
    ```

6. Make your changes
7. Commit with a clear message
8. Open a pull request

## Code Style

- **Rust:** Follow `rustfmt` defaults. Run `cargo fmt` before committing.
- **Python:** Follow PEP 8. Keep stages under 150 lines.
- **JSON:** 2-space indentation for composition graphs.

## Pull Request Process

1. Ensure all tests pass
2. Update documentation if you changed behavior
3. Add a changelog entry for user-facing changes
4. One approval required for merge

## Reporting Bugs

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Environment details (OS, Rust version, Python version)

## License

By contributing, you agree that your contributions will be licensed under the EUPL-1.2.
