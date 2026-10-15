"""Feature-leakage audit (M4).

Guardrails that assert a feature matrix respects the policy contract: no target,
no oracle flag, no post-execution balance (for the pre policy), no raw identifiers
and no provenance fields are ever present as feature columns.
"""

from __future__ import annotations

from .policies import (FORBIDDEN_AS_FEATURES, POST_EXECUTION_BALANCES,
                       TARGET_COLUMN, policy_columns)


def scan_forbidden(policy: str, feature_columns) -> list:
    """Leakage scan that tolerates encoding (e.g. ``type`` -> ``type_*`` one-hot).

    Checks only the hard rules: no forbidden column (target/oracle/identifiers/
    provenance/event_ts), no post-execution balance in the pre policy, no duplicates.
    Unlike :func:`audit_columns` it does NOT require exact equality to the raw
    contract names, so it can validate a materialised, encoded feature matrix.
    """
    cols = list(feature_columns)
    s = set(cols)
    issues = []
    forbidden = s & set(FORBIDDEN_AS_FEATURES)
    if forbidden:
        issues.append(f"forbidden columns present as features: {sorted(forbidden)}")
    if TARGET_COLUMN in s:
        issues.append("target present as feature")
    if policy == "pre" and (s & set(POST_EXECUTION_BALANCES)):
        issues.append(f"post-execution balance leaks into pre policy: {sorted(s & set(POST_EXECUTION_BALANCES))}")
    if len(cols) != len(s):
        issues.append(f"duplicate feature columns: {sorted({c for c in cols if cols.count(c) > 1})}")
    return issues


def audit_columns(policy: str, feature_columns) -> list:
    """Return a list of leakage issues for the given feature column names.

    Empty list == clean.
    """
    cols = list(feature_columns)
    s = set(cols)
    issues = []

    forbidden = s & set(FORBIDDEN_AS_FEATURES)
    if forbidden:
        issues.append(f"forbidden columns present as features: {sorted(forbidden)}")

    if policy == "pre":
        post = s & set(POST_EXECUTION_BALANCES)
        if post:
            issues.append(f"post-execution balances leak into pre-transaction policy: {sorted(post)}")
    elif policy != "investigation":
        issues.append(f"unknown policy {policy!r}")

    if len(cols) != len(s):
        dupes = sorted({c for c in cols if cols.count(c) > 1})
        issues.append(f"duplicate feature columns: {dupes}")

    # feature matrix must equal the declared contract, not a drift of it
    expected = set(policy_columns(policy))
    if s != expected:
        issues.append(f"columns deviate from {policy} contract: "
                      f"extra={sorted(s - expected)} missing={sorted(expected - s)}")
    return issues


def audit_feature_matrix(policy: str, header: list) -> list:
    """Audit a materialised matrix header (excludes join/target side columns).

    ``header`` is the list of columns actually handed to a model. The target and
    ``record_uid`` live in side tables and must not be in ``header``.
    """
    return audit_columns(policy, header)
