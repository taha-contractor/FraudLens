"""FraudLens enhanced-dataset generator (M2 skeleton).

This package provides the modular generator *structure*. At the M2 stage only
configuration, deterministic seeding, schema/provenance definitions, the account
registry ledger and scenario definitions are implemented. Transaction emission,
chain construction and strictly-prior feature building are intentionally left as
interfaces (M3+) — **no enhanced dataset is produced yet.**
"""

GENERATOR_VERSION = "0.1.0"
