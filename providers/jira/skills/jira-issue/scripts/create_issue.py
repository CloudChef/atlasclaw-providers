# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import argparse
import sys

from _common import build_client, ensure_connection, json_out, load_jira_instance, resolve_project_key


def fill_required_fields(client, api_version: str, project_key: str, issue_type: str, fields: dict) -> None:
    meta_resp = client.get(
        f"/rest/api/{api_version}/issue/createmeta",
        params={"projectKeys": project_key, "expand": "projects.issuetypes.fields"},
    )
    
    if meta_resp.status_code != 200:
        return
    
    meta = meta_resp.json()
    for proj in meta.get("projects", []):
        if proj["key"] != project_key:
            continue
        for itype in proj.get("issuetypes", []):
            if itype["name"] != issue_type:
                continue
            for field_key, field_def in itype.get("fields", {}).items():
                if not field_def.get("required"):
                    continue
                if field_key in ("project", "summary", "issuetype", "description", "reporter"):
                    continue
                if field_key == "components":
                    comp_resp = client.get(
                        f"/rest/api/{api_version}/project/{project_key}/components"
                    )
                    if comp_resp.status_code == 200:
                        comps = comp_resp.json()
                        if comps:
                            fields["components"] = [{"id": comps[0]["id"]}]
                elif field_key == "priority":
                    fields.setdefault("priority", {"name": "Medium"})


def main() -> int:
    ap = argparse.ArgumentParser(description="Create Jira issue")
    ap.add_argument("--summary", required=True)
    ap.add_argument("--description", required=True)
    ap.add_argument("--issue-type", default="Task")
    ap.add_argument("--project-key", default="")
    ap.add_argument("--priority", default="")
    args = ap.parse_args()

    try:
        inst = load_jira_instance()
        with build_client(inst)[0] as client:
            _, api_version = build_client(inst)
            ensure_connection(client, api_version)
            project_key = resolve_project_key(client, api_version, args.project_key or str(inst.get("default_project", "")))

            fields: dict = {
                "project": {"key": project_key},
                "summary": args.summary,
                "description": args.description,
                "issuetype": {"name": args.issue_type},
            }
            if args.priority:
                fields["priority"] = {"name": args.priority}

            fill_required_fields(client, api_version, project_key, args.issue_type, fields)

            resp = client.post(f"/rest/api/{api_version}/issue", json={"fields": fields})
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"create failed: {resp.status_code} {resp.text[:300]}")
            data = resp.json()
            json_out({"ok": True, "issue_key": data.get("key"), "issue_id": data.get("id")})
            return 0
    except Exception as e:
        json_out({"ok": False, "error": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
