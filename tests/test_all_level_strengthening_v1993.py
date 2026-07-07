from app.document_parser import parse_document
from app.deterministic_supervisory_checklist import deterministic_supervisory_checklist_issues
from app.comment_quality import prepare_public_issues


def _fixture_paragraphs():
    with open('/mnt/data/Chapter 1 corrections-supervisor-reviewed (20).docx', 'rb') as handle:
        return parse_document(handle.read(), 'Chapter 1 corrections-supervisor-reviewed (20).docx')


def test_mphil_chapter_one_deterministic_review_has_broad_coverage():
    issues = deterministic_supervisory_checklist_issues(
        _fixture_paragraphs(),
        academic_level='Research Masters / MPhil',
        research_approach='quantitative',
        max_issues=80,
    )
    public, stats = prepare_public_issues(issues)
    categories = {row.get('category') for row in public}
    assert len(public) >= 18
    assert 'theoretical_grounding' in categories
    assert 'research_gap_and_problem' in categories
    assert 'objectives_questions_hypotheses' in categories
    assert 'citations_and_sources' in categories
    assert not any('no definitions follow' in (row.get('assessment') or '').lower() for row in public)


def test_all_declared_levels_receive_level_specific_contribution_comment():
    levels = [
        'Bachelors',
        'Non-Research Masters',
        'Research Masters / MPhil',
        'Professional Doctorate',
        'PhD',
    ]
    paragraphs = _fixture_paragraphs()
    for level in levels:
        issues = deterministic_supervisory_checklist_issues(
            paragraphs,
            academic_level=level,
            research_approach='quantitative',
            max_issues=80,
        )
        public, _stats = prepare_public_issues(issues)
        titles = ' '.join(row.get('issue_title', '') for row in public).lower()
        assert 'contribution' in titles


def test_comment_polishing_removes_malformed_imperatives():
    sample = [{
        'category': 'research_gap_and_problem',
        'section': 'Statement of the Problem',
        'issue_title': 'Local evidence is weak',
        'assessment': 'The problem statement is generic.',
        'academic_consequence': 'The justification is weak.',
        'required_action': 'Revise the marked passage so that it incorporate local evidence from the Central Region.',
        'confidence': 0.9,
        'severity': 'major',
    }]
    public, _stats = prepare_public_issues(sample)
    assert public
    assert 'so that it incorporate' not in public[0]['required_action'].lower()
    assert 'by incorporating' in public[0]['required_action'].lower()
