"""Safe restart policy for failed Phase 2 pipeline runs."""

from __future__ import annotations


SAFE_RESTART_STAGE_BY_FAILURE = {
    "created": "scraping",
    "scraping": "scraping",
    "persisting": "scraping",
    "filtering": "filtering",
    "ranking": "filtering",
    "tailoring": "tailoring",
    "notifying": "notifying",
}

RUNNABLE_RESTART_STAGES = frozenset(SAFE_RESTART_STAGE_BY_FAILURE.values())


def safe_restart_stage(failed_stage: str) -> str:
    """Return the earliest stage that can safely reconstruct required state."""
    try:
        return SAFE_RESTART_STAGE_BY_FAILURE[failed_stage]
    except KeyError as exc:
        raise ValueError(f"Unsupported failed pipeline stage: {failed_stage}") from exc


def main(argv=None) -> int:
    import argparse
    import json
    from uuid import UUID
    from src.tracker import PipelineAlreadyRunning, recover_abandoned_run

    parser = argparse.ArgumentParser(description="Recover a stopped worker's stranded run")
    parser.add_argument("run_id", type=UUID)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--confirm-workers-stopped", action="store_true", required=True,
                        help="Confirm all workers and trigger entrypoints are stopped")
    args = parser.parse_args(argv)
    try:
        result = recover_abandoned_run(str(args.run_id), reason=args.reason,
                                       workers_stopped=args.confirm_workers_stopped)
    except (ValueError, PipelineAlreadyRunning) as exc:
        parser.exit(1, f"Recovery refused: {exc}\n")
    print(json.dumps(result, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
