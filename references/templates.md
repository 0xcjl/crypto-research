# 报告与模型记录

## 报告骨架

标题：标的＋研究日期/时间（Asia/Bangkok，同时注明数据UTC时间）

- 执行：实际Agent、可核实模型或unknown、skill版本、模式/深度、研究问题。
- 身份：项目官网、链/合约或native_id；交易池另列；无币项目说明代币状态。
- 核心判断：先回答用户问题，每条结论带URL/evidence_id、数据时间；推断有依据与反证。
- 项目画像与发展：做什么、谁用、可验证进展/用户、团队/资金/商业机制、竞争。
- 适用的链上变化：指标、前值/后值、窗口/单位/范围、来源、潜在解释和反证；无前值建基线。
- 代币机会：流动性、注意力、筹码分别给证据和判断；注意力项目在此之前先给排雷结果。
- 风险与信号：风险等级及最弱环节；信号、适用周期、有效期、触发/失效、条件区间依据、退出限制；无币为NOT_APPLICABLE。
- 最强反方与缺口：哪些事实会改变结论，下一步复查什么。
- 来源表：ID、原文链接、来源/采样数据时间、取得时间、口径/限制、事实或自述/估计/推断。
- 复盘登记：decision_id、30/90到期时间、报告位置。只有record成功后才称已登记。

纯项目研究按适用性收缩，不机械填价格表；quick保留身份、结论、风险、来源与缺口。可使用表格，但每个关键判断仍有证据及时间。实测数据、模拟测试、分析判断、已调度任务分别说明状态。

## 模型判断JSON

以下是字段约定，不是真实信号；值由模型根据实际证据填写：

```json
{
  "decision_id": "unique-safe-id",
  "authored_by": "model",
  "execution_agent": "actual agent",
  "model": "actual model or unknown",
  "as_of": "ISO timestamp with timezone",
  "target_name": "verified project/token name",
  "asset": {"chain": "chain", "native_id": "native-asset-id"},
  "signal": "WATCH",
  "risk": "unknown",
  "signal_window": "research horizon",
  "valid_until": "ISO timestamp with timezone",
  "thesis": "model's evidence-based judgment",
  "invalidation_conditions": ["specific falsifying condition"],
  "recheck_conditions": ["specific measurable condition"],
  "evidence_refs": ["existing successful evidence IDs"],
  "reference_quote": null,
  "benchmark": null,
  "benchmark_gap": "reason for not using a benchmark, when applicable",
  "assertions": [{"id": "event-1", "condition": "event/metric, horizon, threshold and scope defined beforehand", "evidence_refs": ["source-id"]}],
  "report_path": "saved report path"
}
```

代币用asset.address替代native_id；不得同时填两个。无币项目asset=null、signal=NOT_APPLICABLE，reference_quote=null。对更新增加supersedes指向旧decision_id。

BUY/SELL必须填新鲜reference_quote：asset、price（正数USD）、currency=USD、observed_at、venue、instrument、evidence_refs。benchmark如适用为asset+reference_quote；默认非BTC资产用BTC衡量大盘背景，可另列事先确定且历史数据可靠的同类基准。BTC没有可靠外部基准时明确benchmark_gap，不用BTC自己作基准。不得事后换基准。

模型记录signaling窗口和valid_until；未触发条件的研究写WATCH，而不是先登记成BUY再事后挑选成功触发案例。assertions事先写可观察的事件/阈值/截止期；没有可验证主张可留空数组，不能事后补写原预测。
