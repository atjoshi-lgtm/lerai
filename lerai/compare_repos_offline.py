"""Compare offline manual vs official repo CSVs (BLC + FCS).

Outputs:
- structure_diffs.csv: map additions/deletions for each region in BLC and FCS
- fcs_quota_alerts.csv: quota changes for common FCS maps by region
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple

QUOTA_THRESHOLD = 0.2


def looks_like_region(value: str) -> bool:
    return value.isdigit() or value.startswith("region-")


def read_blc(file_path: Path) -> Dict[str, Set[str]]:
    """Read BLC CSV -> Dict[region, Set[maprule]]."""
    data: Dict[str, Set[str]] = defaultdict(set)
    with file_path.open(newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 3:
                continue
            row = [c.strip() for c in row]
            region, maprule = row[1], row[2]
            if not region or not maprule:
                continue
            if not looks_like_region(region):
                continue
            data[region].add(maprule)
    return data


def read_fcs(file_path: Path) -> Dict[str, Dict[str, float]]:
    """Read FCS CSV -> Dict[region, Dict[identifier, quota]]."""
    data: Dict[str, Dict[str, float]] = defaultdict(dict)
    with file_path.open(newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or len(row) < 4:
                continue
            row = [c.strip() for c in row]
            identifier, region, quota_str = row[1], row[2], row[3]
            if not identifier or not region:
                continue
            if not region.startswith("region-"):
                continue
            try:
                quota = float(quota_str)
            except ValueError:
                continue
            data[region][identifier] = quota
    return data


def split_structure_and_quota_diffs(
    manual_regions: Dict[str, Set[str]] | Dict[str, Dict[str, float]],
    official_regions: Dict[str, Set[str]] | Dict[str, Dict[str, float]],
    file_type: str,
    threshold: float | None = None,
) -> Tuple[List[Dict[str, str]], List[Dict[str, float]]]:
    structure_rows: List[Dict[str, str]] = []
    quota_rows: List[Dict[str, float]] = []

    for region in sorted(set(manual_regions) | set(official_regions)):
        manual_items = manual_regions.get(region, {})
        official_items = official_regions.get(region, {})

        manual_keys = set(manual_items)
        official_keys = set(official_items)

        structure_rows.extend(
            build_structure_diffs(
                source_set=manual_keys,
                target_set=official_keys,
                region=region,
                file_type=file_type,
            )
        )

        if file_type == "fcs" and threshold is not None:
            quota_rows.extend(
                build_quota_diffs(
                    manual_map=manual_items,  # type: ignore[arg-type]
                    official_map=official_items,  # type: ignore[arg-type]
                    region=region,
                    threshold=threshold,
                )
            )

    return structure_rows, quota_rows


def build_structure_diffs(
    *,
    source_set: Set[str],
    target_set: Set[str],
    region: str,
    file_type: str,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for item in sorted(source_set - target_set):
        rows.append(
            {
                "file": file_type,
                "region": region,
                "type": "added",
                "item": item,
                "info": "Present in manual_offline, missing in official",
            }
        )
    for item in sorted(target_set - source_set):
        rows.append(
            {
                "file": file_type,
                "region": region,
                "type": "deleted",
                "item": item,
                "info": "Present in official, missing in manual_offline",
            }
        )
    return rows


def build_quota_diffs(
    *,
    manual_map: Dict[str, float],
    official_map: Dict[str, float],
    region: str,
    threshold: float,
) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for identifier in sorted(set(manual_map) & set(official_map)):
        q_man = manual_map[identifier]
        q_off = official_map[identifier]
        diff = abs(q_man - q_off)
        if diff > threshold:
            rows.append(
                {
                    "region": region,
                    "map_identifier": identifier,
                    "manual_quota": q_man,
                    "official_quota": q_off,
                    "diff": diff,
                }
            )
    return rows


def write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare offline manual vs official CSVs.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=QUOTA_THRESHOLD,
        help="Minimum absolute quota difference to report. Use 0 to report every change.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_dir = Path(__file__).parent
    manual_dir = base_dir / "manual_offline"
    official_dir = base_dir / "official"

    print("Comparing BLC files...")
    blc_manual = read_blc(manual_dir / "blc.csv")
    blc_official = read_blc(official_dir / "blc.csv")
    blc_diffs, _ = split_structure_and_quota_diffs(blc_manual, blc_official, "blc")

    print("Comparing FCS files...")
    fcs_manual = read_fcs(manual_dir / "fcs.csv")
    fcs_official = read_fcs(official_dir / "fcs.csv")
    fcs_diffs, quota_alerts = split_structure_and_quota_diffs(
        fcs_manual,
        fcs_official,
        "fcs",
        args.threshold,
    )

    diff_csv_path = base_dir / "structure_diffs.csv"
    quota_csv_path = base_dir / "fcs_quota_alerts.csv"
    write_csv(diff_csv_path, ["file", "region", "type", "item", "info"], blc_diffs + fcs_diffs)
    write_csv(
        quota_csv_path,
        ["region", "map_identifier", "manual_quota", "official_quota", "diff"],
        quota_alerts,
    )

    print("Done.")
    print(f"Found {len(blc_diffs)} structural differences in BLC.")
    print(f"Found {len(fcs_diffs)} structural differences in FCS.")
    comparator = ">" if args.threshold != 0 else ">="
    print(f"Found {len(quota_alerts)} quota changes ({comparator} {args.threshold}%).")
    print(f"Reports written to {diff_csv_path} and {quota_csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
