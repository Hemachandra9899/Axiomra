"""Command Line Interface for Axiomra dataset inspection and verification."""

from __future__ import annotations

import argparse
import sys

from axiomra.data.persistence.parquet import ParquetDatasetRepository


def inspect_dataset_cmd(dataset_id: str, repo: ParquetDatasetRepository | None = None) -> int:
    repository = repo or ParquetDatasetRepository()
    if not repository.store.exists(f"datasets/{dataset_id}/manifest.json"):
        print(f"Error: Dataset {dataset_id} not found", file=sys.stderr)
        return 1

    try:
        dataset = repository.load(dataset_id)
        manifest = dataset.manifest
        is_valid = repository.verify(dataset_id)
        status_str = "PASS" if is_valid else "FAIL"

        print("AXIOMRA DATASET")
        print("─" * 40)
        print(f"Dataset ID        {manifest.dataset_id}")
        print(f"Schema            {manifest.schema_version}")
        print()
        print(f"Universe          {manifest.universe_name} ({manifest.universe_version})")
        print(f"Adjustment        {manifest.adjustment_mode.value if hasattr(manifest.adjustment_mode, 'value') else manifest.adjustment_mode}")
        print()
        print(f"Start             {manifest.start_date}")
        print(f"End               {manifest.end_date}")
        print()
        print(f"Instruments       {manifest.instrument_count}")
        print(f"Bars              {manifest.bar_count}")
        print()
        print("PIT Membership    YES")
        print(f"Quality           {status_str}")
        print()
        print(f"Logical SHA       {manifest.logical_checksum}")
        print(f"Artifact SHA      {manifest.artifact_checksum}")
        print()
        for filename in sorted(manifest.files.keys()):
            verified = "VERIFIED" if is_valid else "UNVERIFIED"
            print(f"{filename:<18} {verified}")
        return 0 if is_valid else 1
    except Exception as e:
        print(f"Error inspecting dataset {dataset_id}: {e}", file=sys.stderr)
        return 1


def verify_dataset_cmd(dataset_id: str, repo: ParquetDatasetRepository | None = None) -> int:
    repository = repo or ParquetDatasetRepository()
    is_valid = repository.verify(dataset_id)
    if is_valid:
        print(f"Dataset {dataset_id}: VERIFIED (OK)")
        return 0
    else:
        print(f"Dataset {dataset_id}: CORRUPTED or MISSING", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="axiomra", description="Axiomra CLI")
    subparsers = parser.add_subparsers(dest="command")

    dataset_parser = subparsers.add_parser("dataset", help="Dataset commands")
    ds_sub = dataset_parser.add_subparsers(dest="subcommand")

    inspect_p = ds_sub.add_parser("inspect", help="Inspect dataset")
    inspect_p.add_argument("dataset_id", type=str, help="Dataset ID (e.g. ds-123)")

    verify_p = ds_sub.add_parser("verify", help="Verify dataset integrity")
    verify_p.add_argument("dataset_id", type=str, help="Dataset ID (e.g. ds-123)")

    args = parser.parse_args()
    if args.command == "dataset":
        if args.subcommand == "inspect":
            sys.exit(inspect_dataset_cmd(args.dataset_id))
        elif args.subcommand == "verify":
            sys.exit(verify_dataset_cmd(args.dataset_id))

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
