# Changelog

## 0.1.5 — 2026-10-29
- 新增 `research.py review-log`（scripts/review_log.py）：每次例行运行向 RUNTIME/review_runs.jsonl 追加一行，含 run_started_at/run_finished_at（UTC 秒 + 曼谷）、doctor_status、due_ids、逐项 outcome（reviewed/pending_data/failed；无到期为 none）、execution_agent/model（缺省 unknown）、errors。doctor 或 due 失败也照写。
- collect：`request(meta=)` 在发起请求时记录 fetched_at（ISO 8601 UTC 秒）和响应 Date 头；fetch_one 记录 fetched_at、http_date、time_precision=second（retrieved_at 保留）。import_native 记录 time_precision（显式或按时间串推断 second/minute；file_mtime 需显式声明）。ledger 接受 claim fetched_at 与证据 retrieved_at 或 fetched_at 一致，并校验 time_precision 取值。
- 旧账本、报告、收据不改；GANG 两项复算和旧判断时间精度问题以勘误追加。
- 测试新增 6 个。

## 0.1.4 — 2026-10-29
- WATCH 基线：WATCH 必须有 reference_quote 或 baseline_gap、assertions 或 no_assertion_reason、signal_window/valid_until；assertion 必须有 check_by。复盘 outcome 新增 counts_toward_hit_rate、event_status、events；stats 新增 WATCH_tracking，不进 BUY/SELL 胜率。旧记录不受影响（只在新登记时校验）。
- 安全检查四态：有 asset 的记录必须给 safety_checks，八项齐全，状态为 checked_none_found/confirmed_risk/unverified/not_applicable；前两态需 method+evidence_refs，后两态需 note。模板同步。
- 证据来源可用 file:///（文件必须存在），用于本地证据；supersedes 必须指向已存在的 decision。
- references/models.md 去掉 --dangerously-bypass-approvals-and-sandbox，改用新增的 scripts/codex_step.py（workspace-write、stdin 置空、--json 解析 token，拿不到写 unknown，记 steps.jsonl）。
- install.verify 要求 manifest 含 references/models.md 和 VERSION，并拒绝含绕过参数的 models.md；doctor 新增 manifest 检查，失败即 degraded。
- 测试新增 8 个。新版 SKILL.md 在 /workspace/crypto-research/staging-0.1.4/，等待注册（已安装的 SKILL.md 未改）。

## 0.1.3 — 2026-10-29
- 复核异议关卡：`record` 要求有 `review_objections[]`；每条要么 adopted（附 summary_change 和 ledger_change），要么 retained（附 retention_reason），有未处理异议时拒绝登记。如果没有复核，必须写 `review_objections_none_reason`。
- 结论级证据：`claims[]` 中每个来源都要有 source_url、observed_at（或 null 加理由）、fetched_at、raw_path（文件必须存在）；fetched_at 要与证据包的 retrieved_at 一致。新增 `data_cutoff` 和 `analysis_completed_at` 两个字段，要求 fetched ≤ cutoff ≤ as_of ≤ completed。
- 新增 `errata` 子命令和账本 record_type=erratum，只追加，不改原条目；`due` 输出附带 errata 列表。
- 测试新增 4 个；fixture `decision()` 补上了新必填字段。
- SHA256SUMS 加入 references/models.md 和 CHANGELOG.md。新版 SKILL.md 在 /workspace/crypto-research/staging/，等待注册。
