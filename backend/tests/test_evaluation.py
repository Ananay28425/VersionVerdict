"""Regression scenarios and integrity checks for published evaluation/witness artifacts."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('versionverdict_evaluation', ROOT / 'scripts/evaluate.py')
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)
CASES_PATH = ROOT / 'fixtures/evaluation/cases.json'
CASES = json.loads(CASES_PATH.read_text())['cases']


@pytest.fixture(scope='module')
def evaluated():
    return EVALUATOR.evaluate()


@pytest.mark.parametrize('case_id', [case['id'] for case in CASES])
def test_reviewed_scenario(case_id, evaluated):
    record = next(item for item in evaluated['cases'] if item['id'] == case_id)
    assert record['actual_labels'] == record['expected_labels'], record


def test_published_metrics_are_reproducible(evaluated):
    saved = json.loads((ROOT / 'fixtures/evaluation/report.json').read_text())
    assert len({case['id'] for case in CASES}) == len(CASES)
    assert len(CASES) >= 20
    assert saved['fixture_hash'] == hashlib.sha256(CASES_PATH.read_bytes()).hexdigest()
    assert saved['metrics'] == evaluated['metrics']
    assert saved['rule_version'] == evaluated['rule_version']
    assert saved['rules_source_hash'] == evaluated['rules_source_hash']
    assert saved['extractor_source_hash'] == evaluated['extractor_source_hash']
    assert saved['actual_distribution'] == evaluated['actual_distribution']
    assert saved['expected_distribution'] == evaluated['expected_distribution']
    assert [(case['id'], case['actual_labels']) for case in saved['cases']] == [
        (case['id'], case['actual_labels']) for case in evaluated['cases']
    ]
    assert all(metric['denominator'] > 0 for metric in saved['metrics'].values())
    assert 'not captured SerpApi' in saved['scope']


def test_published_witnesses_preserve_actual_output_and_authored_code():
    directory = ROOT / 'fixtures/witnesses'
    declared = json.loads((directory / 'cases.json').read_text())
    report = json.loads((directory / 'report.json').read_text())
    records = {case['id']: case for case in report['cases']}
    assert len(records) == len(declared)
    assert set(records) == {case['id'] for case in declared}
    assert report['summary']['total'] == len(declared)
    assert report['summary']['pass'] == sum(case['status'] == 'PASS' for case in records.values())
    for case in declared:
        record = records[case['id']]
        source = (directory / 'authored' / case['snippet']).read_text()
        assert record['code'] == source
        assert record['code_hash'] == hashlib.sha256(source.encode()).hexdigest()
        assert record['expected'] == case['expected']
        if record['status'] == 'PASS':
            assert report['environments'][case['environment']]['pins_match'] is True
            assert record['execution']['returncode'] == 0
            assert '-I' in record['execution']['command']
            assert json.loads(record['execution']['stdout']) == record['observed']
            assert all(record['observed'].get(key) == value for key, value in case['expected'].items())
        elif record['status'] == 'UNVERIFIED':
            assert record['observed'] is None
    assert 'No uploaded or retrieved code' in report['scope']
