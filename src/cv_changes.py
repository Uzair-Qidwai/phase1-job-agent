"""Deterministic CV layout and observed differences, never inferred qualifications."""
from __future__ import annotations

from collections import Counter
import difflib
import re

from src.cv_validation import _claim_segments

LAYOUT_VERSION = 'section-emphasis-v1'
CHANGE_VERSION = 'observed-cv-diff-v1'


def _section_kind(heading: str) -> str | None:
    text = heading.casefold()
    # Teaching experience must not be conflated with industry experience.
    for kind, pattern in (
        ('teaching', r'\b(teaching|mentoring)\b'),
        ('education', r'\b(education|credentials|certifications)\b'),
        ('projects', r'\b(projects|portfolio)\b'),
        ('skills', r'\b(skills|competencies)\b'),
        ('experience', r'\b(experience|employment|career)\b'),
    ):
        if re.search(pattern, text):
            return kind
    return None


def emphasize_sections(text: str, job_title: str) -> tuple[str, dict]:
    """Move complete level-two sections only; preserve their exact contents.

    Fixed role-family preferences are presentation heuristics, not a fit score.
    Unknown roles/layouts remain unchanged. Profile/contact/unknown sections keep
    their slots. Employer headings and bullets always travel with their parent.
    """
    title = job_title.casefold()
    if re.search(r'\bproduct\s+(?:manager|management|lead|owner)\b', title):
        family = 'product'
        priority = ['experience', 'projects', 'skills', 'education', 'teaching']
    elif re.search(r'\b(quantitative|quant|investment|trading)\b', title):
        family = 'quantitative'
        priority = ['education', 'experience', 'projects', 'skills', 'teaching']
    elif re.search(r'\b(engineer|engineering|developer)\b', title):
        family = 'engineering'
        priority = ['skills', 'projects', 'experience', 'education', 'teaching']
    else:
        return text, {'version': LAYOUT_VERSION, 'family': None, 'sections_reordered': False}
    # Require a well-delimited Markdown document; never guess at plain-text roles.
    original = text
    if '```' in text or '~~~' in text:
        return text, {'version': LAYOUT_VERSION, 'family': family, 'sections_reordered': False}
    text = text if text.endswith('\n') else text + '\n'
    starts = list(re.finditer(r'^## (?!#).+\n', text, flags=re.MULTILINE))
    if len(starts) < 2:
        return original, {'version': LAYOUT_VERSION, 'family': family, 'sections_reordered': False}
    prefix = text[:starts[0].start()]
    blocks = [text[m.start():starts[i+1].start() if i+1 < len(starts) else len(text)]
              for i, m in enumerate(starts)]
    kinds = [_section_kind(block.splitlines()[0]) for block in blocks]
    slots = [i for i, kind in enumerate(kinds) if kind is not None]
    ordered = sorted(slots, key=lambda i: priority.index(kinds[i]))
    if ordered == slots:
        return original, {'version': LAYOUT_VERSION, 'family': family, 'sections_reordered': False}
    result = list(blocks)
    for slot, original in zip(slots, ordered):
        result[slot] = blocks[original]
    output = prefix + ''.join(result)
    return output, {'version': LAYOUT_VERSION, 'family': family,
                    'sections_reordered': output != text}


def describe_changes(source: str, output: str) -> dict:
    """Count normalized text passages; a difference is not a new verified fact."""
    before, after = _claim_segments(source), _claim_segments(output)
    removed = list((Counter(before) - Counter(after)).elements())
    added = list((Counter(after) - Counter(before)).elements())
    headings = lambda value: re.findall(r'^## (?!#).+$', value, flags=re.MULTILINE)
    section_order_changed = (Counter(headings(source)) == Counter(headings(output))
                             and headings(source) != headings(output))
    if not added and not removed:
        if source.strip() == output.strip():
            summary = 'Source CV unchanged.'
        elif section_order_changed:
            summary = 'Source wording retained; complete sections reordered.'
        elif before != after:
            summary = 'Source wording retained; passages reordered.'
        else:
            summary = 'Source wording retained; formatting changed.'
    else:
        summary = (f'{len(added)} added or revised passage(s); '
                   f'{len(removed)} omitted or replaced source passage(s). Review the differences.')
    return {'version': CHANGE_VERSION, 'summary': summary,
            'added_or_revised_passages': len(added), 'omitted_or_replaced_passages': len(removed),
            'section_order_changed': section_order_changed,
            'diff': ''.join(difflib.unified_diff(source.splitlines(keepends=True),
                                                output.splitlines(keepends=True),
                                                fromfile='Source CV', tofile='Preview CV'))}
