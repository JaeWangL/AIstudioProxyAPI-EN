# Contributing to AI Studio Proxy API EN

Thank you for your interest in contributing. Bug reports, feature proposals, and pull requests are welcome.

## Getting Started

### Clone the repository

```bash
git clone https://github.com/MasuRii/AIstudioProxyAPI-EN.git
cd AIstudioProxyAPI-EN
```

### Install dependencies

```bash
# Install Poetry (if needed)
curl -sSL https://install.python-poetry.org | python3 -

# Install project dependencies
poetry install --with dev
```

## Development Workflow

1. Create a branch:
   ```bash
   git checkout -b feature/your-change
   ```
2. Implement your changes.
3. Run local checks before committing:
   ```bash
   poetry run ruff check .
   poetry run pyright
   poetry run pytest
   ```
4. Commit using [Conventional Commits](https://www.conventionalcommits.org/).
5. Open a Pull Request.

## CI Notes

GitHub Actions runs lint, type-check, and test workflows on pull requests and pushes.

## Reporting Issues

Please include:

- Steps to reproduce
- Expected behavior vs actual behavior
- Python version and OS
- Relevant logs (for example from `logs/` or `errors_py/`)

## Questions

- Check [README.md](README.md)
- Open a GitHub Issue

## License

Contributions are licensed under [AGPLv3](LICENSE).
