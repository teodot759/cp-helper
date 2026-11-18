"""Verdict computation and the diff view."""

from __future__ import annotations

import difflib

from .models import Case, Result, Verdict
from .runner import CaseRun

_NTSTATUS = {
    0xC0000005: "ACCESS_VIOLATION",
    0xC00000FD: "STACK_OVERFLOW",
    0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC0000096: "PRIV_INSTRUCTION",
    0xC000001D: "ILLEGAL_INSTRUCTION",
    0xC0000409: "STACK_BUFFER_OVERRUN",
    0xC000013A: "CONTROL_C_EXIT",
    0xC0000135: "DLL_NOT_FOUND",
    0xC0000142: "DLL_INIT_FAILED",
}


def exit_description(code: int | None) -> str:
    if code is None:
        return "no exit code"
    if code < 0:
        return f"signal {-code}"
    if code >= 0xC0000000:
        name = _NTSTATUS.get(code)
        if name:
            return f"0x{code:08X} {name}"
    return f"exit {code}"


def _decode(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t\f\v") for line in text.split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def first_difference(expected: str, actual: str) -> tuple[int, str, str] | None:
    expected_n = normalize(expected)
    actual_n = normalize(actual)
    if expected_n == actual_n and expected == actual:
        return None
    exp_lines = expected_n.split("\n")
    act_lines = actual_n.split("\n")
    for index in range(max(len(exp_lines), len(act_lines))):
        exp = exp_lines[index] if index < len(exp_lines) else "<missing line>"
        act = act_lines[index] if index < len(act_lines) else "<missing line>"
        if exp != act:
            return index + 1, exp, act
    # Same normalized text but different bytes (CRLF, trailing spaces, ...).
    for index in range(max(len(expected.split("\n")), len(actual.split("\n")))):
        exp_lines_raw = expected.split("\n")
        act_lines_raw = actual.split("\n")
        exp = exp_lines_raw[index] if index < len(exp_lines_raw) else ""
        act = act_lines_raw[index] if index < len(act_lines_raw) else ""
        if exp != act:
            return index + 1, exp, act
    return None


def make_diff(expected: str, actual: str) -> str:
    expected_n = normalize(expected)
    actual_n = normalize(actual)
    diff = difflib.unified_diff(
        expected_n.split("\n"),
        actual_n.split("\n"),
        fromfile="expected",
        tofile="stdout",
        lineterm="",
        n=3,
    )
    lines = list(diff)
    header = ""
    point = first_difference(expected, actual)
    if point is not None:
        line_no, exp, act = point
        header = f"First difference at line {line_no}:\n  - {exp}\n  + {act}\n\n"
    if not lines:
        return header + "(outputs are identical after normalisation)"
    return header + "\n".join(lines)


def compute_verdict(case: Case, run: CaseRun) -> tuple[Verdict, str, str]:
    """Return ``(verdict, diff, note)``."""
    if run.cancelled:
        return Verdict.SKIPPED, "", "stopped"

    if run.timed_out:
        note = f"wall clock limit {case.timeout_ms} ms exceeded"
        return Verdict.TLE, "", note

    if run.exit_code is None or run.exit_code != 0:
        return Verdict.RE, "", exit_description(run.exit_code)

    actual = _decode(run.stdout)
    if not case.expected_text.strip():
        return Verdict.RAN, "", ""

    expected_bytes = case.expected_text.encode("utf-8")
    if run.stdout == expected_bytes:
        return Verdict.AC, "", ""

    if normalize(case.expected_text) == normalize(actual):
        return Verdict.PE, make_diff(case.expected_text, actual), "matches after normalisation"

    return Verdict.WA, make_diff(case.expected_text, actual), ""


def build_result(case: Case, run: CaseRun) -> Result:
    verdict, diff, note = compute_verdict(case, run)
    stderr = _decode(run.stderr)
    if run.artifact_note:
        stderr = (stderr + "\n" + run.artifact_note).strip()
    if run.truncated:
        note = (note + "; output truncated").strip("; ")
    return Result(
        case_id=case.id,
        verdict=verdict,
        stdout=_decode(run.stdout),
        stdout_raw=run.stdout,
        stderr=stderr,
        exit_code=run.exit_code,
        wall_ms=run.wall_ms,
        produced_files=dict(run.artifacts),
        diff=diff,
        note=note,
    )
