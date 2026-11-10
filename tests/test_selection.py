import pytest
from src.candidate_profile import load_candidate_profile
from src.selection import assess_selection


def select(title='Applied AI Engineer', location='New York, NY', description='We offer visa sponsorship.'):
    return assess_selection(title=title, location=location, description=description,
                            profile=load_candidate_profile())


@pytest.mark.parametrize('location', ['New York, NY', 'San Francisco, CA', 'Los Angeles, CA', 'London, UK'])
def test_sponsorship_required_in_new_cities(location):
    assert select(location=location)['automatic_eligible']
    assert not select(location=location, description='Great benefits')['automatic_eligible']


@pytest.mark.parametrize('description', [
    'We do not provide visa sponsorship.', 'We may offer visa sponsorship.',
    'Do you require visa sponsorship?', 'Will you provide visa sponsorship?',
    'Do we sponsor visas?', 'Visa sponsorship is not available.',
    'We offer visa sponsorship. We cannot sponsor visas.',
    'Candidates must work without visa sponsorship.',
])
def test_ambiguous_negative_or_conflicting_sponsorship_held(description):
    assert not select(description=description)['automatic_eligible']


def test_remote_does_not_bypass_geography():
    assert not select(location='Remote, US')['automatic_eligible']
    assert not select(location='Dallas, TX')['automatic_eligible']
    assert select(location='Remote, Canada', description='')['automatic_eligible']


def test_feedback_generalizes_without_blacklisting_companies():
    assert select(title='Technical Product Manager', location='Toronto')['automatic_eligible']
    assert select(title='Staff Product Manager, AI', location='Toronto')['lane'] == 'stretch'
    assert select(title='AI Product Manager - Agency Exp Required', location='Toronto')['lane'] == 'deprioritized'


def test_exact_feedback_cannot_be_overridden_by_role_match():
    profile = load_candidate_profile()
    url = next(url for url, decision in profile.vacancy_decisions.items() if decision == 'Stretch')
    result = assess_selection(title='Applied AI Engineer', location='Toronto',
                              description='', profile=profile, url=url)
    assert not result['automatic_eligible']
    assert result['lane'] == 'stretch'


def test_keep_does_not_override_sponsorship_gate():
    profile = load_candidate_profile()
    url = next(url for url, decision in profile.vacancy_decisions.items() if decision == 'Keep')
    assert not assess_selection(title='AI Engineer', location='London, UK', description='',
                                profile=profile, url=url)['automatic_eligible']


def test_employer_willingness_is_not_a_guarantee_for_every_candidate():
    result = select(description="We do sponsor visas. However, we aren't able to sponsor visas for every role and every candidate.")
    assert result['automatic_eligible']
    assert result['sponsorship'] == 'offered_with_caveat'
    assert len(result['evidence']) == 2
