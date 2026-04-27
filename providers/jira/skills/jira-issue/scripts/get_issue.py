# -*- coding: utf-8 -*-
# Copyright 2026  Qianyun, Inc., www.cloudchef.io, All rights reserved.

from __future__ import annotations

import argparse
import sys

from _common import build_client, ensure_connection, json_out, load_jira_instance


def main() -> int:
    ap = argparse.ArgumentParser(description="Get Jira issue")
    ap.add_argument("issue_key")
    args = ap.parse_args()

    try:
        inst = load_jira_instance()
        client, api_version = build_client(inst)
        with client:
            ensure_connection(client, api_version)
            resp = client.get(f"/rest/api/{api_version}/issue/{args.issue_key}")
            if resp.status_code != 200:
                raise RuntimeError(f"get failed: {resp.status_code} {resp.text[:300]}")
            issue = resp.json()
            fields = issue.get("fields", {})
            json_out({
                "ok": True,
                "issue_key": issue.get("key"),
                "summary": fields.get("summary"),
                "status": (fields.get("status") or {}).get("name"),
            })
            return 0
    except Exception as e:
        json_out({"ok": False, "error": str(e)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
