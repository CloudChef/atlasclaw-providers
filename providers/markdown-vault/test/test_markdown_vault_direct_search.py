from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "markdown-vault-query" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _config import build_markdown_vault_config
from _direct_search import search_direct


def _config(tmp_path: Path, **overrides):
    """Build a direct-search test config for a temporary vault."""

    vault = tmp_path / "vault"
    vault.mkdir()
    raw_config = {
        "vault_path": str(vault),
        "max_chunk_chars": 400,
        **overrides,
    }
    return build_markdown_vault_config(raw_config=raw_config, instance_name="team", base_dir=tmp_path)


def test_direct_config_requires_only_vault_path(tmp_path: Path) -> None:
    """Verify direct search has no database configuration requirement."""

    vault = tmp_path / "vault"
    vault.mkdir()

    config = build_markdown_vault_config(
        raw_config={"vault_path": str(vault)},
        instance_name="team",
        base_dir=tmp_path,
    )

    assert config.vault_path == vault
    assert config.max_context_chars == 24576
    assert config.max_result_chars == 3072


def test_direct_search_returns_bounded_markdown_text_with_keywords(tmp_path: Path) -> None:
    """Verify keyword expansion can recover a typo and return cited Markdown context."""

    config = _config(tmp_path)
    (config.vault_path / "Infoblox.md").write_text(
        "\n".join(
            [
                "---",
                "title: Infoblox IPAM 对接",
                "tags: [smartcmp, ipam]",
                "aliases: [Infoxblox, IP 地址分配]",
                "---",
                "# Infoblox IPAM 对接",
                "## 支持的功能",
                "申请华为 FC 的 VM 时，可以通过 Infoblox 获取 IP 地址、网关和 DNS。",
            ]
        ),
        encoding="utf-8",
    )

    payload = search_direct(
        config,
        "Infoxblox 分配 IP",
        keywords=["Infoblox", "IPAM", "IP 地址"],
        limit=3,
        path_filter=None,
        tag_filter=None,
    )

    assert payload["success"] is True
    assert payload["search_backend"] == "direct"
    assert payload["results"][0]["path"] == "Infoblox.md"
    assert payload["results"][0]["matched_keywords"]
    assert "Infoblox" in payload["results"][0]["text"]
    assert payload["results"][0]["text_truncated"] is False


def test_direct_search_applies_path_and_tag_filters_before_ranking(tmp_path: Path) -> None:
    """Verify filters are applied before broad common terms can fill the candidate set."""

    config = _config(tmp_path)
    for index in range(20):
        (config.vault_path / f"decoy-{index:02d}.md").write_text(
            "# Decoy\ncommon searchable text\n",
            encoding="utf-8",
        )
    (config.vault_path / "target.md").write_text(
        "---\ntags: [target]\n---\n# Target\ncommon searchable text\n",
        encoding="utf-8",
    )

    by_path = search_direct(
        config,
        "common",
        keywords=["common"],
        limit=1,
        path_filter="target",
        tag_filter=None,
    )
    by_tag = search_direct(
        config,
        "common",
        keywords=["common"],
        limit=1,
        path_filter=None,
        tag_filter="target",
    )

    assert by_path["results"][0]["path"] == "target.md"
    assert by_tag["results"][0]["path"] == "target.md"
    assert by_path["status"]["scanned_chunks"] == 1
    assert by_tag["status"]["scanned_chunks"] == 1


def test_direct_search_downweights_vault_specific_common_query_terms(tmp_path: Path) -> None:
    """Verify broad terms are downweighted from the current vault instead of a fixed stopword list."""

    config = _config(tmp_path)
    for index in range(20):
        (config.vault_path / f"resource-{index:02d}.md").write_text(
            "# 平台资源配置\n平台支持资源配置和资源管理。\n",
            encoding="utf-8",
        )
    (config.vault_path / "idle.md").write_text(
        "# 资源治理\n支持发现闲置资源，并按策略释放长期未使用的云主机。\n",
        encoding="utf-8",
    )

    payload = search_direct(
        config,
        "平台是否支持发现闲置资源？",
        keywords=[],
        limit=5,
        path_filter=None,
        tag_filter=None,
    )

    assert payload["results"][0]["path"] == "idle.md"


def test_direct_search_keeps_single_common_keyword_as_low_weight_signal(tmp_path: Path) -> None:
    """Verify dynamic common-term handling cannot delete the only available query signal."""

    config = _config(tmp_path)
    for index in range(8):
        (config.vault_path / f"kubernetes-{index:02d}.md").write_text(
            "# Kubernetes\nKubernetes deployment notes.\n",
            encoding="utf-8",
        )

    payload = search_direct(
        config,
        "kubernetes",
        keywords=["kubernetes"],
        limit=3,
        path_filter=None,
        tag_filter=None,
    )

    assert payload["result_count"] == 3
    assert all("kubernetes" in result["path"] for result in payload["results"])


def test_direct_search_limits_context_budget(tmp_path: Path) -> None:
    """Verify returned text stays within the provider context budget."""

    config = _config(tmp_path, max_context_chars=1000, max_result_chars=300)
    for index in range(6):
        (config.vault_path / f"long-{index}.md").write_text(
            "# Long\n" + ("budget keyword context " * 80),
            encoding="utf-8",
        )

    payload = search_direct(
        config,
        "budget keyword",
        keywords=["budget", "keyword"],
        limit=6,
        path_filter=None,
        tag_filter=None,
    )

    assert payload["status"]["returned_context_chars"] <= 1000
    assert payload["status"]["limited_by_context_budget"] is True
    assert all(len(result["text"]) <= 300 for result in payload["results"])
    assert any(result["text_truncated"] for result in payload["results"])


def test_runtime_search_script_accepts_keywords_json(tmp_path: Path) -> None:
    """Verify the AtlasClaw runtime script exposes `keywords` through CLI flags."""

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "ops.md").write_text("# Ops\nRollback from the CLI smoke test.\n", encoding="utf-8")
    env = os.environ.copy()
    env["ATLASCLAW_PROVIDER_CONFIG"] = json.dumps(
        {"markdown-vault": {"team": {"vault_path": str(vault), "max_chunk_chars": 400}}}
    )
    env["ATLASCLAW_PROVIDER_TYPE"] = "markdown-vault"
    env["ATLASCLAW_PROVIDER_INSTANCE"] = "team"

    search = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "search.py"),
            "--query",
            "deployment backout",
            "--keywords",
            "rollback",
            "--limit",
            "3",
        ],
        cwd=SCRIPTS_DIR,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert search.returncode == 0, search.stderr
    payload = json.loads(search.stdout)
    assert payload["success"] is True
    assert payload["results"][0]["path"] == "ops.md"
    assert "Rollback" in payload["results"][0]["text"]


@pytest.mark.skipif(
    os.getenv("SMARTCMP_MARKDOWN_VAULT_VALIDATE") != "1",
    reason="SmartCMP local vault validation is opt-in.",
)
def test_smartcmp_question_list_can_be_searched_one_by_one() -> None:
    """Optionally verify every SmartCMP sample question returns bounded direct-search evidence."""

    vault = Path("/Users/lfang/CodeRepo/smartcmp/KnowledgeAgent/SmartCMP")
    question_list = Path("/Users/lfang/CodeRepo/smartcmp/KnowledgeAgent/问题列表.md")
    assert vault.is_dir()
    assert question_list.is_file()

    config = build_markdown_vault_config(
        raw_config={"vault_path": str(vault), "max_chunk_chars": 1800},
        instance_name="smartcmp",
        base_dir=Path.cwd(),
    )
    questions = _extract_questions(question_list)
    assert len(questions) == 18

    failures: list[str] = []
    for question, expected_note in questions:
        payload = search_direct(
            config,
            question,
            keywords=_smartcmp_keyword_fixture(question, expected_note),
            limit=12,
            path_filter=None,
            tag_filter=None,
        )
        if not payload["results"]:
            failures.append(question)
        expected_path_hints = _smartcmp_expected_path_hints(question)
        if expected_path_hints and not _has_expected_path(payload["results"][:5], expected_path_hints):
            paths = ", ".join(result["path"] for result in payload["results"][:5])
            failures.append(f"{question}: top paths [{paths}]")
        assert payload["status"]["returned_context_chars"] <= config.max_context_chars
    assert failures == []


def _extract_questions(path: Path) -> list[tuple[str, str]]:
    questions: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        payload = stripped[2:].strip()
        if " - " in payload:
            question, expected_note = payload.split(" - ", 1)
        else:
            question, expected_note = payload, ""
        questions.append((question.strip(), expected_note.strip()))
    return questions


def _smartcmp_keyword_fixture(question: str, expected_note: str) -> list[str]:
    text = f"{question} {expected_note}"
    keywords: list[str] = []
    if "闲置资源" in text:
        keywords.extend(["闲置资源", "资源闲置", "闲置释放", "超配", "低配", "资源治理", "合规策略"])
    if "任意的类型" in text or "发现的策略" in text:
        keywords.extend(["内置策略", "云主机资源闲置释放策略", "策略名称", "修复建议", "CPU", "内存"])
    if "MaxCompute" in text:
        keywords.extend(["阿里云", "MaxCompute", "DataWorks", "云原生大数据计算服务"])
    if "不用选任何资源" in text:
        keywords.extend(["空请求单", "允许不选任意子请求", "允许提交空请求单", "人工运维操作", "子请求"])
    if "OceanProtect" in text:
        keywords.extend(["OceanProtect", "备份系统", "备份恢复", "备份策略", "SLA", "DCS"])
    if "Lamda" in text:
        keywords.extend(["Lambda", "AWS Lambda", "Terraform", "Terrafrom"])
    if "Terrafrom" in text:
        keywords.append("Terraform")
    if "深信服 SCP" in text:
        keywords.extend(["深信服", "SCP", "物理机", "物理主机", "宿主机", "监控", "告警"])
    if "Infoxblox" in text:
        keywords.extend(["Infoblox", "Infoxblox", "IPAM", "IP 地址", "华为 FC"])
    if "Splunk" in text:
        keywords.extend(["Splunk", "SIEM", "安全事件", "Syslog", "审计", "告警"])
    if "泛微 OA" in text:
        keywords.extend(["泛微", "OA", "外部审批", "第三方审批", "审批回调", "流程"])
    if "财务系统" in text:
        keywords.extend(["财务系统", "账户余额", "余额检查", "费用冻结", "冻结金额", "订单", "结算"])
    if "MySQL" in text and "端口号" in text:
        keywords.extend(["MySQL", "端口", "软件采集", "软件实例", "运行端口", "CMDB"])
    if "排班" in text:
        keywords.extend(["排班", "值班", "on-call", "工单处理", "处理人", "人员"])
    if "漏扫" in text:
        keywords.extend(["漏扫", "漏洞扫描", "最近一次", "VM 详情", "安全系统", "绿盟", "启明星辰"])
    if "ITSM" in text:
        keywords.extend(["ITSM", "ITIL", "事件工单", "问题工单", "变更工单"])
    if "TLS1.2" in text:
        keywords.extend(["TLS1.2", "TLS 1.2", "TLS1.3", "TLS", "禁用 TLS", "安全协议", "协议版本"])
    if "镜像名称" in text or "过滤条件" in text:
        keywords.extend(
            [
                "镜像名称",
                "操作系统镜像",
                "镜像模板",
                "虚拟机模板",
                "Image name pattern",
                "资源包",
                "模板关联",
                "规格关联",
            ]
        )
    if "基线化" in text:
        keywords.extend(["基线化", "基线脚本", "部署工作流", "VM 部署", "初始化脚本", "BigFix"])
    return _dedupe(keywords)


def _smartcmp_expected_path_hints(question: str) -> list[str]:
    hints = {
        "闲置资源": ["安全审计与合规/合规展示、安全扫描与漏洞管理.md"],
        "MaxCompute": ["阿里云公有云接入.md", "阿里云 Apsara 专有云接入.md"],
        "不用选任何资源": ["流程审批与工单.md"],
        "OceanProtect": ["备份恢复系统对接.md"],
        "Lamda": ["Terraform Enterprise 对接.md"],
        "深信服 SCP": ["深信服 SCP 接入.md"],
        "Infoxblox": ["Infoblox IPAM - DNS 对接.md"],
        "Splunk": ["Splunk SIEM 对接.md"],
        "泛微 OA": ["OA - ITSM - 第三方审批.md"],
        "财务系统": ["财务系统 - 费用结算对接.md"],
        "MySQL": ["软硬件配置项采集.md"],
        "排班": ["排班管理.md"],
        "漏扫": ["安全系统 - 漏扫系统对接.md", "启明星辰漏扫对接.md", "绿盟漏扫对接.md"],
        "ITSM": ["ITSM 系统对接.md"],
        "TLS1.2": ["TLS - HTTPS - HA - 负载均衡.md"],
        "镜像名称": ["云账号与云平台接入.md", "磁盘、镜像与快照.md"],
        "基线化": ["流程审批与工单.md", "安全系统 - 漏扫系统对接.md"],
    }
    for marker, expected_hints in hints.items():
        if marker in question:
            return expected_hints
    return []


def _has_expected_path(results: list[dict[str, object]], expected_hints: list[str]) -> bool:
    return any(
        any(hint in str(result["path"]) for hint in expected_hints)
        for result in results
    )


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
