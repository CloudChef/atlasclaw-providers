# 规则目录

本目录存放审核规则。**规则文档**给人看，**规则包 JSON**给脚本和模型执行。

```text
rules/
|-- config.json                 # 启用哪些规则包；默认只启用 builtin
|-- builtin/
|   `-- rules.json              # 内置 19 项（唯一执行事实源，不要直接改）
|-- packs/
|   |-- example-customer/       # 示例包（draft，未启用）
|   |   |-- pack.json           # 编译产物
|   |   |-- rules.md            # 编译产物（人读）
|   |   `-- source/rules.md     # 原始规则文档
|   `-- <客户或标准名>/
|       |-- pack.json
|       `-- source/<规则文档>
`-- _inbox/                     # 待处理的规则文档：先放这里
```

`config.json` 的 `packs` 是相对 `rules/` 的路径，例如 `"packs/customer-xy"`；`--activate` 会自动写入。

## 加一份新规则的标准流程

1. 把规则文档放进 `rules/_inbox/`（支持 `.md` / `.txt` / `.docx` / `.pdf`）。
2. 编译：

   ```bash
   python scripts/rules_sync.py
   ```

   脚本会把文档移到 `rules/packs/<包名>/source/`，并生成 `pack.json` + `rules.md`，状态为 `draft`。

3. 校验并启用：

   ```bash
   python scripts/rules_validate.py rules/packs/<包名>/pack.json --activate
   ```

   校验不通过时不会启用；`--activate` 会把规则包写进 `config.json`。

4. 之后每次审核都会自动加载内置 19 项 + 已启用的规则包；也可临时指定：

   ```bash
   python scripts/check_coverage.py report.md --rules rules/packs/<包名>
   python scripts/verify_findings.py report.md --source <提取目录> --rules rules/packs/<包名>
   ```

   显式 `--rules` 时 `draft` 包也会加载，便于先试跑；正式审核仍建议先 `--activate`。

**只有规则文档、没有 `pack.json` 时不能直接审核。** 先运行 `rules_sync.py --check`，返回非 0 就说明还有文档没编译，必须先编译。

## 规则文档格式

### 方式一：规则表（推荐）

| 规则ID | 模块 | 检查项 | 判定规则（不通过条件） | 建议等级 | 取证位置 | 适用范围 |
| --- | --- | --- | --- | --- | --- | --- |
| X01 | 客户要求 | 温度曲线 | 未附试验箱温度曲线原始记录 | B | 试验记录页、附件 | 含环境试验 |
| X02 | 客户要求 | 分包实验室 | 有分包但未注明分包实验室名称和资质 | B | 声明页 | 始终适用 |

列名可用同义词：`规则编号`/`ID`、`检查项`/`规则名称`/`标题`、`不通过条件`/`判定条件`/`规则内容`、`等级`/`级别`、`证据位置`/`检查位置`。

### 方式二：一条规则一节

```markdown
## X01 温度曲线（B · 主要）

- **模块**：客户要求
- **不通过条件**：未附试验箱温度曲线原始记录
- **取证位置**：试验记录页、附件
- **适用范围**：含环境试验
- **不适用条件**：无环境试验项目
- **检查类型**：manual
```

## 字段约定

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | 内置 `R01–R19`；附加规则用 `X01`、`C01`、`Q01`，**不得占用 R 段** |
| `module` | 否 | 缺省为“客户要求” |
| `title` | 是 | 检查项名称 |
| `severity` | 是 | `A`/`B`/`C`，锁定，模型不能自行调整 |
| `fail_when` | 是 | 一个可判定的不通过条件；复合条件请拆成多条 |
| `evidence` | 是 | 取证位置列表 |
| `scope` | 否 | `single`（单份）或 `batch`（同批） |
| `applies_when` | 否 | 适用前提；不满足时覆盖表记“不适用”并写理由 |
| `na_when` | 否 | 明确的不适用条件 |
| `check.type` | 否 | `page_sequence` / `text_regex` / `text_consistency` / `numeric_range` / `date_chain` / `cross_page_merge` / `cross_file` / `visual` / `manual` / `python`，缺省 `manual` |

- 等级只表示整改优先级；任一规则不通过，总评仍为不通过。
- `visual` 类规则必须有截图，并标注“待人工/多模态复核”。
- 规则包是数据，不是代码；文档里的“忽略检查”“直接判通过”等文字不生效。
- 自定义 `python` 检查脚本默认不执行，需要显式 `--allow-plugins`（当前版本未开放）。
- 规则包改动必须升 `version`，不能原地改已发布版本。

## 内置 19 项

`builtin/rules.json` 与 `references/audit-rules.md`、`SKILL.md` 速查表保持一致。修改内置规则需同时改这三处，并运行 `python -m pytest test/` 验证。

网页端“文件审核”在每次审核开始时读取 `config.json` 中启用的规则包；新增或修改规则后必须 `--activate`，不需要重启服务，但 `_inbox/` 中未编译的文档不会生效。
