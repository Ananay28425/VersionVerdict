#!/usr/bin/env python3
"""Run only reviewed, repository-authored API witnesses in pinned Python environments.

This never accepts uploaded repositories, fetched source code, or arbitrary code paths.
A matching witness proves only the recorded minimal recipe, not a retrieved solution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "witnesses"
ENVIRONMENTS = {
    "pydantic-1.10.15": ["pydantic==1.10.15", "typing_extensions==4.15.0"],
    "pydantic-2.9.2": [
        "pydantic==2.9.2",
        "pydantic_core==2.23.4",
        "annotated-types==0.7.0",
        "typing_extensions==4.15.0",
    ],
    "sqlalchemy-1.4.54": ["SQLAlchemy==1.4.54", "greenlet==3.2.4"],
    "sqlalchemy-2.0.36": [
        "SQLAlchemy==2.0.36",
        "greenlet==3.2.4",
        "typing_extensions==4.15.0",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def command_result(
    command: list[str], *, env: dict[str, str] | None = None, timeout: int = 180
) -> dict:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "command": command,
            "returncode": None,
            "stdout": "",
            "stderr": str(error),
        }


def run(output: Path, venv_root: Path, install: bool = True) -> dict:
    cases = json.loads((FIXTURES / "cases.json").read_text())
    report = {
        "schema_version": 1,
        "checked_at": utc_now(),
        "scope": "Repository-authored minimal recipes, isolated pinned packages, SQLite only. No uploaded or retrieved code was executed. Passing witnesses do not validate arbitrary web sources, production repositories, or other releases.",
        "runner_python": platform.python_version(),
        "environments": {},
        "cases": [],
    }
    if sys.version_info < (3, 12):
        raise RuntimeError("Witnesses require Python 3.12 or later.")
    for name, requirements in ENVIRONMENTS.items():
        directory = venv_root / name
        python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        setup = []
        if not python.exists() and install:
            setup.append(command_result([sys.executable, "-m", "venv", str(directory)]))
        if install and python.exists():
            setup.append(
                command_result(
                    [
                        str(python),
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "--only-binary=:all:",
                        *requirements,
                    ]
                )
            )
        probe_code = "import json,platform,importlib.metadata as m; print(json.dumps({'python':platform.python_version(),'packages':{d.metadata['Name']:d.version for d in m.distributions()}}))"
        probe = command_result([str(python), "-I", "-c", probe_code], timeout=30)
        versions = None
        if probe["returncode"] == 0:
            try:
                versions = json.loads(probe["stdout"])
            except json.JSONDecodeError:
                pass
        normalized = {
            key.lower().replace("_", "-"): value
            for key, value in (versions or {}).get("packages", {}).items()
        }
        pins_match = bool(versions) and all(
            normalized.get(req.split("==")[0].lower().replace("_", "-"))
            == req.split("==")[1]
            for req in requirements
        )
        report["environments"][name] = {
            "requirements": requirements,
            "setup": setup,
            "probe": probe,
            "observed": versions,
            "pins_match": pins_match,
        }
        for case in (item for item in cases if item["environment"] == name):
            path = FIXTURES / "authored" / case["snippet"]
            if not path.resolve().is_relative_to((FIXTURES / "authored").resolve()):
                raise ValueError(
                    "Only repository-authored fixture snippets are allowed."
                )
            source = path.read_text()
            record = {
                **case,
                "code": source,
                "code_hash": hashlib.sha256(source.encode()).hexdigest(),
                "checked_at": utc_now(),
                "observed": None,
                "status": "UNVERIFIED",
            }
            if not pins_match:
                record["reason"] = (
                    "Pinned package environment could not be prepared or verified."
                )
                report["cases"].append(record)
                continue
            environment = dict(os.environ)
            environment["SQLALCHEMY_WARN_20"] = "1"
            execution = command_result(
                [str(python), "-I", str(path)], env=environment, timeout=30
            )
            record["execution"] = execution
            if execution["returncode"] == 0:
                try:
                    observed = json.loads(execution["stdout"])
                    record["observed"] = observed
                    expected = case["expected"]
                    checks = {
                        key: observed.get(key) == value
                        for key, value in expected.items()
                    }
                    record["checks"] = checks
                    record["status"] = "PASS" if all(checks.values()) else "FAIL"
                except json.JSONDecodeError:
                    record["status"] = "FAIL"
                    record["reason"] = "Witness process did not return structured JSON."
            else:
                record["status"] = "FAIL"
                record["reason"] = "Witness process could not complete."
            report["cases"].append(record)
    report["summary"] = {
        label.lower(): sum(case["status"] == label for case in report["cases"])
        for label in ("PASS", "FAIL", "UNVERIFIED")
    }
    report["summary"]["total"] = len(report["cases"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FIXTURES / "report.json")
    parser.add_argument(
        "--venv-root", type=Path, default=Path("/tmp/versionverdict-witness-venvs")
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Only use already prepared pinned environments.",
    )
    args = parser.parse_args()
    report = run(args.output, args.venv_root, install=not args.no_install)
    print(json.dumps({"output": str(args.output), **report["summary"]}))
    return 0 if report["summary"]["pass"] == report["summary"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
