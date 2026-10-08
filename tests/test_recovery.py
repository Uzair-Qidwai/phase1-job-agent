import pytest

from src.recovery import RUNNABLE_RESTART_STAGES, safe_restart_stage


@pytest.mark.parametrize(
    ("failed_stage", "restart_stage"),
    [
        ("created", "scraping"),
        ("scraping", "scraping"),
        ("persisting", "scraping"),
        ("filtering", "filtering"),
        ("ranking", "filtering"),
        ("tailoring", "tailoring"),
        ("notifying", "notifying"),
    ],
)
def test_safe_restart_stage(failed_stage: str, restart_stage: str) -> None:
    assert safe_restart_stage(failed_stage) == restart_stage
    assert restart_stage in RUNNABLE_RESTART_STAGES


def test_unknown_failure_stage_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported failed pipeline stage"):
        safe_restart_stage("unknown-stage")
