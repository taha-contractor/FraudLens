"""Evaluation split helpers (M4).

Two protocols, per the design, are provided as PURE functions over (step,
nameDest, record_uid) so they can be validated WITHOUT materialising a final
train/val/test set (that step is gated until the pipeline passes review):

  * chronological split  — a single step boundary separates earlier (train/val)
    from later (test) time, so no future transaction can inform the past;
  * unseen-destination   — whole destination accounts are held out so a model is
    scored on beneficiaries it never saw during training.

Integrity helpers assert temporal ordering and the train/test disjointness that
must hold before any training is allowed.
"""

from __future__ import annotations


def chronological_split(step, train_max, val_max):
    """Assign a record to 'train' / 'val' / 'test' purely by its ``step``.

    train: step <= train_max ; val: train_max < step <= val_max ; test: step > val_max.
    Boundaries must be ascending so time never flows backwards between sets.
    """
    if not (train_max < val_max):
        raise ValueError("require train_max < val_max for a temporal split")
    if step <= train_max:
        return "train"
    if step <= val_max:
        return "val"
    return "test"


def unseen_destination_holdout(dest_ids, *, seed: int, holdout_frac: float = 0.2):
    """Deterministically hold out a fraction of destination accounts.

    Returns (held_set). All records whose ``nameDest`` is in ``held_set`` belong to
    the unseen-destination evaluation; the rest are eligible for training. The split
    is by ACCOUNT, never by row, so a destination cannot straddle train and test.
    """
    import hashlib
    held = set()
    for d in sorted(set(dest_ids)):
        h = hashlib.sha256(f"{seed}::{d}".encode("utf-8")).hexdigest()
        frac = (int(h[:8], 16) / 0xFFFFFFFF)
        if frac < holdout_frac:
            held.add(d)
    return held


def split_of(record, *, train_max, val_max, held_dests):
    """Combine the two protocols: a record is 'test' if it is in the future OR its
    destination is held out unseen; otherwise train/val by time."""
    when = chronological_split(int(record["step"]), train_max, val_max)
    if record["nameDest"] in held_dests:
        return "test"  # unseen-destination evaluation always takes precedence
    return when


def integrity_checks(assignments) -> list:
    """Given an iterable of (step, label), assert temporal + disjointness rules.

    - every train/val step must be <= every test step (no future leaks to past);
    - a single step maps to exactly one label (a day is never split across sets);
    - train and test sets are disjoint.
    """
    issues = []
    steps_by_label: dict = {}
    step_labels: dict = {}
    for step, label in assignments:
        steps_by_label.setdefault(label, set()).add(step)
        prev = step_labels.get(step)
        if prev is not None and prev != label:
            issues.append(f"step {step} appears in both {prev!r} and {label!r}")
        step_labels[step] = label
    tr = steps_by_label.get("train", set()) | steps_by_label.get("val", set())
    te = steps_by_label.get("test", set())
    if tr & te:
        issues.append(f"train/val and test share steps: {sorted(tr & te)[:5]}")
    if tr and te and max(tr) > min(te):
        issues.append(f"temporal order violated: max(train/val)={max(tr)} > min(test)={min(te)}")
    return issues
