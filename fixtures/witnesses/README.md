# Reviewed API witnesses

`report.json` records actual isolated execution of **12 repository-authored recipes** on Python 3.12.14 with Pydantic 1.10.15/2.9.2 and SQLAlchemy 1.4.54/2.0.36. The package probe, full commands, stdout/stderr, expected and observed outcomes, timestamps, and source hashes are included.

```bash
python3 scripts/verify_versions.py --output fixtures/witnesses/report.json
# Reuse the prepared package environments without another install:
python3 scripts/verify_versions.py --no-install
```

The runner creates virtual environments below `/tmp/versionverdict-witness-venvs` by default. Use `--venv-root <directory>` on another platform. All application and transitive package requirements are pinned. `--only-binary=:all:` avoids source-package builds; platforms lacking a compatible wheel will be reported unverified rather than guessed.

Only `authored/` snippets listed in the reviewed `cases.json` are executed. There is no input for arbitrary code, uploaded manifests, or fetched web recipes. SQLite is local and in memory. These recipes prove specific observed API behavior, not the correctness of entire web pages, arbitrary projects, other package releases, or production deployment.

The recorded SQLAlchemy connection recipe uses `text()` and a managed `engine.begin()` transaction. The 1.4 connection witness explicitly uses future mode; it does not validate every possible 1.4 engine setting.

These witnesses do not call SerpApi or consume search credits.
