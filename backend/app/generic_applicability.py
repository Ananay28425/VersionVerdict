"""Narrow, inspectable version assertions for arbitrary technology targets.

This module compares an explicit named version condition, not the correctness
of an arbitrary program. Unsupported prose and unevaluated conditions abstain.
"""

import re
from dataclasses import dataclass
from urllib.parse import unquote

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .evidence import cite, document, public_allowed
from .models import Card, Label, Profile, SearchHit
from .profiler import version_for

NUMERIC = r'\d+(?:\.\d+){0,2}'
GENERIC_RULESET_VERSION = '2026-10-10-explicit-conditions-v1'
EXPRESSION = rf'(?:>=|<=|==|>|<|!=)\s*{NUMERIC}(?:\s*(?:,|and)\s*(?:>=|<=|==|>|<|!=)\s*{NUMERIC})*'
QUALIFIERS = re.compile(
    r'\b(?:if|unless|except|only|depending|may|might|perhaps|experimental|'
    r'no|not|never|false|myth|incorrect|unsupported|unavailable|hypothetical|'
    r'windows|linux|macos|darwin|board|hardware|compiler|architecture|abi|'
    r'build|feature|plugin|backend|prerelease)\b',
    re.I,
)
CONTEXT_CONDITIONS = re.compile(r'\b(?:requires|must|depends on|on|for)\b', re.I)
STOPWORDS = set(
    'how do i a an the in on for to from with of is are it this that use using '
    'error fix configure install setup import execute run enable disable API '
    'version versions migration documentation compatible compatibility'.casefold().split()
)


@dataclass(frozen=True)
class Assertion:
    kind: str
    constraint: str
    quote: str
    section: str
    qualified: bool


def _query_terms(query: str, target: str) -> set[str]:
    target_terms = set(re.findall(r'[\w-]+', target.casefold()))
    return {
        token
        for token in re.findall(r'[\w-]+', query.casefold())
        if len(token) >= 3
        and token not in STOPWORDS
        and token not in target_terms
        and not token.isdigit()
    }


def _assertions(doc: dict, target: str, query: str) -> list[Assertion]:
    # Require both a named target and a query-specific subject in one local
    # paragraph. A page title, code coincidence, or version URL never suffices.
    name = re.escape(target.strip())
    target_pattern = rf'(?<![\w-]){name}(?![\w-])'
    patterns = [
        (
            'required',
            re.compile(
                rf'(?P<subject>.{{1,160}}?)\s+(?:requires|is supported in|is available in)\s+{target_pattern}\s+(?:versions?\s+)?(?P<version>{EXPRESSION})(?P<tail>.*)',
                re.I,
            ),
        ),
        (
            'introduced',
            re.compile(
                rf'(?P<subject>.{{1,160}}?)\s+(?:was |is )?introduced in\s+{target_pattern}\s+(?:versions?\s+)?(?P<version>{NUMERIC})(?P<tail>.*)',
                re.I,
            ),
        ),
        (
            'removed',
            re.compile(
                rf'(?P<subject>.{{1,160}}?)\s+(?:was |is )?removed in\s+{target_pattern}\s+(?:versions?\s+)?(?P<version>{NUMERIC})(?P<tail>.*)',
                re.I,
            ),
        ),
        (
            'deprecated',
            re.compile(
                rf'(?P<subject>.{{1,160}}?)\s+(?:was |is )?deprecated (?:in|since)\s+{target_pattern}\s+(?:versions?\s+)?(?P<version>{NUMERIC})(?P<tail>.*)',
                re.I,
            ),
        ),
        (
            'introduced',
            re.compile(
                rf'(?P<subject>.{{1,160}}?)\s+is available in\s+{target_pattern}\s+(?:versions?\s+)?(?P<version>{NUMERIC})\s+and later(?P<tail>.*)',
                re.I,
            ),
        ),
        (
            'introduced',
            re.compile(
                rf'(?P<subject>.{{1,160}}?)\s+requires\s+{target_pattern}\s+(?:versions?\s+)?(?P<version>{NUMERIC})\s+(?:or|and)\s+(?:later|newer|higher)(?P<tail>.*)',
                re.I,
            ),
        ),
    ]
    terms = _query_terms(query, target)
    if not terms:
        return []
    assertions = []
    for passage in doc.get('passages', [])[:300]:
        if not isinstance(passage, dict) or not isinstance(passage.get('text'), str):
            continue
        text = passage['text']
        # Sentence boundaries restrict contradictory or conditional clauses;
        # numeric decimal points are retained as part of the version.
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        for sentence in sentences:
            for kind, pattern in patterns:
                match = pattern.fullmatch(sentence.rstrip().rstrip('.'))
                if not match:
                    continue
                subject = set(re.findall(r'[\w-]+', match.group('subject').casefold()))
                if not terms.intersection(subject):
                    continue
                version = match.group('version')
                tail = match.group('tail').strip()
                # Unrecognized suffixes are not silently dropped. '2.0rc1',
                # OR expressions, extra dependencies and platform conditions
                # must remain unresolved.
                scope = passage.get('scope_id')
                scopes = set(passage.get('ancestor_scope_ids') or [scope])
                scopes.add(0)
                neighbors = ' '.join(
                    str(item.get('text', ''))
                    for item in doc.get('passages', [])
                    if isinstance(item, dict)
                    and item.get('scope_id') in scopes
                    and item is not passage
                )
                headings = str(
                    passage.get('heading_context') or passage.get('heading') or ''
                )
                remainder = text.replace(sentence, '')
                qualified = bool(
                    QUALIFIERS.search(
                        sentence + ' ' + neighbors + ' ' + headings + ' ' + remainder
                    )
                    or CONTEXT_CONDITIONS.search(
                        neighbors + ' ' + headings + ' ' + remainder
                    )
                    or tail.strip(' .;:')
                )
                if kind == 'required':
                    constraint = re.sub(r'\s+and\s+', ',', version, flags=re.I).replace(
                        ' ', ''
                    )
                else:
                    constraint = '>=' + version
                try:
                    SpecifierSet(constraint)
                except InvalidSpecifier:
                    continue
                assertions.append(
                    Assertion(
                        kind,
                        constraint,
                        sentence,
                        str(passage.get('heading') or 'Document'),
                        qualified,
                    )
                )
    return assertions


def classify_generic(
    hit: SearchHit, body: str | None, profile: Profile, target: str, query: str
) -> Card:
    card = Card(
        hit=hit,
        id=hit.id,
        label=Label.UNCERTAIN,
        explanation='No explicit query-specific version condition was verified in the source.',
        preconditions=[
            'A declared exact target version and an explicit named source version condition',
            'Version condition only; runtime, hardware, OS, ABI and full solution correctness are not verified',
        ],
    )
    if not body or not public_allowed(hit.url):
        card.explanation = 'Source content could not be fetched safely; snippets cannot establish applicability.'
        return card
    doc = document(body)
    if not doc:
        return card
    assertions = _assertions(doc, target, query)
    if not assertions:
        terms = _query_terms(query, target)
        for passage in doc.get('passages', [])[:300]:
            if not isinstance(passage, dict) or not isinstance(
                passage.get('text'), str
            ):
                continue
            text = passage['text']
            words = set(re.findall(r'[\w-]+', text.casefold()))
            if len(text) <= 800 and terms.intersection(words):
                evidence = cite(
                    doc.get('source_url') or hit.url,
                    text,
                    body,
                    'fetched source excerpt; applicability unresolved',
                    section=str(passage.get('heading') or 'Document'),
                )
                if evidence:
                    card.evidence.append(evidence)
                if len(card.evidence) == 3:
                    break
        return card
    # Retain decisive source passages even when the correct result is abstention.
    for assertion in assertions[:6]:
        evidence = cite(
            doc.get('source_url') or hit.url,
            assertion.quote,
            body,
            'fetched explicit version condition',
            section=assertion.section,
        )
        if evidence:
            card.evidence.append(evidence)
    exact = version_for(profile, target)
    if exact is None:
        card.explanation = 'The target version is a range, missing or conflicting; the explicit source condition remains unresolved.'
        return card
    try:
        version = Version(exact)
    except InvalidVersion:
        card.explanation = 'The declared version uses an unsupported ordering scheme; source conditions were retained for inspection.'
        return card
    if (
        version.is_prerelease
        or version.is_devrelease
        or version.local
        or version.is_postrelease
    ):
        card.explanation = 'Prerelease, development, custom and postrelease ordering is not inferred from generic source conditions.'
        return card
    if any(assertion.qualified for assertion in assertions):
        card.explanation = 'Source conditions include an unevaluated qualifier, dependency or ambiguous version suffix; inspect the passage.'
        return card
    if not card.evidence or len(assertions) > 6:
        card.explanation = 'The source contains too many assertions or missing verifiable quotations; applicability is unresolved.'
        return card
    if doc.get('extraction_complete') is not True:
        card.explanation = 'The bounded source extraction omitted context; version applicability cannot be established safely.'
        return card
    outcomes = []
    for assertion in assertions:
        contains = SpecifierSet(assertion.constraint).contains(
            version, prereleases=False
        )
        if assertion.kind == 'removed':
            outcomes.append(Label.WRONG_VERSION if contains else Label.UNCERTAIN)
        elif assertion.kind == 'deprecated':
            outcomes.append(Label.STALE if contains else Label.UNCERTAIN)
        else:
            outcomes.append(Label.COMPATIBLE if contains else Label.WRONG_VERSION)
    if len(set(outcomes)) != 1 or outcomes[0] == Label.UNCERTAIN:
        card.explanation = 'Source version assertions conflict or do not establish applicability for this version.'
        return card
    card.label = outcomes[0]
    card.rule_id = 'explicit_source_version_condition'
    card.boundary = '; '.join(
        dict.fromkeys(
            f'{target} {item.constraint} ({item.kind})' for item in assertions
        )
    )
    card.explanation = (
        f'The source explicitly documents this query-specific version condition for {target} {exact}. '
        'The verdict covers that condition; complete solution behavior still needs validation.'
    )
    return card


def rank_generic(cards: list[Card], target: str, query: str) -> list[Card]:
    """Metadata changes ordering within verdict groups, never factual labels.

    At most 40 relevance points plus 25 evidence points fit inside each
    100-point verdict bucket. Google/Bing position breaks remaining ties.
    """
    priority = {
        Label.COMPATIBLE: 4,
        Label.UNCERTAIN: 3,
        Label.STALE: 2,
        Label.WRONG_VERSION: 1,
    }
    terms = _query_terms(query, target)
    target_tokens = set(re.findall(r'[\w]+', target.casefold()))
    for card in cards:
        text = ' '.join(
            (card.hit.title, card.hit.snippet, unquote(card.hit.url))
        ).casefold()
        tokens = set(re.findall(r'[\w]+', text))
        subject_tokens = set(re.findall(r'[\w-]+', text))
        # URL punctuation can separate package names; tokenized target matching
        # handles Node.js/Cargo package paths without substring false matches.
        target_match = bool(target_tokens and target_tokens.issubset(tokens))
        matched = sorted(terms.intersection(subject_tokens))
        relevance = (20 if target_match else 0) + min(15, len(matched) * 5)
        if target_match and matched:
            relevance += 5
        reasons = []
        if target_match:
            reasons.append('Target name appears in result title, snippet or URL (+20).')
        if matched:
            reasons.append(
                f'Query subject terms in result metadata: {", ".join(matched[:6])} (+{min(15, len(matched) * 5)}).'
            )
        if target_match and matched:
            reasons.append('Target and query subject both match (+5).')
        if not reasons:
            reasons.append('No target or query subject match in result metadata (+0).')
        reasons.append(
            'Search metadata affects ordering only; verdict requires fetched source evidence.'
        )
        card.relevance_score = relevance
        card.ranking_reasons = reasons
        card.score = (
            priority[card.label] * 100
            + relevance
            + min(25, len(card.evidence) * 5)
            - min(card.hit.position, 10)
        )
    return sorted(cards, key=lambda item: (-item.score, item.hit.id))
