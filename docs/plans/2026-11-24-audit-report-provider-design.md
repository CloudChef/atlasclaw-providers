# AtlasClaw Provider UI/Python 扩展 + audit-report Provider 设计与规格

日期：2026-11-24
状态：设计稿（待确认后实施）
范围：atlasclaw core、atlasclaw-providers、audit-report provider
上位标准：`atlasclaw/docs/PROVIDER-EXTENSION-STANDARD.md`（Provider Extension Standard v1）

本文件只描述 audit-report 这个**参考实现**；任何与标准冲突之处以标准为准。新增 provider 必须复用同一套 manifest、UI 嵌入协议、API 契约和 Host Services，不得为单个 provider 增加特例。

---

## 1. 目标

1. 在 AtlasClaw 中引入**基于 provider 包的前端 UI 扩展**：provider 目录存在即被发现，可在左侧导航增加页面入口。
2. 引入**provider 自己的后端 Python 扩展**：复用现有 `runtime-api.json` 机制，补齐实例、二进制响应、后台任务能力。
3. 把 `audit-report` 从 standalone skill 升级为 **provider 包**，提供“文件审核”页面：
   - 上传 PDF/Word；
   - 文档列表（文档名称/报告编号/上传时间/处理状态/审核结果/操作）；
   - 后台审核任务、进度、结果查看；
   - 审核结果 HTML 在线预览与下载。
4. 保持向后兼容：没有 `ui` 的 provider 行为不变；standalone skills 仍可加载。

非目标（本轮不做）：

- 多租户跨用户共享文档库（默认按用户隔离，管理员可选全量视图，后续再加）；
- 多节点/分布式任务队列（单进程 `asyncio` 任务，重启标记失败）；
- 在 provider UI 中直接执行任意第三方远程 JS（只加载本 provider 包内静态资源）；
- 审核规则本身的改写（复用现有 19 项规则与脚本）。

---

## 2. 现状与可复用能力

| 能力 | 现状 | 结论 |
|---|---|---|
| Provider 发现 | `providers_root` 扫描目录，要求 `PROVIDER.md`，可选 `provider.schema.json` | 可直接扩展 manifest |
| Provider 后端 API | `runtime-api.json` + `api/provider_http_routes.py`，路径 `/api/providers/{type}/{instance}/{path}`，`async handler(request, context)` | **复用**，需补实例、二进制响应 |
| Provider 配置 UI | `provider.schema.json → config_schema` 渲染表单 | 可复用 catalog/icon |
| Provider 技能 | `providers/<p>/skills/*` 启动加载 | audit-report 直接迁入 |
| 前端导航 | `app.js` 静态路由；`sidebar.js` 左侧栏；`header.js` 用户菜单 | 需新增动态入口 |
| 附件/文件 | 已有 `/api/chat/attachments`（图片/文档），物化到 work_dir | audit 上传可复用或独立 |
| 后台任务 | `run_service.execute_agent_run` + `APIContext.active_runs` | 需封装为 provider 可用的 host 服务 |

---

## 3. 总体架构

```
providers/audit-report/
  provider.schema.json      # catalog + ui + runtime_capabilities + config
  runtime-api.json          # 后端 API 路由 -> api/handlers.py
  ui/index.html|app.js|style.css
  api/handlers.py|store.py|service.py
  skills/audit-report/      # 原技能整体迁入
  assets/icon.svg
        │
        ├── core 启动扫描 ──► Provider UI Registry ──► GET /api/ui/extensions
        │                                        └──► GET /api/ui/extensions/{p}/{nav}/{asset}
        │
        └── provider.schema.json ──► HTTP manifest ──► /api/providers/audit-report/default/*
                                                    │
                                                    └── ProviderHostServices（workspace / run facade / db）

前端 SPA
  sidebar 动态入口 “文件审核”
        └── 路由 /ext/audit-report/file-audit
              └── <iframe src="/api/ui/extensions/audit-report/file-audit/index.html">
                     └── fetch("/api/providers/audit-report/default/documents")
```

### 3.1 方案选型

| 方案 | 说明 | 结论 |
|---|---|---|
| A. 核心内置文档页 | 不做 provider UI，core 写死页面 | 快，但不满足“provider UI 扩展”，弃用 |
| **B. Provider 静态页 + iframe（推荐）** | provider 自带 `ui/`，core 只做导航与静态托管 | 隔离好、迭代快、core 改动小 |
| C. Provider JS 模块注入主 SPA | 直接 import 第三方 JS 到主文档 | 权限/样式/安全耦合高，弃用 |

采用 **B**。

---

## 4. Core 改动规格

### 4.1 Provider manifest 扩展

`provider.schema.json` 使用标准中的 `extensions` 块（完整字段与规则见 `PROVIDER-EXTENSION-STANDARD.md` 第 4 节）：

```json
{
  "schema_version": 1,
  "provider_type": "audit-report",
  "catalog": {
    "display_name": "文件审核",
    "description": "上传检测/试验报告，执行 19 项合规审核并生成报告。",
    "badge": "AUDIT",
    "icon": "AR",
    "icon_path": "assets/icon.svg",
    "accent": "#1d4ed8",
    "extension_only": true
  },
  "runtime_capabilities": ["documents", "audit"],
  "extensions": {
    "version": 1,
    "requires": { "host": ">=1.0 <2.0" },
    "ui": {
      "assets_root": "ui",
      "nav": [
        {
          "id": "file-audit",
          "title": { "zh-CN": "文件审核", "en-US": "File Audit" },
          "icon_path": "assets/icon.svg",
          "entry": "index.html",
          "access": "user",
          "layout": "full",
          "order": 10
        }
      ]
    },
    "api": { "manifest": "runtime-api.json" }
  },
  "config_schema": { "fields": [] }
}
```

`runtime-api.json` 使用标准 v1 格式（`version` + `routes[]`，支持 `response: json|binary`、超时和 body 上限）。

### 4.2 新增 Core 模块

| 文件 | 职责 |
|---|---|
| `app/atlasclaw/api/service_provider_schemas.py` | 解析标准 `extensions` 块与 `catalog.extension_only`；`ProviderSchemaDefinition` 增加 `extensions` |
| `app/atlasclaw/core/provider_extension_registry.py`（新） | 聚合 nav/api/jobs 等扩展点；`list_nav_for_user()`、`resolve_asset()`、`resolve_api()` |
| `app/atlasclaw/api/routes_ui_extensions.py`（新） | `GET /api/ui/extensions`、`GET /api/ui/extensions/{provider}/{nav}/{asset:path}` |
| `app/atlasclaw/api/provider_http_routes.py` | 支持 `Response`/`StreamingResponse`；应用路由级超时/body 上限 |
| `app/atlasclaw/core/provider_registry.py` | `extension_only` provider 注册隐式 `default` 实例 |
| `app/atlasclaw/core/provider_host_services.py`（新） | 标准 Host Services v1：`data_dir`、`agent.run_skill/start_run/events/cancel`、`emit_event` |
| `app/atlasclaw/core/provider_agent_host.py`（新） | 把 `selected_capability` 钉住技能 + `init_run`/`execute_agent_run` 包装成 provider 可用的 Agent Host；提供事件缓冲与产物收集 |
| `app/atlasclaw/tools/validate_provider.py`（新） | 标准一致性校验 CLI + JSON diagnostics |

### 4.3 UI 导航与静态托管 API

```
GET /api/ui/extensions
→ 200
{
  "items": [
    {
      "provider_type": "audit-report",
      "nav_id": "file-audit",
      "label": "文件审核",
      "route": "/ext/audit-report/file-audit",
      "asset_base": "/api/ui/extensions/audit-report/file-audit/",
      "icon_url": "/api/ui/extensions/audit-report/file-audit/../assets/icon.svg",  // 或独立 icon 路由
      "order": 10
    }
  ]
}
```

```
GET /api/ui/extensions/{provider_type}/{nav_id}/{asset:path}
```

- 仅允许 `entry` 所在目录 `ui/` 下的文件；`/` 默认映射 `index.html`。
- 禁止符号链接、`..`、空字节；路径解析后必须仍在 `ui/` 内。
- MIME 白名单：`html/js/css/svg/png/jpg/webp/woff2/json`；其余 404。
- 响应头：
  - `Cache-Control: private, max-age=60`（HTML `no-store`，便于升级）；
  - `X-Content-Type-Options: nosniff`；
  - `Content-Security-Policy: frame-ancestors 'self'`（页面自身 CSP 由页面定义）。
- 鉴权：走现有登录态；`access=admin` 时校验 `authz.is_admin`。

### 4.4 Provider HTTP 运行时增强

1. **隐式实例**：`extension_only` provider 自动提供 `default` 实例；`ensure_provider_instance_access` 对 `default` 放行（仍校验 provider 权限）。
2. **二进制响应**：`_build_provider_http_response` 允许返回 `starlette.responses.Response`（含 `StreamingResponse`），由 provider 自行设置 `Content-Type/Content-Disposition`；core 只追加 `X-Content-Type-Options: nosniff`，并对 `text/html` 强制 `CSP: sandbox`。
3. **上传**：现有 `Request` 已支持重放 body；Starlette `await request.form()` 可直接解析 multipart。单路由声明 `max_body_bytes`（默认 32 MiB，上限 128 MiB）。
4. **后台任务**：P0 不新增通用队列；provider 在 handler 内 `asyncio.create_task` 启动审核，任务状态写 provider 自有 DB。P1 再抽 `ProviderHostServices.start_agent_run()`。

### 4.5 前端 SPA 改动

| 文件 | 改动 |
|---|---|
| `scripts/app.js` | 启动时 `GET /api/ui/extensions`，构造动态路由 `/ext/:provider/:nav` → `pages/provider-extension.js`；在 `renderSidebar` 后渲染 `#sidebar-provider-nav` |
| `scripts/components/sidebar.js` | 新增 `renderProviderNav(items)`，渲染在“Back to Chat/New Chat”下方，带图标、active 状态、i18n |
| `scripts/pages/provider-extension.js`（新） | 全高 iframe；`sandbox="allow-scripts allow-forms allow-same-origin"`；`referrerpolicy="same-origin"`；加载失败提示 |
| `scripts/router.js` | 无需改动（支持 `:param`） |
| `locales/*.json` | 新增 `nav.fileAudit`/扩展加载错误文案 |

路由与导航关系：

```
左侧栏 [← Back to Chat]
        [文件审核]        ← provider nav
        [会话列表...]      ← 原有
```

`/ext/audit-report/file-audit` 刷新可直接打开；未授权用户导航项不显示，直接访问返回 403 页面。

---

## 5. audit-report Provider 详细设计

### 5.1 包结构

```
providers/audit-report/
  PROVIDER.md
  provider.schema.json
  runtime-api.json
  README.md
  assets/icon.svg
  ui/
    index.html
    app.js
    style.css
  api/
    __init__.py
    handlers.py        # async handler(request, context)
    store.py           # provider 自有 SQLite（sqlite3/线程池）
    service.py         # 上传、解析、审核编排、结果汇总
    report_no.py       # 报告编号提取
  skills/audit-report/ # 从 skills/ 迁入（SKILL.md/scripts/references/test）
  test/
    test_handlers.py
    test_store.py
    test_provider_layout.py
```

迁移策略：

- 新 provider 自带技能后，删除 `atlasclaw-providers/skills/audit-report`，避免同名技能重复注册。
- 旧部署若仍从 `skills_root` 加载 standalone 版本，升级时以 provider 版本为准；文档标注“二选一”。

### 5.2 数据存储

Provider 自有 SQLite：`<workspace>/.provider-data/audit-report/audit.db`（WAL）。
不新增 core 迁移；provider 首次请求自动建库建表。

```sql
CREATE TABLE IF NOT EXISTS audit_documents (
  id              TEXT PRIMARY KEY,
  user_id         TEXT NOT NULL,
  tenant_id       TEXT NOT NULL DEFAULT '',
  file_name       TEXT NOT NULL,
  file_path       TEXT NOT NULL,          -- provider data 相对路径
  extension       TEXT NOT NULL,
  size            INTEGER NOT NULL,
  sha256          TEXT NOT NULL,
  pages           INTEGER,
  report_no       TEXT,
  status          TEXT NOT NULL,          -- pending|running|completed|failed
  run_id          TEXT,
  findings_total  INTEGER DEFAULT 0,
  findings_review INTEGER DEFAULT 0,
  grade_summary   TEXT,                   -- A/B/C 计数或总评
  report_path     TEXT,                   -- 生成的 HTML 相对路径
  error_code      TEXT,
  error_message   TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_documents_owner ON audit_documents(user_id, created_at DESC);
```

文件目录：

```
<workspace>/.provider-data/audit-report/<tenant>/<user>/documents/<id>/original.pdf
                                                    /report.html
                                                    /evidence/*.png
```

审核执行时复制到 `users/<uid>/work_dir/audit/<id>/`（技能脚本需要 work_dir 沙箱），完成后把 HTML/证据拷回 provider 数据目录。

### 5.3 后端 API

前缀：`/api/providers/audit-report/default`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/documents` | 列表：`q`（文件名/报告编号）、`status`、`page`、`page_size`、`order=created_at_desc` |
| POST | `/documents` | multipart 上传（`file`、可选 `report_no`、`auto_audit`），返回文档记录 |
| GET | `/documents/{document_id}` | 详情 + 结果摘要 |
| POST | `/documents/{document_id}/audit` | 启动/重试审核，返回 `run_id` |
| GET | `/documents/{document_id}/file` | 原文件（下载/内联预览） |
| GET | `/documents/{document_id}/report` | HTML 审核报告（`inline`） |
| DELETE | `/documents/{document_id}` | 删除记录与文件 |
| GET | `/documents/{document_id}/events` | （P1）SSE 进度；P0 用 3s 轮询详情 |

响应示例：

```json
{
  "id": "9f1c...",
  "file_name": "仪表板装饰件检测报告.pdf",
  "report_no": "RPT-2026-0214",
  "pages": 12,
  "size": 2048576,
  "status": "completed",
  "findings_total": 13,
  "findings_review": 4,
  "grade_summary": {"A": 9, "B": 4, "C": 0},
  "created_at": "2026-11-24T10:32:00Z",
  "updated_at": "2026-11-24T10:35:12Z",
  "actions": ["view_result", "download_report", "reaudit"]
}
```

状态机：

```
pending ──audit──► running ──ok──► completed
   │                  │
   │                  └──error──► failed ──audit──► running
   └──auto_audit──────────────────▲
```

### 5.4 审核执行

**P0（推荐）**：handler 内通过 Host Services 调用 agent（标准 6.5）：

```python
handle = await context.host.agent.run_skill(
    skill_id="audit-report",
    prompt=f"请使用 audit-report 技能审核 {file_name}，生成完整 HTML 报告",
    files=[ProviderFileRef(path=doc_path, name=file_name, mime="application/pdf")],
    session=ProviderSessionSpec(kind="ephemeral"),
    timeout_seconds=1200,
    metadata={"document_id": document_id},
)
```

执行步骤：

1. 复制原文件到 provider 数据目录，登记 `pending`；
2. 调用 `host.agent.run_skill(skill_id="audit-report")`：
   - **显式钉住技能**，路由不得改选其他技能；
   - 使用隐藏会话 `agent:main:user:<uid>:provider:audit-report:<job>`；
   - 文件由 host 复制进 run work_dir，技能脚本按原有沙箱规则执行；
3. provider 订阅 `handle.events()`：
   - `phase`/`assistant_delta` → 写入 `progress`（0-100）与阶段文案；
   - `tool_started/finished` → 记录阶段（提取/取证/校验/渲染）；
4. `run_finished` 后从 `snapshot.artifacts` 取 HTML 报告与证据，复制到 `data_dir/runs/<run_id>/`，状态置 `completed`；
5. `run_failed/cancelled/timeout` 写 `error_code`，状态 `failed`，允许重试；
6. 核心重启导致的中断统一标记 `host_restarted`。

**不允许**的可选实现（不推荐）：浏览器直接调 `/api/agent/run`，provider 只存 run_id。缺点：刷新/关页丢失状态、绕过 provider 权限边界、无法保证技能钉住。

`context.host.agent` 的完整语义（skill pinning、文件、会话、事件、产物、限额、错误码）见标准 6.5 节；provider 侧不得自行调用 `AgentRunner` 或构造 `APIContext`。

**5.4.1 实现修订（2026-11-24）**：单次 `run_skill` 跑完整文档已被证明不可靠
（66 页 PDF 时模型把全部轮次用于试探文本提取，最后无报告）。实际实现改为
provider 驱动的确定性管道：

1. provider 自己调用 `extract_report.py --no-images` 预提取文本，不把 PDF 交给模型；
2. 文本按页切成 ≤60k 字符片段（最多 8 段），19 条规则均分为 3 批；
3. 每个「片段 × 规则批」调用一次无技能、无工具的 `agent.start_run()`，要求只返回
   一个包含每条规则判定的 JSON；
4. 缺规则/解析失败自动补跑（最多 3 次），仍缺少则该规则记 `REVIEW`；
5. provider 合并判定、生成 Markdown + `verification.json`，再用
   `render_report.py --delivery` 渲染 HTML。

这样报告生成不再依赖模型一次跑完全流程：只要文档有文本层就一定产出可下载报告；
无文本层（扫描件）直接失败为 `no_text_layer`（运行时无 OCR）。印章/签名/照片类
规则在纯文本管道下记为 `REVIEW`。

### 5.5 前端页面规格（iframe 内）

布局对齐截图：

```
文档处理                                     [↑ 上传文档]
─────────────────────────────────────────────────────
[上传列表] [审核结果]
[搜索文件名或报告编号] [全部状态 ▾] [上传时间 ▾]
─────────────────────────────────────────────────────
文档名称 | 报告编号 | 上传时间 | 处理状态 | 审核结果 | 操作
📄 仪表板装饰件检测报告.pdf | RPT-2026-0214 | 11-24 10:32 | ● 审核完成 | 13 条问题 · 4 条待复核 | 查看结果
📄 前保险杠尺寸检测报告.pdf | RPT-2026-0213 | 11-24 10:28 | ● 审核中 | — | 查看进度
📄 车门内饰件来料报告.pdf | — | 11-24 10:25 | ● 待审核 | — | 开始审核
共 5 份文档
```

交互：

- 上传：拖拽/选择，多文件；上传后 `status=pending`；`auto_audit=true` 时自动置 `running`。
- 筛选：q 防抖 300ms；状态/时间本地或服务端过滤（P0 服务端）。
- 行操作按状态：
  - `pending`：开始审核 / 重新上传 / 删除
  - `running`：查看进度（弹窗/进度条 + 当前阶段文案）
  - `completed`：查看结果（摘要 + 问题列表 + 打开 HTML 报告）
  - `failed`：重新上传 / 重试
- 结果页签“审核结果”：按等级/规则筛选，展示证据缩略图；点击图片放大；`打开完整报告` 用 `/report?inline=1` 新窗口。
- 空态/加载态/错误态；所有文案 zh-CN/en-US。
- 轮询仅在有 `running` 文档时开启，页面隐藏时暂停（`visibilitychange`）。

### 5.6 报告编号提取

- 上传后读取 PDF/DOCX 前 3 页文本；
- 正则优先级：`报告编号[:：]\s*([A-Za-z0-9\-\/]+)`、`RPT-\d{4}-\d{4}`、`JC-\d{4}-\d{7}[A-Z]?`；
- 找不到留空，UI 允许手工编辑（P1）；
- 提取结果只用于列表展示/搜索，不参与审核判定。

---

## 6. 权限与安全

| 项 | 规则 |
|---|---|
| 导航可见性 | `ui.nav[].access` + RBAC；未授权不返回、不显示 |
| UI 静态资源 | 仅 provider `ui/` 目录；禁 `..`/符号链接；MIME 白名单 |
| Provider API | 沿用 `/api/providers/...` 登录态 + `ensure_provider_instance_access`；文档操作二次校验 `user_id` |
| 文件读取 | `O_NOFOLLOW`；解析后路径必须在 provider 数据目录内 |
| HTML 报告 | 内联时强制 `CSP: sandbox`；禁止脚本访问父页面 |
| iframe | `sandbox="allow-scripts allow-forms allow-same-origin"`；`frame-ancestors 'self'` |
| 上传限制 | 单文件 20 MiB（与聊天附件一致）；单用户总量默认 500 MiB，超出返回 413 |
| 任务隔离 | 每个文档一个 `asyncio` 任务；同文档并发审核拒绝（409） |
| 审计日志 | 记录 upload/audit/download/delete 的 user、doc、时间、结果码 |

信任模型：provider 包由管理员安装，其 Python 在 core 进程内执行，视为受信代码；UI 虽在 iframe 中，但同源，安全边界依赖 CSP 与路径校验。

---

## 7. 需求规格（Spec）

### 7.1 Core（MUST）

| ID | 需求 | 验收 |
|---|---|---|
| C-01 | `provider.schema.json` 支持 `ui.nav`，非法 manifest 启动时告警并跳过该 provider | 单测：缺字段/非法路径/绝对路径均被拒绝 |
| C-02 | 启动后 `GET /api/ui/extensions` 返回已授权 nav，含 route 与 asset_base | 接口测试：admin/user 可见性不同 |
| C-03 | 静态资源路由只能访问 `ui/` 下文件，路径穿越返回 404 | 单测：`../`、绝对路径、符号链接 |
| C-04 | `extension_only` provider 自动获得 `default` 实例 | 接口测试：未配置 service_providers 也能调通 |
| C-05 | provider handler 可返回 `Response`/`StreamingResponse` | 单测：HTML/PDF 下载头正确 |
| C-06 | 无 `ui` 的 provider 行为不变 | 回归测试 |
| C-07 | 左侧导航渲染 provider 入口并支持 active 状态 | 前端测试：渲染/点击/刷新 |

### 7.2 audit-report provider（MUST）

| ID | 需求 | 验收 |
|---|---|---|
| A-01 | 上传 PDF/DOCX 成功，返回记录与 `pending` 状态 | API 测试 + 真实文件 |
| A-02 | 列表支持 q/status/分页，按创建时间倒序 | API 测试 |
| A-03 | 开始审核后状态 `running`，完成后 `completed` 且写入报告路径 | 集成测试（mock run） |
| A-04 | 审核失败记录 `failed` + 错误码，可重试 | 集成测试 |
| A-05 | 报告 HTML 可内联打开（CSP sandbox），原文件可下载 | 接口测试头字段 |
| A-06 | 用户只能访问自己的文档；跨用户 404 | API 测试 |
| A-07 | 删除文档同时删除文件与记录 | API 测试 |
| A-08 | 页面展示 6 列、状态徽标、按状态操作、轮询进度 | 手工验收 + DOM 测试 |
| A-09 | 页面在 1280×720 及以上无横向滚动，支持中英文 | 手工验收 |
| A-10 | 审核报告问题数/待复核数与 HTML 一致 | 与 `verification.json` 比对 |

### 7.3 SHOULD

- S-01：SSE 进度替代轮询；
- S-02：批量上传与批量审核；
- S-03：管理员“全部文档”视图；
- S-04：报告编号手工编辑与去重提示；
- S-05：保留期清理任务（默认 90 天）。

---

## 8. 测试计划

| 层 | 内容 |
|---|---|
| Core 单测 | manifest 解析、nav 权限过滤、静态路径穿越、隐式实例、Response 透传 |
| Provider 单测 | store CRUD、状态机、报告编号正则、路径安全、404/409/413 |
| Provider 集成 | 上传→审核（mock agent run）→完成→报告读取；失败重试 |
| 前端 | nav 渲染、路由跳转、iframe 加载失败提示；页面 DOM 渲染（jsdom） |
| E2E | 部署环境真实上传一份 PDF，等待完成，打开 HTML 报告；核对问题数与 `verification.json` |
| 回归 | 无 `ui` 的旧 provider（jira/SmartCMP）启动与技能加载不受影响 |

---

## 9. 实施阶段

| 阶段 | 内容 | 预计 |
|---|---|---|
| P0-1 | Core：manifest `extensions` + 隐式实例 + 静态路由 + Response 透传 | 2d |
| P0-2 | Core：Host Services + Agent Host（技能钉住、事件、产物、取消/超时） | 2.5d |
| P0-3 | Frontend：动态 nav + `/ext/...` + iframe + bridge | 1d |
| P0-4 | Provider：包结构、store、上传/列表/详情/删除、报告编号 | 2d |
| P0-5 | Provider：`host.agent.run_skill` 审核编排 + 进度 + 结果汇总 | 2d |
| P0-6 | UI 页面（上传/列表/筛选/状态/结果） | 2d |
| P1 | SSE、批量、保留期、管理员视图、编号编辑 | 2d |
| 测试/部署 | 单测/集成/E2E/文档/153 环境验收 | 1.5d |

合计约 **15 人日**（P0 约 11.5 人日）。

---

## 10. 风险与待确认

| 风险 | 影响 | 缓解 |
|---|---|---|
| `asyncio` 任务随重启丢失 | 运行中文档卡住 | 启动时把 `running` 标记 `failed`，提示重试；P1 换任务表 |
| 单 worker 长任务占资源 | 并发审核变慢 | 限制单用户并发 1；任务超时 15 分钟 |
| provider Python 与 core 版本耦合 | 升级需同步 | 通过 `ProviderHostServices` 窄接口，避免直接 import 内部模块 |
| iframe 同源脚本 | 恶意 provider 可访问父页 | 只安装受信 provider；后续可改为独立子域/沙箱 |
| 与聊天附件的重复存储 | 磁盘翻倍 | 审核文件单独存储，聊天附件不参与；保留期清理 |
| 旧 standalone audit-report 重复 | 技能重复注册 | 迁移时删除 `skills/audit-report` 并在 README 标注 |

**待确认（以下均为标准 v1 的默认值）**

1. UI 方案：**iframe 静态页 + bridge 协议**（标准 v1 固定） / 不建议改。
2. 审核执行：**后台 agent run（Host Services）**（推荐） / 浏览器驱动 run。
3. 列表范围：**按用户隔离**（推荐） / 管理员默认看全量（v2 再定）。
4. 技能迁移：**迁入 provider 并删除 standalone**（推荐） / 保留两份。
5. 存储：**provider 自有 SQLite**（推荐） / 新增 core 表（v2 再评估）。

确认后输出实施任务清单（tasks.md），按 P0-1 → P0-5 顺序落地；新增 provider 一律复用标准，不再写一次性方案。
