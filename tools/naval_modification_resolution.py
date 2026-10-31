"""Resolve pinned static declarations, never simulate installed or effective game parameters.

Common IDs and local scalar overrides are traceable declaration candidates.
Compound blocks remain separate: the engine's merge/activation semantics are not assumed.
"""

from __future__ import annotations

import re
from collections import Counter

from neko_warthunder.adapters.naval_instrument_fields import _finite
from neko_warthunder.adapters.naval_static_reference import CONFIGURATION_COUNTERS

_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")
_SCALARS = {
    "tier",
    "modClass",
    "invertEnableLogic",
    "deactivationIsAllowed",
    "prevModification",
    "reqModification",
    "modUpgradeType",
    "modOverdriveType",
}
_BLOCKS = (
    "effects",
    "disableModEffects",
    "upgradeEffect",
    "upgradeEffect_inverted",
    "overdriveEffect",
    "overdriveEffect_inverted",
)
_DIRECTIVES = {"include", "_include", "extends", "_extends", "inherit", "_use", "baseFile"}


def _metadata(key, value):
    if key in {"invertEnableLogic", "deactivationIsAllowed"}:
        return value if type(value) is bool else None
    if key == "tier":
        return value if type(value) is int and 0 <= value <= 100 else None
    if key in {"prevModification", "reqModification"}:
        values = value if isinstance(value, list) else [value]
        return (
            list(values)
            if len(values) <= 64 and all(isinstance(v, str) and _NAME.fullmatch(v) for v in values)
            else None
        )
    return value if isinstance(value, str) and _NAME.fullmatch(value) else None


def _atoms(block):
    """Keep scalar declarations and structure counts; never preserve arbitrary strings/containers."""
    if not isinstance(block, dict):
        return {"status": "invalid", "atoms": {}, "complex_blocks": 0, "uninterpreted_values": 1}
    atoms, complex_blocks, unknown = {}, 0, 0
    stack = [(block, (), 0)]
    while stack:
        item, prefix, depth = stack.pop()
        if depth > 12 or len(atoms) >= 2048:
            unknown += 1
            continue
        for key, value in sorted(item.items(), reverse=True):
            if len(atoms) >= 2048:
                unknown += 1
                continue
            if not isinstance(key, str) or not _NAME.fullmatch(key):
                unknown += 1
                continue
            path = prefix + (key,)
            if isinstance(value, dict):
                complex_blocks += 1
                stack.append((value, path, depth + 1))
            elif type(value) is bool or _finite(value):
                atoms["/".join(path)] = value
            else:
                # String references, repeated blocks and arrays need separate engine
                # interpretation. Counting them does not make them no-ops.
                unknown += 1
    return {
        "status": "declared",
        "atoms": dict(sorted(atoms.items())),
        "complex_blocks": complex_blocks,
        "uninterpreted_values": unknown,
    }


def _directive_count(value):
    count, stack = 0, [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            count += sum(key in _DIRECTIVES for key in item)
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return count


def _cycle_nodes(graph):
    # At most 256 declared nodes: bounded reachability also catches overlapping
    # cycles whose edges lead to a node visited by an earlier DFS branch.
    cyclic = 0
    for start in graph:
        seen, pending = set(), list(graph[start])
        while pending:
            target = pending.pop()
            if target == start:
                cyclic += 1
                break
            if target not in seen and target in graph:
                seen.add(target)
                pending.extend(graph[target])
    return cyclic


def resolve_modifications(unit: dict, definitions: dict) -> dict:
    common = definitions.get("modifications")
    templates = definitions.get("templates")
    if not isinstance(common, dict) or not isinstance(templates, dict):
        raise ValueError("Invalid common modification definitions")
    local = unit.get("modifications", {})
    invalid_modifications = not isinstance(local, dict) or len(local) > 256
    if invalid_modifications:
        local = {}
    counts, details, graph = Counter(), {}, {}
    counts["unsupported_directive_count"] = _directive_count(unit)
    if invalid_modifications:
        counts["invalid_declaration_count"] += 1
    valid_names = {
        name
        for name, value in local.items()
        if isinstance(name, str) and _NAME.fullmatch(name) and isinstance(value, dict)
    }
    for name, declared in sorted(local.items()):
        if not isinstance(name, str) or not _NAME.fullmatch(name) or not isinstance(declared, dict):
            counts["invalid_declaration_count"] += 1
            continue
        inherited = common.get(name)
        if isinstance(inherited, dict):
            counts["common_definition_count"] += 1
        else:
            inherited = {}
            counts["missing_common_definition_count"] += 1
        counts["unsupported_directive_count"] += _directive_count(inherited)
        counts["declared_count"] += 1
        counts["local_override_count"] += bool(declared)
        selected, origins = {}, {}
        for key in sorted(_SCALARS):
            owner = declared if key in declared else inherited
            if key not in owner:
                continue
            value = _metadata(key, owner[key])
            if value is None:
                counts["invalid_declaration_count"] += 1
            selected[key] = value
            origins[key] = "unit" if key in declared else "common"
        graph[name] = []
        for key in ("prevModification", "reqModification"):
            if isinstance(selected.get(key), list):
                for target in selected[key]:
                    graph[name].append(target)
                    counts["dependency_edge_count"] += 1
                    if target not in valid_names:
                        counts["missing_dependency_count"] += 1
        blocks = {}
        for key in _BLOCKS:
            layers = {}
            for layer, owner in (("common", inherited), ("unit", declared)):
                if key not in owner:
                    continue
                value = _atoms(owner[key])
                layers[layer] = value
                counts["complex_effect_block_count"] += value["complex_blocks"]
                counts["uninterpreted_effect_value_count"] += value["uninterpreted_values"]
                if value["status"] == "invalid":
                    counts["invalid_declaration_count"] += 1
                if layer == "unit" and owner[key] == {}:
                    counts["explicit_empty_block_count"] += 1
            if layers:
                if len(layers) == 2:
                    counts["overlapping_block_count"] += 1
                blocks[key] = {"layers": layers, "merge_status": "not_simulated"}
        template_results = {}
        for slot in ("modUpgradeType", "modOverdriveType"):
            if slot not in selected:
                continue
            counts["template_reference_count"] += 1
            template_name = selected[slot]
            template = templates.get(template_name) if isinstance(template_name, str) else None
            if not isinstance(template, dict):
                counts["missing_template_count"] += 1
                template_results[slot] = {"name": template_name, "status": "missing"}
                continue
            template_blocks = {key: _atoms(template[key]) for key in _BLOCKS if key in template}
            for value in template_blocks.values():
                counts["complex_effect_block_count"] += value["complex_blocks"]
                counts["uninterpreted_effect_value_count"] += value["uninterpreted_values"]
                counts["invalid_declaration_count"] += value["status"] == "invalid"
            copy_weapon = template.get("copyWeaponMod")
            if copy_weapon is True:
                counts["external_weapon_template_count"] += 1
            if copy_weapon is not None and type(copy_weapon) is not bool:
                counts["invalid_declaration_count"] += 1
            directives = _directive_count(template)
            counts["unsupported_directive_count"] += directives
            template_results[slot] = {
                "name": template_name,
                "status": "declared",
                "copyWeaponMod": copy_weapon if type(copy_weapon) is bool else None,
                "blocks": template_blocks,
            }
        details[name] = {
            "common_definition": name if name in common else None,
            "metadata_candidates": selected,
            "metadata_origins": origins,
            "blocks": blocks,
            "templates": template_results,
            # Economic/UI/special flags outside this resolver's contract remain
            # visible as unparsed key names, never silently treated as no-ops.
            "other_declaration_keys": {
                layer: sorted(
                    key
                    for key in owner
                    if isinstance(key, str)
                    and _NAME.fullmatch(key)
                    and key not in _SCALARS
                    and key not in _BLOCKS
                    and key not in _DIRECTIVES
                )
                for layer, owner in (("common", inherited), ("unit", declared))
            },
        }
    counts["cycle_node_count"] = _cycle_nodes(graph)
    partial = any(
        counts[key]
        for key in (
            "missing_common_definition_count",
            "missing_dependency_count",
            "cycle_node_count",
            "missing_template_count",
            "unsupported_directive_count",
            "invalid_declaration_count",
        )
    )
    summary = {key: counts[key] for key in CONFIGURATION_COUNTERS}
    summary.update(
        base_status="unresolved_directives" if counts["unsupported_directive_count"] else "direct_fields",
        status="partial" if partial else "declarations_resolved" if counts["declared_count"] else "none_declared",
        effective_parameters_available=False,
        installed_state_known=False,
        engine_composition_verified=False,
    )
    return {
        "summary": summary,
        "modifications": details,
        "effective_parameters": None,
        "effective_parameter_reasons": [
            "installed_modifications_unknown",
            "game_mode_unknown",
            "engine_composition_unverified",
        ],
    }
