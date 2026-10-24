import json

import pytest

from app.lockfiles import LockedDependency, LockfileError, parse_lockfile

POETRY = """
[[package]]
name = "Pydantic"
version = "2.9.2"

[[package]]
name = "typing_extensions"
version = "4.12.2"
"""

CARGO = """
[[package]]
name = "serde"
version = "1.0.210"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "serde"
version = "0.9.15"
"""


def test_poetry_lock_normalizes_names():
    deps = parse_lockfile("poetry.lock", POETRY)
    assert deps == [
        LockedDependency("pydantic", "2.9.2", "python"),
        LockedDependency("typing-extensions", "4.12.2", "python"),
    ]


def test_cargo_lock_keeps_multiple_versions():
    deps = parse_lockfile("Cargo.lock", CARGO)
    assert [d.version for d in deps] == ["0.9.15", "1.0.210"]


def test_package_lock_v3_handles_scoped_nested_and_links():
    lock = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "app", "version": "1.0.0"},
            "node_modules/react": {"version": "18.3.1"},
            "node_modules/@types/node": {"version": "22.5.0"},
            "node_modules/a/node_modules/react": {"version": "17.0.2"},
            "node_modules/ws-link": {"resolved": "packages/ws", "link": True},
            "packages/ws": {"version": "0.1.0"},
        },
    }
    deps = parse_lockfile("package-lock.json", json.dumps(lock))
    assert {(d.name, d.version) for d in deps} == {
        ("react", "18.3.1"),
        ("react", "17.0.2"),
        ("@types/node", "22.5.0"),
    }


def test_package_lock_v1_recurses_and_skips_git_urls():
    lock = {
        "lockfileVersion": 1,
        "dependencies": {
            "lodash": {"version": "4.17.21"},
            "foo": {
                "version": "1.2.3",
                "dependencies": {"lodash": {"version": "3.10.1"}},
            },
            "bar": {"version": "github:user/bar#abc123"},
        },
    }
    deps = parse_lockfile("package-lock.json", json.dumps(lock))
    assert {(d.name, d.version) for d in deps} == {
        ("lodash", "4.17.21"),
        ("lodash", "3.10.1"),
        ("foo", "1.2.3"),
    }


def test_path_prefix_and_case_are_ignored():
    assert parse_lockfile("sub/dir/POETRY.LOCK", POETRY)


@pytest.mark.parametrize(
    "name,content",
    [
        ("poetry.lock", "not [valid toml"),
        ("package-lock.json", "{broken"),
        ("package-lock.json", "[]"),
        ("package-lock.json", "{}"),
        ("yarn.lock", ""),
    ],
)
def test_bad_input_raises_lockfile_error(name, content):
    with pytest.raises(LockfileError):
        parse_lockfile(name, content)


def test_oversized_lockfile_rejected():
    with pytest.raises(LockfileError):
        parse_lockfile("poetry.lock", b"#" * (1024 * 1024 + 1))