"""FraudLens M5 modelling package.

Feature-matrix loading, fixed evaluation splits, model registry, fraud-detection
metrics and ensemble/winner selection. Trains only after the leakage and temporal
integrity gates pass. CSV in/out for datasets; JSON for manifests.
"""
