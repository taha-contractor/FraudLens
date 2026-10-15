"""Operator entrypoints (M1-M3).

Subcommands:
  profile-source    read-only profile of the original PaySim CSV (M1)
  validate-config   validate the default generator config (M2)
  static-checks     run the skeleton static checks (M2)
  generate-pilot    write a small CSV-only pilot enhanced dataset + gates (M3)
  generate-full     stream the FULL enhanced dataset (all originals + synthetic).
                    DRY-RUN by default; writes only with --confirm-full (M5 gate).
"""

from __future__ import annotations

import argparse
import json
import os

from .config import default_config
from .validate import ValidationHarness


def cmd_validate_config(_args) -> int:
    cfg = default_config()
    print(json.dumps({"ok": True, "config_version": cfg.config_version,
                      "generator_version": cfg.generator_version,
                      "generation_run_id": cfg.generation_run_id()}, indent=2, sort_keys=True))
    return 0


def cmd_static_checks(_args) -> int:
    issues = ValidationHarness().run_static_checks()
    print(json.dumps({"ok": not issues, "issues": issues}, indent=2, sort_keys=True))
    return 0 if not issues else 1


def cmd_profile_source(args) -> int:
    from data import origindata  # local import; requires ml/src on sys.path
    profile = origindata.profile_source(args.path, chunksize=args.chunksize,
                                        verify_checksum=not args.no_checksum)
    profile["coherence_issues"] = origindata._coherence_checks(profile)
    print(json.dumps(profile, indent=2, sort_keys=True))
    return 0


def cmd_generate_pilot(args) -> int:
    from .pipeline import generate_pilot
    summary = generate_pilot(args.out_dir, n_generated=args.n_generated,
                             n_original=args.n_original)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def cmd_generate_full(args) -> int:
    from .config import default_config
    from .pipeline import generate_enhanced_dataset
    cfg = default_config()
    plan = {
        "mode": "full", "include_original": "all",
        "generated_rows": cfg.generated_rows, "master_seed": cfg.master_seed,
        "expected_generated_fraud_rate": round(
            sum(cfg.type_weights[t] * cfg.fraud_rate_by_type[t] for t in cfg.type_weights)
            / sum(cfg.type_weights.values()), 5),
        "original_rows": 6_362_620,
        "would_write": bool(args.confirm_full),
    }
    if not args.confirm_full:
        plan["note"] = "dry-run: nothing generated (re-run with --confirm-full to write)"
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    summary = generate_enhanced_dataset(args.out_dir, cfg, include_original="all")
    print(json.dumps({"plan": plan, "result": summary["counts"]}, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FraudLens enhanced-dataset pipeline (M1-M3).")
    sub = p.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("validate-config"); pc.set_defaults(func=cmd_validate_config)
    sc = sub.add_parser("static-checks"); sc.set_defaults(func=cmd_static_checks)

    gp = sub.add_parser("generate-pilot")
    gp.add_argument("--out-dir", default=os.path.join("ml", "data", "processed", "enhanced"))
    gp.add_argument("--n-generated", type=int, default=20_000, dest="n_generated")
    gp.add_argument("--n-original", type=int, default=2000, dest="n_original")
    gp.set_defaults(func=cmd_generate_pilot)

    gf = sub.add_parser("generate-full")
    gf.add_argument("--out-dir", default=os.path.join("ml", "data", "processed", "enhanced_full"))
    gf.add_argument("--confirm-full", action="store_true",
                    help="required to actually write the multi-million-row dataset")
    gf.set_defaults(func=cmd_generate_full)

    pp = sub.add_parser("profile-source")
    pp.add_argument("--path", default=None)
    pp.add_argument("--chunksize", type=int, default=500_000)
    pp.add_argument("--no-checksum", action="store_true")
    pp.set_defaults(func=cmd_profile_source)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
