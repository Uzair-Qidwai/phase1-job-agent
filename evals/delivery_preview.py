"""Render a synthetic digest locally; no Gmail credentials, DB writes or send."""
import argparse
from pathlib import Path
from src.emailer import _build_html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        stream.write(_build_html([dict(title="Example AI Engineer", company="Test Company",
                                      location="Toronto", source="fixture", match_score=0.9,
                                      url="https://example.com/job", changes_made="Evidence-backed test preview")]))
    print(f"Preview written to {args.output}; no email sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
