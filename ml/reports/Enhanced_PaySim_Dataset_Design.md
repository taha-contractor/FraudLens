# FraudLens — Enhanced PaySim Dataset Design & Limitation-Reduction Specification

**Phase:** Specification + **M1–M2 data infrastructure** implemented (read-only loader + generator
skeleton). No full dataset has been generated and no models have been trained.

**Operational decision (approved):** the **enhanced synthetic dataset is the sole operational ML dataset**
used by the FraudLens pipeline for training, validation, testing and inference development. The original
PaySim CSV is a **read-only source** folded into that dataset through audited / transformed
original-derived records — **not** a separate operational benchmark. Original and generated records are
distinguished only via **provenance metadata**; original fraud labels are **never silently changed**, and
generated fraud labels remain **documented simulation assumptions**, not validated real-world fraud.
**Authoritative raw input (read-only, immutable):** `ml/data/raw/PS_20174392719_1491204439457_log.csv`
**SHA-256:** `16910F90577B0D981BF8FF289714510BB89BC71BFF7D3F220F024E287E4EEA6B` · **Size:** 493,534,783 bytes (verified unchanged this session)
**Status of every PaySim figure below:** *VERIFIED* by streaming the actual file (not taken from secondary sources).

> Provenance-honesty note: PaySim is **synthetic mobile-money** data produced by the PaySim
> simulator (Motiwalla, City, University of London, 2019). Neither the original nor any enhanced
> dataset may be described as real bank customers, real accounts, or real transactions. All fraud
> "scenarios" in this spec are **configurable, documented assumptions**, **not** validated real-world
> fraud typologies.

---

## 1. Existing dataset limitations (verified baseline)

Verified facts used throughout:

| Property | Verified value |
|---|---|
| Rows / columns | 6,362,620 / 11 (header present) |
| `isFraud = 1` | 8,213 (0.12908%) |
| `isFlaggedFraud = 1` | 16 (0.000251%) |
| Fraud **by type** | CASH_OUT 4,116 + TRANSFER 4,097 — **0 in PAYMENT / CASH_IN / DEBIT** |
| Type counts | CASH_OUT 2,237,500 · PAYMENT 2,151,495 · CASH_IN 1,399,284 · TRANSFER 532,909 · DEBIT 41,432 |
| Missing values | 0 in every column |
| Exact duplicate rows | 0 |
| Unique `nameOrig` | 6,353,307 of 6,362,620 (**~99.9% of origins appear once**) |
| Unique `nameDest` | 2,722,362 (prefixes C 4,211,125 / M 2,151,495 — reused) |
| `step` | 1–743, all distinct, rows non-decreasing (day-granularity, **no wall-clock timestamps**) |
| `amount` | min 0.0, max 92,445,516.64, mean 179,861.9, **no negatives** |
| Origin-debit balance identity | `newbalanceOrig ≈ oldbalanceOrg − amount` holds for only **25.9%** of debit-type rows |
| Destination balances | **36.4%** of rows have `oldbalanceDest = newbalanceDest = 0` |
| Volume vs fraud | rows front-loaded (steps 1–~322 ≈ 70% of rows); **fraud back-loaded** (≈0.08% early → ≈0.42% late) |

Derived limitations:

* **L1 — Fraud-type concentration.** Labels exist only in TRANSFER & CASH_OUT. A model can learn the simulator artifact "fraud ⇒ type ∈ {TRANSFER, CASH_OUT}" and never scores PAYMENT/CASH_IN/DEBIT.
* **L2 — Near-absent account histories.** Because origins are ~unique per transaction, per-account velocity/history features (the backbone of the earlier India Benchmark V1 research line) cannot be derived. Historical context is limited to reused *destinations*.
* **L3 — Balance inconsistency.** Post-transaction balances violate the debit identity ~74% of the time; destination balances are frequently zeroed. `oldbalance*`/`newbalance*` are unreliable as truth.
* **L4 — Insufficient transaction relationships.** No explicit linkage between related transactions (e.g. a fraud TRANSFER→CASH_OUT chain to the same mule) and no stable recurring account identity across a behavioural sequence.
* **L5 — Severe class imbalance** (0.129%) coupled with **temporal prevalence shift** between early and late steps.
* **L6 — Feature leakage risk.** `newbalanceOrig`, `newbalanceDest`, `isFlaggedFraud` are post-event / oracle-like and leak the outcome if used naively.
* **L7 — Evaluation weaknesses.** Day-granularity `step` only; no fine temporal resolution; random splits leak related transactions; no natural held-out "unseen account" because origins are already unique; no calibration / cost / per-scenario reporting.
* **L8 — Provenance uncertainty.** Measured rows/fraud (6,362,620 / 8,213) diverge from commonly cited PaySim figures (~6,359,668 / ~8,722); official checksum/licence not confirmed.

---

## 2. Which limitations can be reduced

| # | Limitation | Reducible by the enhanced generator? | Notes / boundary |
|---|---|---|---|
| L1 | Fraud-type concentration | **Addressed (synthetic)** | Generator emits labelled fraud across **all 5 types**; but patterns are *assumptions*, not validated real fraud. Original-derived records keep their type-confined labels but are **combined** with generated fraud in the other types, so the sole operational dataset is not type-confined (the original CSV is a read-only source, not a held-out benchmark). |
| L2 | Limited account histories | **Addressed (synthetic)** | Generator maintains persistent accounts with rich, repeated, chronological history so history features become learnable. |
| L3 | Balance inconsistency | **Addressed (synthetic)** / **Cannot fix original** | Generated data keeps a **balanced ledger** (identity holds by construction). The **original file is immutable** — its inconsistency remains and is documented, not repaired. |
| L4 | Transaction relationships | **Addressed (synthetic)** | Generator emits **linked chains** with stable ids and a `chain_id`. |
| L5 | Class imbalance + shift | **Partially / configurable** | Configurable prevalence; must NOT be equal-balanced to inflate scores; temporal shift is retained deliberately for a realistic holdout. Oversampling is a separate later training-only experiment. |
| L6 | Feature leakage | **Addressed (policy)** | Handled by the **two feature policies** (§7) — exclude post-event/oracle fields from the pre-transaction model. Raw columns remain available for the investigation policy. |
| L7 | Evaluation weaknesses | **Partially addressed** | Generator can add **sub-step timestamps** and reusable accounts to enable unseen-destination + chain-safe splits. "Synthetic ≠ real" can **never** be removed. |
| L8 | Provenance uncertainty | **Cannot remove here** | Requires re-verification against the official source (out of scope; needs authorization to download). |

**Cannot be removed at all:** real-world validity (data is synthetic); the original file's own properties (immutable); the original's provenance ambiguity (until separately verified).

---

## 3. Proposed generator architecture

A **separate, reproducible, config-driven** synthetic generator. Deterministic output =
`f(config_version, generator_version, random_seed, account_registry_snapshot)`. No random wall-clock
or hidden state; a re-run with the same seed + config byte-reproduces the dataset.

Modules (proposed under `ml/src/generator/`):

1. **`config.py` / `configs/*.yaml`** — declarative knobs: scale (target row count), per-type volumes, per-scenario weights, prevalence targets, account-population sizes, amount distributions, step/timestamp horizon, seed. Every run pins a full config snapshot.
2. **`accounts.py` — AccountRegistry.** Persistent population of origin and destination accounts with stable ids (same `C##########` / `M##########` format and digit entropy as PaySim), opening balances, and a **running ledger** so `oldbalance`/`newbalance` are internally consistent. Accounts recur across many transactions and over time (fixes L2/L4).
3. **`scenarios.py` — ScenarioLibrary.** Explicit, id'd **legitimate** and **fraud** behavioural templates per transaction type (§5). Each scenario is a distribution + rules (amount range, cadence, velocity, beneficiary novelty, chain topology) and carries a `scenario_id`. Legit "unusual" controls sit alongside fraud so that **unusual ≠ automatically fraudulent**.
4. **`emitter.py` — TransactionEmitter.** Generates a chronologically-ordered stream by `step` (+ sub-step timestamp), respecting the ledger, drawing counts per scenario from config. Emits `record_uid`, `chain_id`, `scenario_id`, and the PaySim-compatible fields.
5. **`chains.py` — ChainBuilder.** Constructs linked multi-step sequences (e.g. first-transfer→immediate-cash-out; layering deposits→drain) with a shared `chain_id` and a single consistent fraud label for the whole chain (fixes L4; enables chain-safe splitting).
6. **`features.py` — StrictlyPriorFeatureBuilder.** Computes historical/velocity features by **causal pass** (only records strictly earlier than the current timestamp, per key), identical contract to the causal pass validated in the earlier India Benchmark V1 research. No future rows, no future labels (§6, §9).
7. **`provenance.py` — ProvenanceAnnotator.** Writes the separate metadata table (§4). Provenance never enters the feature matrix.
8. **`validate.py` — ValidationHarness.** Runs the §10 data-quality gates; a run is only "promoted" if all hard gates pass.
9. **`cli.py` / `run_generate.py`** — entrypoint that ties seed+config, writes artifacts, records a manifest (config snapshot, seed, versions, checksums, counts).

**Integration rule:** generated records are **never** written into `data/raw/`; they are produced into
`data/processed/enhanced/` and joined to the original only through the provenance/`record_uid` scheme.
Approved, audited original-derived records and generated records are **combined into the single operational
enhanced dataset**; the original CSV is a **read-only source**, never a separate benchmark (§9).

---

## 4. Proposed schema & provenance strategy

### 4.1 Feature table (PaySim-compatible) — `data/processed/enhanced/enhanced_transactions.csv`
Columns available to the model (subject to the §7 policy that selects the subset):

* **Base (mirrors PaySim):** `step`, `event_ts` *(sub-step timestamp; generated rows only — original left untouched)*, `type`, `amount`, `nameOrig`, `oldbalanceOrg`, `newbalanceOrig`, `nameDest`, `oldbalanceDest`, `newbalanceDest`
* **Targets:** `isFraud` (0/1). `isFlaggedFraud` retained **only** for original rows (investigation policy); generated rows are set to `0` — the oracle flag is never fabricated, and the column is excluded from the initial predictive feature set (approved decision 13).
* **Derived, strictly-prior features (generated; optionally re-derived for original where keys allow):** e.g. `origin_txn_count_prev`, `origin_avg_amount_prev`, `origin_amount_dev_prev`, `origin_time_since_prev_txn`, `dest_txn_count_prev`, `dest_unique_origins_prev`, `origin_amount_last24h`, `origin_txn_last24h`, `origin_unique_dests_last24h` — every one computed only from records with `event_ts` **strictly before** the current row (no self-row, no future).

### 4.2 Provenance table (kept **separate** from features) — `data/processed/enhanced/provenance.csv`
Joined by `record_uid`; **never** used as a model feature:

| Field | Meaning |
|---|---|
| `record_uid` | stable unique id linking features ↔ provenance (opaque, random, same format both sources) |
| `source_dataset` | `paysim_original` \| `fraudlens_generated` |
| `record_origin` | `original` \| `generated` |
| `generator_version` | semver of generator build |
| `config_version` / `generation_run_id` | pinned config id + per-run id (seed + uuid) |
| `scenario_id` | for generated rows (`null` for original) |
| `chain_id` | shared id for linked-chain rows (`null` if unlinked) |
| `dataset_version` | version of this derived dataset release |

### 4.3 No-artificial-tells rule (anti-shortcut)
Generated rows must **not** be trivially separable from original rows via feature space. Enforced by:
matching id formats/entropy, drawing amounts from continuous distributions (no rounding signatures),
no constant/sentinel columns, no `event_ts` present for original rows in a way that leaks origin, and a
**discriminator QC test** (§10): a classifier trained to tell generated-vs-original from **features only**
should achieve ≈ random (AUC ≈ 0.5). Provenance lives only in the separate table, joined after the fact.

---

## 5. Fraud & legitimate scenario specifications

All scenarios are **configurable assumptions** with an explicit `scenario_id`, weight, and a documented
behavioral rationale. Every type has **both** fraud and **legitimate "unusual-but-normal" controls**, so
novelty/high-value/frequency alone do **not** imply fraud (directly counters L1 and shortcut learning).

| Type | Legitimate scenarios (controls) | Fraud scenarios |
|---|---|---|
| **PAYMENT** | `PAY-L1` routine small retail; `PAY-L2` recurring saved merchant; `PAY-L3` **legit first-time high-value purchase** (unusual but legal) | `PAY-F1` account-takeover payment to an atypical merchant after credential change; `PAY-F2` rapid payment burst following dormancy |
| **CASH_IN** | `CIN-L1` periodic salary/agent top-up; `CIN-L2` **legit cluster of large deposits** (e.g. business receipts) | `CIN-F1` structuring: many sub-threshold deposits to one account; `CIN-F2` funnel-in to a mule immediately before drain (chain head) |
| **CASH_OUT** | `COUT-L1` scheduled ATM/agent withdrawal within pattern; `COUT-L2` legitimate large cash-out with matching prior balance build-up | `COUT-F1` full-balance drain to zero; `COUT-F2` rapid cash-out right after inbound deposit (layering); `COUT-F3` many cash-outs converging on one agent/mule |
| **TRANSFER** | `TRF-L1` P2P to long-standing beneficiary; `TRF-L2` **legit first transfer to a new beneficiary** with steady balance | `TRF-F1` first transfer to brand-new beneficiary then immediate cash-out (chain); `TRF-F2` high-value balance-drain transfer; `TRF-F3` transfer-velocity spike in a short window |
| **DEBIT** | `DEB-L1` subscription/auto-debit recurring; `DEB-L2` legitimate utility debit with varying amount | `DEB-F1` unauthorized recurring debit post credential theft; `DEB-F2` anomalous merchant debit inconsistent with history |

Coverage floors (config): every fraud scenario must produce ≥ a minimum count per scenario and
appear across **multiple time bands** so no scenario is a time-confounded shortcut. Chain scenarios
(`CIN-F2`, `TRF-F1`, `COUT-F2`) share a `chain_id` and are labelled consistently end-to-end.

---

## 6. Account-history & transaction-chain design

* **Repeated, stable accounts (L2/L4).** A fixed population of origin/destination accounts, each
  participating in many transactions over time; ids persist and recur (unlike PaySim's ~unique origins).
* **Chronological sequences.** Emission ordered by `(step, event_ts)`; per-account history is a real time series.
* **Velocity & historical-amount features.** Built by the **strictly-prior causal pass**: for each row,
  aggregates use only that key's records **strictly earlier** in time (window definitions in §4.1). This
  reproduces the semantics validated in the earlier India Benchmark V1 research and never touches the current row's own outcome.
* **Consistent balances (L3).** The AccountRegistry ledger updates balances transaction-by-transaction so
  `newbalance = oldbalance ± amount` **by construction** (with rounding tolerance recorded).
* **Linked chains.** `ChainBuilder` emits multi-step graphs (fan-in/fan-out, layering) under one `chain_id`;
  the chain has a single label and a shared story (used by the chain-safe split in §9).
* **Legit vs suspicious behavioural variation.** Both fraud and legitimate accounts exercise overlapping
  "unusual" motifs so that history features are informative but not deterministic oracles.

---

## 6A. Temporal semantics — `step` vs `event_ts`

This section records the exact temporal meaning of each time field so evaluators can build a
leakage-safe chronological scheme without inventing information that the source does not contain.

**What `step` represents.** In the original PaySim CSV, `step` is a **day-granularity simulation index**
(integer `1`–`743`, one unit per simulated day), *not* a wall-clock date and *not* a sub-day time. Rows
are non-decreasing in `step`; there is **no intra-day timestamp** in the source. Generated rows reuse the
**same `step` semantics** — an integer day drawn from `[step_start, step_end]` (`1`–`743`) — so `step` is a
shared, comparable key across both sources.

**How generated `event_ts` is derived.** For generated rows only, an `event_ts` string is computed as a
**synthetic reference clock**:

```
event_ts = EPOCH + (step - 1) days + sec seconds,  EPOCH = 2017-01-01 00:00:00
```

`EPOCH` is **arbitrary** and carries no real-calendar meaning; it exists purely to give a deterministic
sub-day ordering handle. `sec` is drawn uniformly from `[0, 86400)` per row when
`substep_resolution = "second"` (0 otherwise). `event_ts` is formatted `"%Y-%m-%d %H:%M:%S"`.
**Original rows keep `event_ts = ""` (empty) — no timestamp is ever fabricated for them.**

**How events are ordered.** Generated emission and ledger replay use the deterministic total order
`(step, sec, record_uid)`. Within a fraud chain the head precedes the drain (`sec = 100 + pos*600`,
in-precedes-out in the same day). The row order written to CSV is this sorted order, so a fixed
seed/config reproduces the sequence byte-for-byte.

**Can originals + generated share a valid chronological evaluation scheme?** **Yes, at day granularity.**
Both sources carry `step`, so chronological train/val/test splits defined on **complete `step` boundaries**
(§9.1) are valid over the combined dataset — no step straddles two folds. Sub-day ordering is available
**only for generated rows**; originals cannot be ordered within a day relative to generated rows because
they carry no intra-day time. Therefore any decision instant that mixes the two must be expressed on the
coarsest common key — the day (`step`) — and sub-day velocity features must not be expected of originals.

**Which temporal assumptions remain synthetic (must not be read as real):**
* The `2017-01-01` epoch and the resulting `event_ts` dates are **not real transaction times**; they are an
  ordering device only.
* Generated intra-day `sec` is a **uniform draw**, not a modelled arrival/inter-transaction process.
* Generated `step` is drawn **uniformly across `1`–`743`**, whereas the original volume is **front-loaded**
  (steps ~1–322 ≈ 70% of rows) and its fraud rate is **back-loaded** (≈0.08% early → ≈0.42% late). The
  generated data therefore does **not** reproduce the original's temporal volume/prevalence shift; the
  original's shift is retained in the original-derived rows.
* Day-granularity of the original **cannot be retroactively refined** (A2); fine intra-day behaviour is a
  generated-only capability.

No historical/velocity feature builder or model is implemented here; this is a semantics record for the
M4/M6 temporal protocol.

---

## 6B. Streaming, memory & reproducibility guarantee

The full-scale path writes CSV in a **single streaming pass**: generated rows are produced by the emitter
and originals are streamed via `origindata.iter_source_records`, both fed as one iterator of
`(transaction_row, provenance_row)` pairs to `_stream_transactions_and_provenance`, which buffers **at
most one row** and publishes each file atomically (write `*.tmp` then `os.replace`). The whole
multi-million-row dataset is never materialised as a list.

**Exact reproducibility guarantee.** For a **fixed `master_seed` + `config_version` + `generator_version`**,
the emitted CSV is **byte-identical**. This holds because:
* Randomness derives from `rng.seed_for(label, master_seed)` and NumPy `default_rng` (PCG64) labelled
  streams, which are reproducible across platforms for a given seed.
* Row sequence is a **deterministic total order** on `(step, sec, record_uid)`, independent of write
  batching.
* Serialisation is fixed: UTF-8, `\n` line terminator (no CRLF), `csv.DictWriter` with a pinned column
  order, and generated money formatted to 2 decimals. Original-derived values are copied **verbatim as
  text** (no float coercion, no re-formatting), so they reproduce exactly from the immutable source.
* **Chunk size does not affect output bytes.** `chunksize` only bounds the read/write buffer; because the
  ordering and serialisation above are chunk-independent, varying `chunksize` produces identical bytes
  (asserted by the M3 test suite). It is therefore a **performance** knob, not a reproducibility one.

**Memory boundary (documented M5 work).** Originals are fully streamed (one pandas chunk resident). The
emitter currently materialises its generated slice in memory, bounded by `generated_rows` (~2 M); a
sharded / external-sort generated replay is a deferred M5 optimisation and is **not** required for
correctness or reproducibility — only to lower peak memory further.

---

## 7. Feature policies (two, never combined)

### A. Pre-transaction risk scoring  *(score **before** the transfer completes)*
* **Include:** `type`, `amount`, `oldbalanceOrg`, `step`/`event_ts`-derived calendar features, and strictly-prior
  history/velocity features (§4.1) computed from records earlier than the decision instant.
* **Exclude (unavailable pre-execution / leakage):** `isFraud` (target), `isFlaggedFraud` (oracle flag),
  `newbalanceOrig`, `newbalanceDest` (post-event), `oldbalanceDest`/destination-side state that is not known
  pre-execution, and `nameOrig`/`nameDest` raw ids (high-cardinality; use only aggregated history).
* **Document** the availability timestamp of every included feature (= the decision instant).

### B. Post-transaction investigation  *(retrospective / analyst-assisted)*
* **Permit** post-event fields (`newbalanceOrig`, `newbalanceDest`, `oldbalanceDest`, `isFlaggedFraud`) **only**
  when genuinely observable at the defined investigation time, and only for investigation/analytics — not for
  the pre-transaction model.
* **Guard against leakage:** historical aggregates must still exclude **future** records and **future** labels
  relative to the investigation timestamp; the investigation timestamp is recorded per feature.
* These two policies are **materialized as separate feature matrices**; they are never concatenated into one
  model matrix (prevents a post-event field silently entering the deployed risk model).

---

## 8. Class-distribution strategy

* **Original-derived records:** read from the immutable CSV and carried into the enhanced dataset with
  their labels **unchanged** (8,213 fraud / 0.129%, fraud confined to TRANSFER+CASH_OUT). They are a
  **read-only source**, not a separate benchmark; their type-concentration is offset by generated fraud in
  the other three types.
* **Generated dataset:** **configurable** per-type and per-scenario prevalence. Recommend a
  **moderate, documented** target (not equal 50/50): a plausible-for-simulation fraud rate that still
  leaves a hard imbalance so evaluation stays honest, with **minimum per-scenario counts** to guarantee
  coverage of every fraud type across all five transaction types.
* **Honesty constraints:** validation and test distributions must reflect the generated base rate — **no
  resampling of val/test**. Any oversampling/undersampling/SMOTE is a **training-only** experiment, logged
  separately, and never applied to the untouched final test.
* **No accuracy-target tuning (rule 6):** prevalence/scale are chosen for **scientific coverage** (does
  generalization across the newly-labelled types hold), not to hit a number.

---

## 9. Evaluation & leakage-prevention strategy

**Operational role:** the enhanced dataset (original-derived + generated, distinguished only by provenance)
is the **only** dataset used to build train/validation/test folds and to run inference development. The
original PaySim CSV is read-only input to it, never a held-out benchmark.

**Approved data workflow:** (1) read the original CSV without modifying it → (2) audit and transform
original-derived records where appropriate → (3) generate additional synthetic legitimate + fraudulent
transactions → (4) combine the approved original-derived and generated records into the enhanced dataset
(provenance-tagged) → (5) validate the resulting dataset (§10) → (6) build leakage-safe features and
chronological train/validation/test splits from the enhanced dataset → (7) use the enhanced dataset
throughout the operational ML pipeline.

1. **Chronological splits on complete `step` boundaries** (no step straddles two folds). Measured feasibility
   on the *original* distribution: earliest band (steps 1–~322) → train (fraud present), mid band → validation
   (fraud present), latest band (≈steps 378–743) → **test with ≈4,008 fraud** — every fold is fraud-bearing
   despite back-loaded fraud.
2. **Unseen-destination-account evaluation.** Because generated origins now recur, a genuine held-out axis
   exists: report a protocol on **destinations/accounts unseen during training** (group by account/`nameDest`),
   in addition to the time axis. (Combined time+account protocol mirrors the preserved `experiment_3` methodology,
   but re-implemented fresh under `ml/`.)
3. **Chain-safe partitioning (L4 leakage).** Splits must place an **entire `chain_id`** (and any connected
   account component) in a **single partition**, so a fraud chain cannot leak equivalent examples across train
   /val/test. Assert zero chain/connected-component overlap between partitions.
4. **Validation-only threshold.** Select the operating threshold on validation only (max-F1 / precision-constrained),
   applied **unchanged** to test; never derived from test labels.
5. **Metrics.** PR-AUC (primary), precision, recall, F1, FP, FN, ROC-AUC, per-transaction-type metrics, and
   **per-fraud-scenario recall** (so coverage of the newly-added fraud types is provable). Confusion matrices
   at the chosen threshold; report the train→test prevalence shift.
6. **Enhanced-only folds; diagnostic only.** Because the enhanced dataset is the sole operational dataset,
   every train/val/test fold is derived from it (chronological, chain-safe). As an **optional diagnostic**
   (never the operational protocol), a model may be compared trained-on-original-derived vs
   trained-on-enhanced against the **same held-out enhanced test fold** to show whether the added scenarios
   and types help generalization. The original CSV is not an independent test target.
7. **Shortcut/leakage checks** (run each evaluation): per-feature AUC ceiling to detect ≥0.95 single-feature
   "too-easy" leaks; the §4.3 generated-vs-original discriminator; explicit strictly-prior audit that no feature
   uses future info; verify label is not recoverable from excluded fields.
8. **Held-out final test** used exactly once; no feature selection, thresholding, or tuning touches it.

**Claims the data cannot support:** any real-world banking effectiveness; fine-grained intra-day velocity on the
original (day-granularity only); fraud patterns beyond the simulated scenario library.

---

## 10. Data-quality validation checklist (hard gates unless noted)

Original and generated data are audited **separately**; unusual *original* transactions are **never** discarded
for failing a synthetic rule (rule: audit ≠ auto-drop).

1. Missing values — count per column; originals verified 0; generated expected 0 except documented nulls.
2. Duplicate transactions — exact-duplicate check (originals: 0); generated must be 0 by `record_uid`.
3. Invalid transaction types — only the 5 allowed values.
4. Invalid/inconsistent labels — `isFraud ∈ {0,1}`; `isFlaggedFraud` present only for original rows.
5. Negative/invalid amounts — none (originals verified 0 negatives); flag pathological outliers for audit, don't silently drop.
6. Balance reconciliation — generated rows must satisfy the ledger identity within tolerance (hard gate for generated); original failures are **documented, not corrected** (immutable).
7. Temporal ordering — `step` (and `event_ts`) well-defined and non-decreasing where relevant.
8. Account identifier consistency — id format/entropy matches PaySim; generated ids are stable/reusable.
9. Fraud coverage by transaction type — generated fraud must appear in **all five** types (hard gate that proves L1 addressed); original remains TRANSFER/CASH_OUT-only (documented).
10. Scenario coverage — every `scenario_id` meets its configured minimum count and time-band spread.
11. Source provenance — every record has `record_uid` + resolvable provenance row; features table carries no provenance columns.
12. Class distribution — matches config target within tolerance; val/test not resampled.
13. Feature availability — every feature maps to a declared prediction/investigation timestamp (§7).
14. Future-information leakage — strictly-prior features recomputed on a shuffled/future-blinded copy must be unchanged; any deviation = fail.
15. Generation-rule violations — generated rows contradicting their scenario/ledger definitions are quarantined for review.
16. Anti-shortcut discriminator (§4.3) — generated-vs-original AUC from features only must be ≈0.5 (soft gate; large gap = fix before promotion).

---

## 11. Proposed file structure & milestones

```text
ml/
├── data/
│   ├── raw/                    # original PaySim (immutable, read-only) — DO NOT TOUCH
│   └── processed/
│       ├── enhanced/           # features_*.parquet + provenance_*.parquet + run manifests
│       │   └── MANIFEST.md     # seed, config snapshot, versions, checksums, counts
│       └── qc/                 # audit/validation outputs (leakage + DQ reports)
├── src/
│   ├── data/                   # loaders + original-data validator (read-only)
│   ├── generator/              # config, accounts, scenarios, emitter, chains, features, provenance, cli
│   │   └── configs/            # versioned *.yaml scenario/volume configs
│   ├── features/               # feature-policy builders (pre-transaction / investigation)
│   ├── training/               # (later) model fitting
│   ├── evaluation/             # (later) splits, thresholds, metrics, leakage checks
│   └── inference/              # risk-scoring helpers (still NOT wired to backend)
├── tests/                      # generator determinism, chain-safety, leakage, DQ gates
├── artifacts/                  # trained models (later)
└── reports/                    # THIS spec + future reports
```

Milestones:
* **M0 ✅** Spec approved; **enhanced dataset confirmed as the sole operational ML dataset**.
* **M1 ✅ implemented** — read-only chunked PaySim loader + schema/checksum/label/type profiler (`src/data/origindata.py`); never writes to the source.
* **M2 ✅ implemented** — generator **skeleton**: config validation, deterministic seed handling, schema, account-registry ledger, scenario/provenance/chains/emitter interfaces, validation harness; tests for determinism, schema, provenance and source preservation. **No dataset generated.**
* **M3 ✅ implemented** — CSV-only deterministic emitter + linked chains across all 5 types, account registry, chronological ledger replay, §10 dataset gates, chunked CSV writing, provenance sidecar + JSON manifest, `generate-pilot` CLI; M1–M2 skeletons replaced by real code; a validated ~20k-record pilot (seed 42, realized fraud ~3.0%) is produced. **No full-scale generation, no training, no final feature/split build.**
* **M4** Strictly-prior feature builder + the two separate feature policies; leakage/audit gates green. *(Blocked until feature-availability rules are reviewed.)*
* **M5** Build + validate the full enhanced dataset (features + provenance tables, anti-shortcut discriminator, full §10 pass).
* **M6** Evaluation harness on the **enhanced dataset only** (chronological + unseen-destination + chain-safe splits, validation-only threshold, per-type/per-scenario metrics; optional original-derived-vs-enhanced diagnostic). *(Model training happens only from here on, in a later, separate task.)*

---

## 12. Risks, assumptions, unresolved questions

* **A1** Fraud scenarios are **assumptions**, not validated typologies; conclusions are "the model can learn
  fraud in all five types", not "real fraud is like this".
* **A2** Adding sub-step `event_ts` improves temporal resolution for generated data but cannot retroactively
  add it to the original (day-granularity stays).
* **A3** Reproducibility requires pinning config+seed+generator version; changing any ⇒ new `dataset_version`.
* **R1 (operational risk, needs decision)** — `.gitignore` currently does **not** ignore `ml/data/raw/*.csv`:
  the **493 MB** raw PaySim CSV is presently trackable and could be accidentally committed; likewise large
  generated outputs under `data/processed/`. A narrow ignore rule is likely needed (deliberately **not** done
  in this spec-only task).
* **R2** If generated data is mixed with original for training, histories must be computed consistently; mixing
  must always carry `source_dataset` provenance (rule 8) — never silently.
* **R3** Over-balancing classes is explicitly rejected (rules 5/6); the temptation to tune prevalence to lift
  headline metrics must be governed by the M6 comparison being coverage-driven, not accuracy-driven.
* **Q1** Official PaySim checksum/licence still unconfirmed (L8) — verification may require an authorized re-download.

---

## 13. Proposed defaults (configurable; coverage-driven, not score-driven)

Sensible **starting defaults** for the generator configuration. Every value stays configurable and **none is
chosen to reach a model-score target** (rules 5/6). Values still requiring sign-off before the full run are
flagged ⚠ (see §14).

| Setting | Proposed default | Rationale / notes |
|---|---|---|
| Generated row count | ~2,000,000 | same order as the original; ample per-scenario coverage |
| Overall generated fraud rate | ~3% | deliberately **still imbalanced** — not equal-balanced; pilot realized 3.0% |
| Fraud rate **by type** (generated) | TRANSFER 0.06, CASH_OUT 0.05, DEBIT 0.03, PAYMENT 0.01, CASH_IN 0.01 | guarantees fraud in **all five** types (fixes L1); CASH_OUT/TRANSFER elevated to mirror where PaySim fraud concentrates; type weights {PAY .24, CIN .24, COUT .22, TRF .18, DEB .12} make the weighted rate land on ~3% |
| Min count per fraud scenario | 200 | coverage floor, spread over ≥2 time bands |
| Account population | 200,000 origin + 80,000 destination | origins recur → real histories (fixes L2); ids reused in chains |
| Time granularity | `step` (day) = primary split key; `event_ts` at **second** resolution for generated intra-step order | original rows keep day granularity only |
| Output format | **CSV only** — `enhanced_transactions.csv` + `provenance.csv` in **separate** files (+ `manifest.json` metadata) | approved decision: no Parquet; features never contain provenance |
| Chain-safe split rule | partition by connected component over `chain_id ∪ nameOrig ∪ nameDest`; assert zero cross-fold overlap | blocks L4 chain leakage |
| Versioning | `generator_version=0.1.0`, `config_version=cfg-default-v1`, `dataset_version=enhanced-v1`, `generation_run_id=sha256(seed, config_version)[:16]` | deterministic; no wall-clock in ids |
| Master seed | `42` (approved) | per-component seeds derived via `rng.py` |
| Ledger balance tolerance | ±0.01 | generated `newbalance = oldbalance ± amount` must hold within this |

---

## 14. Decisions status after M3

**Approved (locked by the M3 sign-off):** output format is **CSV-only** (no Parquet); master seed **42**;
generated scale target ~**2,000,000** rows; overall generated fraud rate ~**3%** with the configurable
per-type split in §13; original TRANSFER/CASH_OUT fraud rows are folded in with labels **unchanged**;
`isFlaggedFraud` stays out of the initial predictive feature set; `chain_id ∪ nameOrig ∪ nameDest` is the
chain-safe split key; `event_ts` uses second-resolution intra-step ordering for generated rows only.

**Still to sign off before full (≈2 M) generation:**
1. **Pilot → full-scale go-ahead** — confirm the validated pilot (this milestone) is acceptable to scale up.
2. **`.gitignore`** — the 493 MB raw CSV and `data/processed/` outputs are currently **untracked but not
   ignored** (R1); a narrow ignore rule is recommended before any large write (**not** changed here).
3. **Final derived-feature list** (§4.1) and the two feature policies — deferred to **M4**, blocked until the
   feature-availability review confirms no future-information leakage.

**Resolved by earlier approved decisions:** the former "supplement vs independent benchmark" question is
settled — the **enhanced dataset is the sole operational dataset**; the original CSV is a read-only source.
