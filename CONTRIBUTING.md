# Contributing

Thank you for helping improve Forge Orchestrator. Contributions should
preserve the service's local-inference architecture, caller-owned external
tool boundary, and documented API contracts.

## Code of conduct

By participating, you agree to abide by the
[Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
Treat contributors respectfully and professionally.

## Report bugs

Search existing issues first. Include:

- Steps to reproduce, expected behavior, and actual behavior.
- Python version, operating system, and relevant dependency versions.
- A minimal request or test case with secrets and personal data removed.

## Suggest features

Open an issue describing the user need, intended behavior, and trade-offs.
Discuss significant architecture or API changes before implementing them.

## Local development

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m pip install pytest
python -m pytest
```

For production configuration, set `FORGE_ENVIRONMENT=production` and provide
`FORGE_CHECKPOINT_ROOT` on persistent storage. The service will not start in
production without the checkpoint root.

## Pull requests

- Create a focused branch, such as `feat/local-embeddings` or
  `fix/checkpoint-resume`.
- Use clear commit messages, preferably with prefixes such as `feat:`,
  `fix:`, `docs:`, or `test:`.
- Before requesting review, confirm:
  - [ ] Tests cover behavior changes.
  - [ ] Documentation and public contracts are updated when applicable.
  - [ ] `python -m pytest` passes, and the result is reported.
  - [ ] No secrets, model credentials, or user data are included.

Maintainers review and merge contributions. Review may request follow-up
changes; no review-time guarantee is implied.

## Security reports

Do not report suspected vulnerabilities in public issues. Use
[GitHub's private vulnerability reporting](https://github.com/TediForge/Forge/security/advisories/new)
for this repository.

## Getting help

For usage and development questions, open a GitHub issue with a minimal,
reproducible example. Do not post credentials, private data, or sensitive logs.
