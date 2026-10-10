#!/usr/bin/env python3
"""Evaluate curated source scenarios; never invoke SerpApi or execute source recipes."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.applicability import RULESET_VERSION, classify_all
from app.evidence import extract
from app.models import SearchHit
from app.profiler import parse_profile

DEFAULT_CASES = ROOT / 'fixtures/evaluation/cases.json'
DEFAULT_REPORT = ROOT / 'fixtures/evaluation/report.json'
DEFINITIVE = {'COMPATIBLE', 'WRONG_VERSION', 'STALE'}


def evaluate(cases_path: Path = DEFAULT_CASES) -> dict:
    raw = cases_path.read_bytes()
    fixture = json.loads(raw)
    facts = json.loads((ROOT / 'fixtures/evidence/facts.json').read_text())
    records = []
    matched_labels = definitive = correct_definitive = predicted_uncertain = (
        total_labels
    ) = 0
    for case in fixture['cases']:
        profile = parse_profile(
            case['id'],
            [('requirements.txt', case['manifest'].encode())],
            pydantic_api_mode=case['pydantic_api_mode'],
            sqlalchemy_future=case['sqlalchemy_future'],
        )
        hit = SearchHit(
            id=case['id'],
            title=case['title'],
            url=case['source_url'],
            snippet='Discovery metadata is not definitive source evidence.',
            position=1,
        )
        body = case['source']
        if body is not None and case['source_format'] == 'html':
            body = extract(body, provenance='authored_evaluation_fixture')
        cards = classify_all(
            hit,
            body,
            profile,
            case['library'],
            facts if case['facts'] == 'complete' else {},
        )
        actual = [card.label.value for card in cards]
        expected = case['expected_labels']
        # Mixed examples are paired by document order. Missing/extra cards count as errors.
        correct = actual == expected
        count = max(len(actual), len(expected))
        total_labels += count
        for index, label in enumerate(actual):
            expected_label = expected[index] if index < len(expected) else None
            matched_labels += label == expected_label
            predicted_uncertain += label == 'UNCERTAIN'
            if label in DEFINITIVE:
                definitive += 1
                correct_definitive += label == expected_label
        records.append(
            {
                'id': case['id'],
                'expected_labels': expected,
                'actual_labels': actual,
                'status': 'PASS' if correct else 'FAIL',
                'rationale': case['rationale'],
                'explanations': [card.explanation for card in cards],
                'recipe_count': len(cards),
                'evidence_counts': [len(card.evidence) for card in cards],
            }
        )
    passed = sum(record['status'] == 'PASS' for record in records)
    return {
        'schema_version': 1,
        'rule_version': RULESET_VERSION,
        'rules_source_hash': hashlib.sha256(
            (ROOT / 'backend/app/applicability.py').read_bytes()
        ).hexdigest(),
        'extractor_source_hash': hashlib.sha256(
            (ROOT / 'backend/app/evidence.py').read_bytes()
        ).hexdigest(),
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'scope': fixture['scope'],
        'limitations': [
            'Curated fixtures are not a random sample of real-world results.',
            'This suite does not measure live API success, latency, general search relevance, or production accuracy.',
            'Published source URLs identify documentation families; evaluation HTML is explicitly authored input, not a capture from those URLs.',
        ],
        'fixture_hash': hashlib.sha256(raw).hexdigest(),
        'case_count': len(records),
        'metrics': {
            'exact_case_match': {
                'numerator': passed,
                'denominator': len(records),
                'value': passed / len(records) if records else None,
            },
            'label_accuracy': {
                'numerator': matched_labels,
                'denominator': total_labels,
                'value': matched_labels / total_labels if total_labels else None,
            },
            'definitive_label_precision': {
                'numerator': correct_definitive,
                'denominator': definitive,
                'value': correct_definitive / definitive if definitive else None,
            },
            'definitive_coverage': {
                'numerator': definitive,
                'denominator': total_labels,
                'value': definitive / total_labels if total_labels else None,
            },
            'uncertainty_rate': {
                'numerator': predicted_uncertain,
                'denominator': total_labels,
                'value': predicted_uncertain / total_labels if total_labels else None,
            },
        },
        'expected_distribution': dict(
            Counter(
                label for case in fixture['cases'] for label in case['expected_labels']
            )
        ),
        'actual_distribution': dict(
            Counter(label for record in records for label in record['actual_labels'])
        ),
        'cases': records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    parser.add_argument('--output', type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = evaluate(args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(
        json.dumps(
            {
                'output': str(args.output),
                'case_count': report['case_count'],
                'metrics': report['metrics'],
            }
        )
    )
    return 0 if all(case['status'] == 'PASS' for case in report['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
