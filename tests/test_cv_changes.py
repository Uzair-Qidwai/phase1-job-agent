from collections import Counter

import pytest

from src.cv_changes import describe_changes, emphasize_sections
from src.cv_validation import TailoredCVResult, validate_tailored_cv, _claim_segments

SOURCE = '''# Fictional Candidate

## Summary
Built evaluation tools for documented projects.

## Education
Expected graduation in 2027.

## Teaching Experience
### Teaching Assistant | Example University
- Assisted students with debugging exercises.

## Industry Experience
### Founder | Example Company
- Led a team of four on a documented platform.

## Projects
- Built an evaluation harness measuring latency and accuracy.

## Additional Information
Languages: English.
'''


@pytest.mark.parametrize('title,first', [
    ('AI Engineer', '## Projects'),
    ('Senior Product Manager', '## Industry Experience'),
    ('Quantitative Analyst', '## Education'),
])
def test_layout_retains_facts_and_employer_context(title,first):
    output,layout=emphasize_sections(SOURCE.rstrip(),title)
    headings=[line for line in output.splitlines() if line.startswith('## ')]
    assert headings[0]=='## Summary' and headings[1]==first
    assert headings[-1]=='## Additional Information'
    assert Counter(_claim_segments(output))==Counter(_claim_segments(SOURCE))
    result=TailoredCVResult(tailored_cv=output,changes_made='Source wording retained.',evidence_used=[{
        'claim':'Built an evaluation harness measuring latency and accuracy.',
        'source':'master_cv','source_text':'Built an evaluation harness measuring latency and accuracy.'}])
    assert validate_tailored_cv(result,master_cv=SOURCE,candidate_profile_text='').valid
    assert 'Expected graduation in 2027.' in output
    assert '### Founder | Example Company\n- Led a team of four' in output
    again,_=emphasize_sections(output,title)
    assert again==output
    assert layout['family'] is not None


@pytest.mark.parametrize('text,title', [
    (SOURCE,'Unclassified Role'),
    ('Plain CV text with no Markdown sections.','AI Engineer'),
    (SOURCE+'\n```\n## Projects\nExample\n```','AI Engineer'),
])
def test_ambiguous_layout_is_not_guessed(text,title):
    output,layout=emphasize_sections(text,title)
    assert output==text and not layout['sections_reordered']


def test_summaries_describe_observed_changes_not_model_intent():
    assert describe_changes(SOURCE,SOURCE)['summary']=='Source CV unchanged.'
    output,_=emphasize_sections(SOURCE,'AI Engineer')
    report=describe_changes(SOURCE,output)
    assert report['summary']=='Source wording retained; complete sections reordered.'
    assert report['added_or_revised_passages']==report['omitted_or_replaced_passages']==0
    assert '--- Source CV' in report['diff'] and '+++ Preview CV' in report['diff']


def test_omissions_rewrites_and_duplicate_passages_are_reported():
    source='Documented work.\nDocumented work.\nExpected graduation in 2027.'
    output='Documented work.\nGraduated in 2027.'
    report=describe_changes(source,output)
    assert report['added_or_revised_passages']==1
    assert report['omitted_or_replaced_passages']==2
    assert 'Review the differences.' in report['summary']
    # This report identifies changes; the separate factuality gate must reject them.
    assert '-Expected graduation' in report['diff']
