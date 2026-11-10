from evals.metrics import pairwise_accuracy, precision_at_k


def test_precision_at_k() -> None:
    predicted = ["strong-1", "weak-1", "strong-2"]
    relevant = {"strong-1", "strong-2"}
    assert precision_at_k(predicted, relevant, 3) == 2 / 3


def test_pairwise_accuracy() -> None:
    scores = {"ai-engineer": 91, "quant": 82, "nurse": 8}
    pairs = [
        ("ai-engineer", "quant"),
        ("ai-engineer", "nurse"),
        ("quant", "nurse"),
    ]
    assert pairwise_accuracy(scores, pairs) == 1.0


def test_pairwise_accuracy_detects_bad_ordering() -> None:
    scores = {"strong": 10, "weak": 90}
    assert pairwise_accuracy(scores, [("strong", "weak")]) == 0.0
