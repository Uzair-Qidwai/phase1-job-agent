from src.qualifications import assess_qualifications as assess


def test_high_relevance_cannot_establish_python_or_duration():
    r = assess('Requirements\n8+ years of software development experience with Python.\nSQL required.',
               '# Python\nBuilt an AI agent. Led a team for 10 years.')
    assert r['undocumented_skills'] == ['Python', 'SQL']
    assert r['requirements'][0]['duration_requires_review']
    assert all(x['status'] == 'needs_review' for x in r['requirements'])


def test_evidence_is_exact_and_not_a_proficiency_claim():
    r = assess('Proficiency in Python required.', '- Built evaluation tools with Python.')
    skill = r['requirements'][0]['skills'][0]
    assert skill['status'] == 'mention_found'
    assert skill['source_excerpts'] == ['- Built evaluation tools with Python.']
    assert r['status'] == 'needs_review'


def test_negation_learning_and_boundaries_do_not_supply_evidence():
    r = assess('Python and Java required.', 'No Python experience.\nLearning Python.\nBuilt JavaScript tools.')
    assert r['undocumented_skills'] == ['Java', 'Python']


def test_optional_skills_not_reported_as_required_gaps():
    r = assess('Required Qualifications\nPython\nPreferred Qualifications\nAWS\nDocker is a plus\nBenefits\nGreat team', '')
    assert r['undocumented_skills'] == ['Python']
    assert len(r['requirements']) == 3


def test_alternatives_unrecognized_requirements_and_degree_stay_for_review():
    r = assess('Requirements\nAWS or Azure\nA completed CS degree\nStrong stakeholder communication', 'Used AWS.\nCS degree in progress.')
    assert len(r['requirements']) == 3
    assert r['requirements'][0]['requirement'] == 'AWS or Azure'
    assert all(x['status'] == 'needs_review' for x in r['requirements'])


def test_no_recognized_requirement_never_means_qualified():
    r = assess('Join our great team!', 'Python')
    assert not r['requirements']
    assert r['status'] == 'needs_review'


def test_optional_parenthetical_does_not_hide_required_python():
    r = assess('8+ years of experience with Python (Go or TypeScript a plus).', '')
    assert r['undocumented_skills'] == ['Python']
