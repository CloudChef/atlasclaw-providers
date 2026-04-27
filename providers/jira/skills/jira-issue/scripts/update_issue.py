# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import argparse
import sys

from _common import build_client, ensure_connection, json_out, load_jira_instance


def main() -> int:
    ap = argparse.ArgumentParser(description="Update Jira issue")
    ap.add_argument("issue_key")
    ap.add_argument("--summary", default="")
    ap.add_argument("--description", default="")
    ap.add_argument("--priority", default="")
    args = ap.parse_args()

    fields = {}
    if args.summary:
        fields["summary"] = args.summary
    if args.description:
        fields["description"] = args.description
    if args.priority:
        fields["priority"] = {"name": args.priority}

    if not fields:
        json_out({"ok": False, "error": "no fields provided"})
        return 1

    try:
        inst = load_jira_instance()
        client, api_version = build_client(inst)
        with client:
            ensure_connection(client, api_version)
            resp = client.put(f"/rest/api/{api_version}/issue/{args.issue_key}", json={"fields": fields})
            if resp.status_code not in (200, 204):
                raise RuntimeError(f"update failed: {resp.status_code} {resp.text[:300]}")
            json_out({"ok": True, "issue_key": args.issue_key, "updated_fields": list(fields.keys())})
            return 0
    except Exception as e:
        json_out({"ok": False, "error": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
