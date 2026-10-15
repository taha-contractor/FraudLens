"""M4 feature package: causal feature engineering with separated policies.

Two feature policies are defined and kept SEPARATE (never combined into one
matrix), per the enhanced-PaySim design:

  * pre-transaction risk scoring  -> only info observable BEFORE execution;
  * post-transaction investigation -> post-event info allowed only when it was
    available at investigation time, never future records/labels.

The feature contract (which columns exist, which are forbidden as features, and
the strictly-prior history features) is single-sourced here so leakage audits and
the builder cannot drift apart.
"""
