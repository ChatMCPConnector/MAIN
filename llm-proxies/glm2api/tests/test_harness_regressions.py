import sys
from pathlib import Path


HARNESS_DIR = Path(__file__).resolve().parents[1] / "harness"
sys.path.insert(0, str(HARNESS_DIR))

import order_matrix  # noqa: E402
import sweep2  # noqa: E402


def test_order_matrix_rejects_unlisted_chunk_output(monkeypatch):
    class _Accumulator:
        def build_response(self):
            return {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {"function": {"name": "read", "arguments": "{}"}}
                            ]
                        }
                    }
                ]
            }

    monkeypatch.setattr(
        order_matrix,
        "stream",
        lambda *_args, **_kwargs: (
            "Der Bericht ist fuer Sie.  ",
            "",
            _Accumulator(),
        ),
    )
    label, parts, expected, expected_calls = next(
        row for row in order_matrix.LAYOUTS if row[0] == "rand-links-im-carry"
    )

    _streamed, problems = order_matrix.check(
        parts, expected, expected_calls, 1, label
    )

    assert any(problem.startswith("chunk-output-unbekannt:") for problem in problems)


def test_order_matrix_known_whitespace_variants_are_chunk_exact():
    label, parts, expected, expected_calls = next(
        row for row in order_matrix.LAYOUTS if row[0] == "rand-links-im-carry"
    )

    expected_output = order_matrix.KNOWN_CHUNK_OUTPUTS[label][1]
    streamed, problems = order_matrix.check(
        parts, expected, expected_calls, 1, label
    )

    assert streamed == expected_output
    assert any(problem.startswith("soll-exakt:") for problem in problems)
    assert not any(problem.startswith("chunk-output-unbekannt:") for problem in problems)

    # Ein korrekt ge-whitelisteter Output darf als bekannte reine
    # Whitespace-Abweichung gelten, aber nur ohne weitere Problemklassen.
    whitespace_problems = [
        problem
        for problem in problems
        if problem.startswith(("soll-exakt:", "chunk-invariante:"))
    ]
    other_problems = [
        problem for problem in problems if problem not in whitespace_problems
    ]
    assert streamed == order_matrix.KNOWN_CHUNK_OUTPUTS[label][1]
    assert whitespace_problems
    assert not other_problems

    unexpected_output, unexpected_problems = order_matrix.check(
        parts, expected, expected_calls, 1, label, expected_stream=expected_output + " "
    )
    assert unexpected_output == expected_output
    assert any(
        problem.startswith("chunk-invariante:")
        for problem in unexpected_problems
    )


def test_sweep_known_exception_does_not_hide_call_failure():
    label, parts, allowed, expected_stream, expected_calls, expected_finish, expected_body = next(
        row for row in sweep2.SCENARIOS if row[0] == "selbst-steuerung+call"
    )

    streamed, problems = sweep2.check(
        label,
        parts,
        allowed,
        expected_stream,
        ["unexpected_tool"],
        expected_finish,
        expected_body,
        1,
    )

    assert streamed == ""
    assert any(problem.startswith("aufrufe:") for problem in problems)
    assert not sweep2._is_known_stream_only_difference(
        label, 1, streamed, expected_stream, problems
    )


def test_sweep_no_longer_whitelists_fixed_s14_residue():
    assert "selbst-steuerung+call" not in sweep2.KNOWN
    assert not sweep2._is_known_stream_only_difference(
        "selbst-steuerung+call",
        1,
        "D",
        "",
        ["stream: IST 'D' != SOLL ''"],
    )
    assert not sweep2._is_known_stream_only_difference(
        "selbst-steuerung+call",
        1,
        "De",
        "",
        ["stream: IST 'De' != SOLL ''"],
    )
    assert not sweep2._is_known_stream_only_difference(
        "selbst-steuerung+call",
        2,
        "D",
        "",
        ["stream: IST 'D' != SOLL ''"],
    )
    assert not sweep2._is_known_stream_only_difference(
        "selbst-steuerung+call",
        1,
        "D",
        "",
        ["stream: IST 'D' != SOLL ''", "aufrufe: IST [] != SOLL ['read']"],
    )


def test_sweep_preamble_followup_expectation_preserves_paragraph_boundary():
    label, parts, allowed, expected_stream, expected_calls, expected_finish, expected_body = next(
        row for row in sweep2.SCENARIOS if row[0] == "praeambel+call+prosa"
    )

    _streamed, problems = sweep2.check(
        label,
        parts,
        allowed,
        expected_stream,
        expected_calls,
        expected_finish,
        expected_body,
        1,
    )

    assert not problems
