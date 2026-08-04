import logging
import os


LEROY_MINIMAL_QUOTA_DIFF_PCT = float(os.environ.get("LEROY_MINIMAL_QUOTA_DIFF_PCT", 5.0))
logger = logging.getLogger(__name__)


def filter_csv_diff(diff_text: str) -> dict:
    result = {
        "added": [],
        "removed": [],
        "modified": [],
    }

    added_lines = {}
    removed_lines = {}

    for raw_line in diff_text.splitlines():
        line = raw_line.rstrip("\n")
        if not line or line.startswith("---") or line.startswith("+++") or line.startswith("@@"):
            continue

        if line.startswith("-") and not line.startswith("---"):
            payload = line[1:].strip()
            parts = [part.strip() for part in payload.split(",")]
            if len(parts) < 2:
                continue
            key = (parts[0], parts[1])
            removed_lines[key] = parts[2:]
        elif line.startswith("+") and not line.startswith("+++"):
            payload = line[1:].strip()
            parts = [part.strip() for part in payload.split(",")]
            if len(parts) < 2:
                continue
            key = (parts[0], parts[1])
            added_lines[key] = parts[2:]

    for key, new_values in added_lines.items():
        if key not in removed_lines:
            result["added"].append({"key": key, "values": new_values})

    for key, old_values in removed_lines.items():
        if key not in added_lines:
            result["removed"].append({"key": key, "values": old_values})

    shared_keys = set(added_lines).intersection(removed_lines)
    for key in shared_keys:
        old_values = removed_lines[key]
        new_values = added_lines[key]

        is_significant_change = False
        for old_value, new_value in zip(old_values, new_values):
            try:
                old_num = float(old_value)
                new_num = float(new_value)
            except (TypeError, ValueError):
                continue

            pct_change = abs(new_num - old_num) / max(old_num, 1e-9) * 100
            if pct_change > LEROY_MINIMAL_QUOTA_DIFF_PCT:
                is_significant_change = True
                break

        if is_significant_change:
            result["modified"].append(
                {
                    "key": key,
                    "before": old_values,
                    "after": new_values,
                }
            )

    logger.debug(
        "Filtered CSV diff (added=%d, removed=%d, modified=%d, threshold_pct=%.2f)",
        len(result["added"]),
        len(result["removed"]),
        len(result["modified"]),
        LEROY_MINIMAL_QUOTA_DIFF_PCT,
    )
    return result


def process_all_diffs(raw_diffs_dict: dict) -> dict:
    filtered = {}

    for filename, file_payload in raw_diffs_dict.items():
        if not isinstance(file_payload, dict):
            continue

        diff_text = file_payload.get("diff", "")
        filtered[filename] = filter_csv_diff(diff_text)

    logger.info("Processed CSV diffs for %d file(s)", len(filtered))
    return filtered
