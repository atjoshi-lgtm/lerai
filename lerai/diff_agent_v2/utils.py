"""Pure data-transformation utilities for diff_agent_v2."""

from __future__ import annotations

import csv
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

QUOTA_THRESHOLD = 0.2
logger = logging.getLogger(__name__)


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
    logger.info("Read BLC data from %s (regions=%d)", file_path, len(data))
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
    logger.info("Read FCS data from %s (regions=%d)", file_path, len(data))
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

    logger.info(
        "Built diffs for %s (structure=%d, quota=%d, threshold=%s)",
        file_type,
        len(structure_rows),
        len(quota_rows),
        threshold,
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


def load_map_translations(data_dir: Path) -> dict[str, str]:
    """Load maprule-id to shortname translations from lerai data CSV."""
    map_dict: dict[str, str] = {}
    map_file_path = data_dir / "mapruleid_mapname.csv"

    with map_file_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized_row = {
                str(k).strip().lstrip("\ufeff"): (str(v).strip() if v is not None else "")
                for k, v in row.items()
                if k is not None
            }
            mapruleid = normalized_row.get("mapruleid", "")
            shortname = normalized_row.get("shortname", "")
            if not mapruleid:
                continue

            key = f"mr-{mapruleid}"
            map_dict[key] = shortname

    logger.info("Loaded map translations from %s (count=%d)", map_file_path, len(map_dict))
    return map_dict


def _normalize_map_lookup_id(raw_id: str) -> str:
    """Normalize diff identifiers to maprule keys used by mapruleid_mapname.csv."""
    candidate = raw_id.strip()
    if not candidate:
        return ""

    if ":" in candidate:
        candidate = candidate.split(":", 1)[0].strip()

    if candidate.isdigit():
        return f"mr-{candidate}"

    return candidate


def translate_diff_maps(diff_list: list[dict], map_dict: dict[str, str], id_key: str) -> None:
    """Add map_name to each diff row based on the ID field provided by id_key."""
    for row in diff_list:
        raw_id = str(row.get(id_key, "")).strip()
        normalized_id = _normalize_map_lookup_id(raw_id)
        row["map_name"] = map_dict.get(normalized_id, "Unknown")

    logger.info("Translated map names for %d diff row(s) using key=%s", len(diff_list), id_key)


def load_geography_mapping(data_dir: Path) -> dict[str, dict[str, str]]:
    """Build region -> {metro, country, geo} mapping from geography CSVs."""
    geo_country_path = data_dir / "geo_country.csv"
    country_metro_path = data_dir / "country_metro.csv"
    metro_region_path = data_dir / "metro_region.csv"

    country_to_geo: dict[str, str] = {}
    with geo_country_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            country = str(row.get("country", "")).strip()
            geo = str(row.get("geo", "")).strip()
            if country:
                country_to_geo[country] = geo

    metro_to_country: dict[str, str] = {}
    with country_metro_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            metro = str(row.get("metro_area", "")).strip()
            country = str(row.get("country", "")).strip()
            if metro:
                metro_to_country[metro] = country

    region_to_hierarchy: dict[str, dict[str, str]] = {}
    with metro_region_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_region = str(row.get("region", "")).strip()
            region = raw_region.removeprefix("region-")
            if not region:
                continue

            metro = str(row.get("metro_area", "")).strip()
            country = metro_to_country.get(metro, "")
            geo = country_to_geo.get(country, "")
            region_to_hierarchy[region] = {
                "metro": metro,
                "country": country,
                "geo": geo,
            }

    logger.info(
        "Loaded geography mapping (regions=%d, metros=%d, countries=%d)",
        len(region_to_hierarchy),
        len(metro_to_country),
        len(country_to_geo),
    )
    return region_to_hierarchy


def inject_geography(diff_list: list[dict], geo_dict: dict[str, dict[str, str]]) -> None:
    """Inject metro/country/geo fields into diff rows using region lookup."""
    for row in diff_list:
        raw_region = str(row.get("region", "")).strip()
        clean_region = raw_region.removeprefix("region-")
        hierarchy = geo_dict.get(clean_region)
        if hierarchy:
            row["metro"] = hierarchy.get("metro", "")
            row["country"] = hierarchy.get("country", "")
            row["geo"] = hierarchy.get("geo", "")
        else:
            row["metro"] = "Unknown"
            row["country"] = "Unknown"
            row["geo"] = "Unknown"

    logger.info("Injected geography fields for %d diff row(s)", len(diff_list))
