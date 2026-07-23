"""
toml_merger.py

Provides AST-preserving edits to a live TOML document using tomlkit.
Supports adding, editing, and removing individual stanzas inside
the ``override-records`` Array of Tables without disturbing comments
or formatting of unrelated entries.
"""

import logging
from typing import Any, Dict

import tomlkit

logger = logging.getLogger(__name__)


def merge_intent_into_toml(live_toml_str: str, intent: Dict[str, Any]) -> str:
    """Apply a single intent operation to a live TOML string.

    Parses *live_toml_str* with tomlkit to preserve all comments and
    formatting, performs the requested action, then serialises the
    document back to a string.

    Args:
        live_toml_str: The current contents of ``override.toml`` as a string.
        intent: A dictionary produced by the entity extractor containing at
            minimum the keys ``action``, ``scope_key``, ``scope_value``,
            ``directive``, and ``directive_value``.

    Returns:
        The modified TOML document as a string.

    Raises:
        ValueError: If ``action`` is ``"edit"`` or ``"remove"`` and no
            matching stanza is found, or if ``action`` is unknown.
    """
    doc = tomlkit.parse(live_toml_str)

    if "override-records" not in doc:
        doc.add("override-records", tomlkit.aot())

    action: str = intent.get("action", "add")
    scope_key: str = intent["scope_key"]
    scope_value: Any = intent["scope_value"]
    directive: str = intent["directive"]
    directive_value: Any = intent["directive_value"]

    if action == "add":
        new_table = tomlkit.table()
        new_table.add(scope_key, scope_value)
        new_table.add(directive, directive_value)
        doc["override-records"].append(new_table)

    elif action in ("edit", "remove"):
        records = doc["override-records"]
        match_index: int | None = None

        for idx, table in enumerate(records):
            if table.get(scope_key) == scope_value and directive in table:
                match_index = idx
                break

        if match_index is None:
            msg = (
                f"No stanza found with {scope_key}={scope_value!r} "
                f"and directive '{directive}' for action '{action}'."
            )
            logger.warning(msg)
            raise ValueError(msg)

        if action == "edit":
            doc["override-records"][match_index][directive] = directive_value
        else:  # remove
            # Build a new AOT that excludes the matched index; tomlkit does
            # not support in-place deletion from an Array of Tables.
            new_aot = tomlkit.aot()
            for idx, table in enumerate(records):
                if idx != match_index:
                    new_aot.append(table)
            doc["override-records"] = new_aot

    else:
        raise ValueError(
            f"Unknown action '{action}'. Must be one of: 'add', 'edit', 'remove'."
        )

    return doc.as_string()
