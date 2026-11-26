# 任务系统约定
{{SYSTEM}}

---

# 文本证据边界
{{TEXT_EVIDENCE}}

---

# 本次任务：分段识别项目目录证据
{{CHUNK_CONTRACT}}

---

# 全文和分段元数据
全文实际物理页数：{{PAGE_COUNT}}
分段序号：{{CHUNK_INDEX}}/{{CHUNK_COUNT}}
本段正式页范围（须由segments与non_project_pages页范围分类完整覆盖）：{{FORMAL_PAGE_NUMBERS}}
仅作续接上下文、不得计入上述正式页范围分类：{{CONTEXT_PAGE_NUMBERS}}

---

# 相邻页上下文文字（仅用于判断分段边界是否续接）
本区包含可用的前一页和后一页，但均不属于当前分段的正式审核页，不能据此重复覆盖或改写项目边界。
<CONTEXT_PAGES>
{{CONTEXT_TEXT}}
</CONTEXT_PAGES>

---

# 上一段已校验扫描原文（仅用于稳定跨段项目标识）
以下原文不属于本段正式页；不得把它计入本段正式页分类。
若当前段续接其末尾项目，沿用相同id和title；若不续接，按本段证据识别新项目。
<PREVIOUS_SCAN_RAW>
{{PREVIOUS_SCAN_RAW}}
</PREVIOUS_SCAN_RAW>

---

# 当前分段全部正式页原生文本
不得省略任何页或把报告印刷页码当物理页码。
<FORMAL_PAGES>
{{FORMAL_TEXT}}
</FORMAL_PAGES>

---

# 输出限制
只输出分段合同要求的JSON对象，不输出分析过程、完整报告、规则表或业务审核结论。
