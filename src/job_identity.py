"""Source-aware job identity and URL canonicalization.

Phase 2 uses native source identifiers wherever possible. URLs remain useful
metadata, but tracking parameters must not define identity and identity-bearing
parameters must never be discarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "trk",
    "trackingId",
    "ref",
    "refId",
}


@dataclass(frozen=True)
class JobIdentity:
    source: str
    source_job_id: str | None
    canonical_url: str

    @property
    def dedupe_key(self) -> str:
        if self.source_job_id:
            return f"{self.source}:{self.source_job_id}"
        return f"{self.source}:{self.canonical_url}"


def _clean_query(query: str, *, keep_only: set[str] | None = None) -> str:
    items = parse_qsl(query, keep_blank_values=False)
    cleaned: list[tuple[str, str]] = []
    for key, value in items:
        if keep_only is not None and key not in keep_only:
            continue
        if key in TRACKING_PARAMS or key.startswith("utm_"):
            continue
        cleaned.append((key, value))
    cleaned.sort()
    return urlencode(cleaned)


def canonicalize_url(url: str, source: str) -> str:
    """Return a deterministic source-aware canonical URL."""

    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    host = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    source = source.lower().strip()

    if source == "indeed":
        # Indeed job identity is carried by the jk query parameter.
        query = _clean_query(parts.query, keep_only={"jk"})
    else:
        query = _clean_query(parts.query)

    return urlunsplit((scheme, host, path, query, ""))


def extract_source_job_id(url: str, source: str) -> str | None:
    """Extract a stable native source job identifier when one is available."""

    source = source.lower().strip()
    parts = urlsplit(url)

    if source == "indeed":
        params = dict(parse_qsl(parts.query, keep_blank_values=False))
        return params.get("jk")

    if source == "linkedin":
        # Public LinkedIn job URLs commonly contain /jobs/view/<numeric-id>.
        segments = [segment for segment in parts.path.split("/") if segment]
        if "view" in segments:
            idx = segments.index("view")
            if idx + 1 < len(segments):
                candidate = segments[idx + 1].split("-")[-1]
                if candidate.isdigit():
                    return candidate

    return None


def build_job_identity(url: str, source: str) -> JobIdentity:
    return JobIdentity(
        source=source.lower().strip(),
        source_job_id=extract_source_job_id(url, source),
        canonical_url=canonicalize_url(url, source),
    )
