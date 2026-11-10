"""Auditable automatic-selection policy; unknown sponsorship never means yes."""
from __future__ import annotations

import re

from src.candidate_profile import CandidateProfile

VERSION = 'selection-v1-user-feedback'


def assess_selection(*, title: str, location: str, description: str,
                     profile: CandidateProfile, url: str = "") -> dict:
    result = {'version': VERSION, 'automatic_eligible': True, 'lane': 'priority',
              'sponsorship': 'not_assessed', 'evidence': [], 'reason': 'Selection policy disabled.'}
    if not profile.automatic_selection_policy:
        return result

    def hold(lane, reason):
        result.update(automatic_eligible=False, lane=lane, reason=reason)
        return result

    # Word boundaries prevent LA matching unrelated place names; London ON is domestic.
    domestic = bool(re.search(r'\b(canada|toronto|ontario|vancouver|montreal)\b', location, re.I))
    international = bool(re.search(r'\b(new york|nyc|san francisco|los angeles)\b', location, re.I)
                         or (re.search(r'\blondon\b', location, re.I)
                             and re.search(r'\b(uk|united kingdom|england)\b', location, re.I)))
    if not domestic and not international:
        return hold('review', 'Location eligibility is unconfirmed; remote does not imply worldwide access.')
    if international and not domestic:
        statements = [s.strip() for s in re.split(r'[\n.!]+', description) if re.search(r'visa|sponsor', s, re.I)]
        caveats = [s for s in statements if re.search(r'(?:not|aren.t|cannot|unable).*(?:every|all) (?:role|candidate)', s, re.I)]
        negative = [s for s in statements if s not in caveats
                     if re.search(r'\b(no|not|cannot|unable|without|unavailable|aren.t|isn.t|won.t|don.t|doesn.t)\b', s, re.I)]
        positive = [s for s in statements if re.search(
            r'\bwe (?:do |can |will )?(?:offer|provide|support)\b.*\b(?:visa|immigration) sponsorship\b|\bwe (?:do |can |will )?sponsor visas\b|\b(?:visa|immigration) sponsorship (?:is )?available\b', s, re.I)
            and '?' not in s
            and not re.search(r'\b(may|might|case.by.case|depending|if|not|cannot|unable|without|no|aren.t|isn.t|won.t|don.t|doesn.t)\b', s, re.I)]
        result['evidence'] = negative + positive + caveats
        result['sponsorship'] = 'conflicting' if negative and positive else 'unavailable' if negative else 'offered_with_caveat' if positive and caveats else 'offered' if positive else 'unknown'
        if result['sponsorship'] not in {'offered', 'offered_with_caveat'}:
            return hold('review', 'International role needs an explicit, unambiguous sponsorship offer.')
    else:
        result['sponsorship'] = 'domestic_scope'
    decision = profile.vacancy_decisions.get(url.rstrip('/'))
    if decision in {'Stretch', 'Pass'}:
        return hold('stretch' if decision == 'Stretch' else 'deprioritized',
                    'User rated this exact vacancy ' + decision + '.')
    if decision == 'Keep':
        result['reason'] = 'User Keep decision; geographic/sponsorship policy satisfied.'
        return result
    if re.search(r'\b(agency|restaurant)\b', title, re.I):
        return hold('deprioritized', 'Title is in a domain declined in the user review; no company exclusion.')
    if re.search(r'\b(staff|principal|director|head|vp)\b', title, re.I):
        return hold('stretch', 'Leadership scope needs review before automatic selection.')
    if not re.search(r'\b(?:applied ai engineer|ai engineer|technical product manager)\b', title, re.I):
        return hold('stretch', 'Outside the highest-preference role families from the user review.')
    result['reason'] = 'Preferred role family and geographic/sponsorship policy satisfied; qualifications still require review.'
    return result
