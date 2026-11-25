# 规则文档收件箱

把待处理的规则文档放在这里（`.md` / `.txt` / `.docx` / `.pdf`），然后运行：

```bash
python scripts/rules_sync.py --check   # 先检查有没有未编译的文档
python scripts/rules_sync.py           # 编译成 rules/packs/<包名>/pack.json
```

编译后文档会移入 `rules/packs/<包名>/source/`，收件箱只保留本说明。
