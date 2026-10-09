"""Conservative requirement-to-source evidence triage, not qualification certification."""
from __future__ import annotations

import re

VERSION = 'qualification-evidence-v1'
# Deliberately bounded vocabulary. Unrecognized requirements remain visible for review.
SKILLS = {
    'Python': r'python', 'C#/.NET': r'c\#|\.net', 'SQL': r'sql',
    'Java': r'java', 'TypeScript': r'typescript', 'Go': r'golang|go',
    'PyTorch': r'pytorch', 'TensorFlow': r'tensorflow',
    'AWS': r'aws|amazon web services', 'Azure': r'azure',
    'GCP': r'gcp|google cloud', 'Docker': r'docker', 'Kubernetes': r'kubernetes',
    'Git': r'git', 'CI/CD': r'ci/cd|continuous integration',
    'MCP': r'mcp|model context protocol', 'LangChain': r'langchain',
    'LangGraph': r'langgraph', 'LiteLLM': r'litellm',
    'Pandas': r'pandas', 'NumPy': r'numpy', 'Scikit-learn': r'scikit[- ]learn',
    'React': r'react', 'Angular': r'angular', 'RAG': r'rag|retrieval[- ]augmented generation',
}
REQUIRED = re.compile(r'^(?:minimum|required|basic|essential)?\s*(?:qualifications|requirements|skills)(?: and experience)?$|^what you (?:bring|need)$', re.I)
OPTIONAL = re.compile(r'^(?:preferred|desired|bonus|nice.to.have)(?:\s+qualifications|\s+skills|\s+requirements)?$', re.I)
STOP = re.compile(r'^(?:benefits|about us|compensation|responsibilities|what you.ll do|the .+ experience|equal opportunity).*$', re.I)
CUE = re.compile(r'\b(?:required|must|proficiency|proficient|experience|expertise|familiarity|degree)\b', re.I)
NEGATIVE = re.compile(r'\b(?:no|not|without|lack|lacks|learning|studying|aspiring|planned)\b', re.I)
YEARS = re.compile(r'\b\d+(?:\s*[-–]\s*\d+)?\+?\s+years?\b', re.I)


def _mentions(text: str, pattern: str) -> bool:
    return bool(re.search(r'(?<![\w])(?:' + pattern + r')(?![\w])', text, re.I))


def assess_qualifications(description: str, source_cv: str) -> dict:
    """Keep exact requirement/source excerpts; absence means undocumented, not unqualified.

    Skill mentions only locate potential evidence. Duration, alternatives and whole
    statements always require human interpretation; no percentage of fit is inferred.
    """
    source_lines = [s.strip() for s in source_cv.splitlines() if s.strip() and not s.lstrip().startswith('#')]
    rows = []
    section = 'unspecified'
    for raw in description.splitlines():
        line = raw.strip().strip('#*•- \t').rstrip(':').strip()
        if not line:
            continue
        if REQUIRED.fullmatch(line):
            section = 'required'; continue
        if OPTIONAL.fullmatch(line):
            section = 'preferred'; continue
        if STOP.fullmatch(line):
            section = 'unspecified'; continue
        if section == 'unspecified' and not CUE.search(line):
            continue
        importance = section
        main_clause = re.sub(r'\([^)]*\)', '', line)
        if re.search(r'\b(?:preferred|nice.to.have|a plus|not required)\b', main_clause, re.I):
            importance = 'preferred'
        elif re.search(r'\b(?:must|required)\b', line, re.I):
            importance = 'required'
        skills = []
        for name, pattern in SKILLS.items():
            if _mentions(line, pattern):
                evidence = [s for s in source_lines if _mentions(s, pattern) and not NEGATIVE.search(s)]
                optional_mention = any(_mentions(part, pattern) and re.search(r'a plus|preferred|optional', part, re.I)
                                       for part in re.findall(r'\(([^)]*)\)', line))
                skill_importance = 'preferred' if optional_mention and not _mentions(main_clause, pattern) else importance
                skills.append({'skill': name, 'importance': skill_importance, 'status': 'mention_found' if evidence else 'not_documented',
                               'source_excerpts': evidence})
        rows.append({'requirement': raw.strip(), 'importance': importance,
                     'skills': skills, 'duration_requires_review': bool(YEARS.search(line)),
                     'status': 'needs_review'})
    missing = sorted({s['skill'] for r in rows if r['importance'] != 'preferred'
                      for s in r['skills'] if s['status'] == 'not_documented' and s['importance'] != 'preferred'})
    return {'version': VERSION, 'status': 'needs_review', 'requirements': rows,
            'undocumented_skills': missing,
            'summary': ('Not documented in source CV: ' + ', '.join(missing) + '. ' if missing else '')
                       + 'Qualification review required; role relevance is not verified fit.',
            'limitations': 'Bounded keyword evidence triage; mentions do not prove proficiency, duration or full requirement coverage. Unparsed requirements may remain.'}
