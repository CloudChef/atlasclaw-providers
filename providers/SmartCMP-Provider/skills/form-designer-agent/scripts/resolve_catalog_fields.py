# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

"""Resolve requested service-catalog field labels to exact catalog keys."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from typing import Any


NEXT_TOOL = "smartcmp_generate_catalog_context_form"
NEXT_STEP = (
    "call smartcmp_generate_catalog_context_form immediately with catalogContextFields; "
    "do not ask whether the composed field should be visible because composed fields are hidden-submitted by default"
)
RESOURCE_SPEC_RESERVED = {
    "node",
    "type",
    "params",
    "resourceBundleId",
    "resourceBundleParams",
    "resourceBundleTags",
}
FIELD_SEPARATOR_NAMES = {"FULLWIDTH COMMA", "IDEOGRAPHIC COMMA"}
CJK_LABEL_TRANSLATIONS = [
    (("90E8", "95E8"), "department"),
    (("9879", "76EE"), "project"),
    (("4E1A", "52A1", "7EC4"), "business group"),
    (("6240", "6709", "8005"), "owner"),
    (("540D", "79F0"), "name"),
    (("8BA1", "7B97", "89C4", "683C"), "compute specification"),
    (("8BA1", "8D39", "7C7B", "578B"), "billing type"),
    (("5E26", "5BBD"), "bandwidth"),
]
SEMANTIC_ALIAS_GROUPS = {
    "department": ("department", "dept"),
    "project": ("project",),
    "business group": ("businessgroup", "businessgroupname", "businessgroupid", "tenant", "bu"),
    "owner": ("owner", "ownername", "ownerid"),
    "name": ("displayname",),
    "compute specification": (
        "computespecification",
        "computeprofile",
        "computeprofileid",
        "flavor",
        "flavorid",
        "instancetype",
    ),
    "billing type": ("billingtype", "internetcharge", "chargetype"),
    "bandwidth": ("bandwidth",),
}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize(value: Any) -> str:
    text = _clean(value).lower()
    return "".join(ch for ch in text if ch.isalnum())


def _localized_text(value: Any) -> str:
    if not isinstance(value, dict):
        return _clean(value)
    for key in ("zh", "zh_CN", "zh-CN", "cn", "en", "value", "label", "title"):
        if _clean(value.get(key)):
            return _clean(value.get(key))
    return ""


def _label_from_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("label", "title", "displayName", "display_name", "nameZh", "name"):
        if _clean(value.get(key)):
            return _clean(value.get(key))
    for key in ("i18nTitle", "i18n_title"):
        if text := _localized_text(value.get(key)):
            return text
    return ""


def _cjk_signature(value: str) -> str:
    codepoints = [
        f"{ord(ch):04X}"
        for ch in value
        if unicodedata.name(ch, "").startswith("CJK UNIFIED IDEOGRAPH-")
    ]
    return "-".join(codepoints)


def _translated_label(value: str) -> str:
    signature = _cjk_signature(value)
    if not signature:
        return ""
    for codepoints, label in CJK_LABEL_TRANSLATIONS:
        if "-".join(codepoints) in signature:
            return label
    return ""


def _output_label(value: str) -> str:
    return _translated_label(value) or value


def _semantic_groups_from_text(value: Any) -> set[str]:
    text = _normalize(value)
    groups = set()
    for group, aliases in SEMANTIC_ALIAS_GROUPS.items():
        if any(alias in text for alias in aliases):
            groups.add(group)
    return groups


def _semantic_groups_for_label(label: str) -> set[str]:
    groups = _semantic_groups_from_text(label)
    translated = _translated_label(label)
    if translated:
        groups.add(translated)
        groups.update(_semantic_groups_from_text(translated))
    return groups


def _looks_like_backend_key(value: str) -> bool:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_@:\-]*", value):
        return False
    if re.search(r"[A-Z]", value):
        return True
    if "_" in value or value.endswith("Id") or value.endswith("_id"):
        return True
    return bool(re.search(r"[a-z][A-Z]", value))


def _split_labels(value: str) -> list[str]:
    labels: list[str] = []
    normalized = "".join(
        "," if ch in {",", "\n"} or unicodedata.name(ch, "") in FIELD_SEPARATOR_NAMES else ch
        for ch in value.strip()
    )
    for item in re.split(r",+", normalized):
        item = item.strip()
        if item and item not in labels:
            labels.append(item)
    return labels


def _field_label(field: Any, fallback_key: str) -> str:
    if isinstance(field, dict):
        for key in ("label", "title", "name", "displayName", "display_name"):
            if _clean(field.get(key)):
                return _clean(field.get(key))
        for key in ("i18nTitle", "i18n_title"):
            if text := _localized_text(field.get(key)):
                return text
        for key in ("templateOptions", "template_options", "props", "options", "ui"):
            if text := _label_from_mapping(field.get(key)):
                return text
    return fallback_key


def _iter_named_fields(value: Any, source: str):
    if isinstance(value, dict):
        for raw_key, raw_field in value.items():
            field = raw_field if isinstance(raw_field, dict) else {}
            key = _clean(field.get("key") if field else "") or _clean(raw_key)
            if key:
                yield {"key": key, "label": _field_label(field, key), "source": source, "field": field}
    elif isinstance(value, list):
        for raw_field in value:
            if not isinstance(raw_field, dict):
                continue
            key = _clean(raw_field.get("key") or raw_field.get("name") or raw_field.get("id"))
            if key:
                yield {"key": key, "label": _field_label(raw_field, key), "source": source, "field": raw_field}


def _iter_required_fields(value: Any, source: str):
    if not isinstance(value, list):
        return
    for raw_key in value:
        key = _clean(raw_key)
        if key:
            yield {"key": key, "label": key, "source": source, "field": {"key": key}}


def _field_candidates(detail: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def add_many(value: Any, source: str) -> None:
        existing = {(c["key"], c["label"], c["source"]) for c in candidates}
        for candidate in _iter_named_fields(value, source):
            pair = (candidate["key"], candidate["label"], candidate["source"])
            if pair not in existing:
                candidates.append(candidate)
                existing.add(pair)

    add_many(detail.get("catalogPayloadFields"), "catalogPayloadFields")
    instructions = detail.get("instructions") if isinstance(detail.get("instructions"), dict) else {}
    add_many(list(_iter_required_fields(instructions.get("topLevelRequired"), "instructions.topLevelRequired")), "instructions.topLevelRequired")
    add_many(instructions.get("topLevelFields"), "instructions.topLevelFields")
    add_many(instructions.get("params"), "instructions.params")
    generic = instructions.get("genericRequest") if isinstance(instructions.get("genericRequest"), dict) else {}
    add_many(generic.get("processForm"), "instructions.genericRequest.processForm")
    specs = instructions.get("resourceSpecs")
    if isinstance(specs, list):
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            add_many(spec.get("params"), "instructions.resourceSpecs.params")
            add_many(spec.get("resourceBundleParams"), "instructions.resourceSpecs.resourceBundleParams")
            direct = {
                key: value
                for key, value in spec.items()
                if key not in RESOURCE_SPEC_RESERVED and isinstance(value, dict)
            }
            add_many(direct, "instructions.resourceSpecs.resourceSpecFields")
    return candidates


def _candidate_evidence(candidate: dict[str, Any]) -> str:
    values = [candidate.get("key"), candidate.get("label")]
    field = candidate.get("field")
    if isinstance(field, dict):
        for key in ("description", "ask", "when", "type", "node", "location"):
            values.append(field.get(key))
    return " ".join(_clean(value) for value in values if _clean(value))


def _candidate_field_summary(candidate: dict[str, Any]) -> dict[str, str]:
    summary = {
        "key": str(candidate["key"]),
        "label": str(candidate["label"]),
        "source": str(candidate["source"]),
    }
    evidence = _candidate_evidence(candidate)
    if evidence:
        summary["evidence"] = evidence
    return summary


def _candidate_tokens(candidate: dict[str, Any]) -> set[str]:
    tokens = {
        _normalize(candidate.get("key")),
        _normalize(candidate.get("label")),
    }
    return {token for token in tokens if token}


def _candidate_semantic_groups(candidate: dict[str, Any]) -> set[str]:
    return _semantic_groups_from_text(_candidate_evidence(candidate))


def _candidate_match_rank(label: str, candidate: dict[str, Any]) -> int | None:
    target = _normalize(label)
    if not target:
        return None
    if target in _candidate_tokens(candidate):
        return 0
    translated = _translated_label(label)
    if translated and _normalize(translated) in _candidate_tokens(candidate):
        return 1
    if _semantic_groups_for_label(label) & _candidate_semantic_groups(candidate):
        return 2
    evidence = _normalize(_candidate_evidence(candidate))
    # Substring evidence matching is useful for CJK descriptions, but short
    # ASCII labels such as "name" must not match unrelated keys like ownerName.
    raw_label = _clean(label)
    can_use_substring = (
        any(ord(ch) > 127 for ch in target)
        or bool(re.search(r"\s", raw_label))
    )
    if len(target) >= 2 and bool(evidence) and can_use_substring and target in evidence:
        return 3
    return None


def _resolve_one(label: str, candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    ranked = [
        (rank, candidate)
        for candidate in candidates
        if (rank := _candidate_match_rank(label, candidate)) is not None
    ]
    if not ranked:
        return None, []
    best_rank = min(rank for rank, _ in ranked)
    matches = [candidate for rank, candidate in ranked if rank == best_rank]
    keys = {item["key"] for item in matches}
    if len(keys) == 1:
        return matches[0], []
    if len(keys) > 1:
        return None, matches
    return None, []


def resolve_catalog_fields(detail: dict[str, Any], labels_text: str) -> dict[str, Any]:
    labels = _split_labels(labels_text)
    candidates = _field_candidates(detail)
    mappings: list[dict[str, str]] = []
    missing: list[str] = []
    ambiguous: list[dict[str, Any]] = []
    for label in labels:
        candidate, ambiguous_matches = _resolve_one(label, candidates)
        if candidate:
            mappings.append(
                {"label": _output_label(label), "key": candidate["key"], "source": candidate["source"]}
            )
        elif ambiguous_matches:
            ambiguous.append(
                {
                    "label": label,
                    "matches": [_candidate_field_summary(item) for item in ambiguous_matches],
                }
            )
        else:
            missing.append(label)

    can_generate = bool(labels) and not missing and not ambiguous
    context_fields = ",".join(f"{item['label']}={item['key']}" for item in mappings) if can_generate else ""
    backend_key_label_warnings = sorted(
        {
            item["label"]
            for item in mappings
            if _normalize(item["label"]) == _normalize(item["key"])
            and _looks_like_backend_key(item["label"])
        }
    )
    return {
        "catalogId": detail.get("id") or detail.get("catalogId") or detail.get("uuid"),
        "catalogName": detail.get("name") or detail.get("catalogName"),
        "requestedLabels": labels,
        "fieldEvidenceCount": len(candidates),
        "candidateFields": [_candidate_field_summary(candidate) for candidate in candidates],
        "mappings": mappings,
        "missingLabels": missing,
        "ambiguousLabels": ambiguous,
        "catalogContextFields": context_fields,
        "backendKeyLabelWarnings": backend_key_label_warnings,
        "canGenerateCatalogContextForm": can_generate,
        "nextTool": NEXT_TOOL if can_generate else "",
        "nextStep": NEXT_STEP if can_generate else "",
    }


def _emit_meta(meta: dict[str, Any]) -> None:
    print("##CATALOG_FIELD_RESOLUTION_META_START##", file=sys.stderr)
    print(json.dumps(meta, ensure_ascii=False), file=sys.stderr)
    print("##CATALOG_FIELD_RESOLUTION_META_END##", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("[ERROR] Missing required catalog_detail_json and labels arguments.")
        return 1
    try:
        detail = json.loads(argv[0])
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Invalid catalog detail JSON: {exc}")
        return 1
    if not isinstance(detail, dict):
        print("[ERROR] Catalog detail JSON must be an object.")
        return 1
    labels_text = argv[1].strip()
    if not labels_text:
        print("[ERROR] Missing requested labels.")
        return 1

    meta = resolve_catalog_fields(detail, labels_text)
    if meta["canGenerateCatalogContextForm"]:
        print(f"Resolved Catalog Fields: {meta['catalogContextFields']}")
        if meta["backendKeyLabelWarnings"]:
            print(
                "[WARNING] Requested labels look like backend keys. "
                "Preserve the user's output labels on the left side of label=key pairs: "
                + ",".join(meta["backendKeyLabelWarnings"])
            )
        print(f"Next: {meta['nextStep']}")
    else:
        unresolved = meta["missingLabels"] or [
            item["label"] for item in meta["ambiguousLabels"]
        ]
        print(f"Catalog fields unresolved. Missing labels: {','.join(unresolved)}")
    _emit_meta(meta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
