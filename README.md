# Crypto Research

A portable Agent Skill for researching crypto projects, products, protocols, and tokens. Core instructions and reports are Chinese-first. It works with Codex and Hermes and can be installed in compatible cloud agents.

Current version: **0.1.2**. This repository is private; no open-source license is granted.

## Research workflow

- Route natural-language requests, project/token names, addresses, and links to the appropriate research method.
- Cover products without tokens, projects before token launch, established protocols/tokens, and attention-driven tokens. Alpha research is an objective that can overlay those routes.
- Prioritize risk screening for attention-driven projects. Evaluate short-term conditions through liquidity, attention, and ownership/sell-pressure structure.
- Use scripts for collection, rate limiting, deduplication, normalization, and arithmetic. The model interprets evidence, competing explanations, risk, and research signals.
- Attach sources and timestamps, preserve uncertainty, and examine comparable on-chain changes rather than inferring trends from one snapshot.
- Save append-only judgments and support reviews after 30 and 90 days. Research signals never execute trades or wallet actions.

For attention/alpha research without an explicit chain, prioritize **Robinhood Chain and Base**, followed by Sui, BSC, and Solana. Explicit requests for other chains take precedence. Chain scope does not start an automatic scanner.

## Install

Requires Python 3.10 or later; scripts use the standard library. Authenticate to GitHub with access to this private repository, then clone it:

```bash
gh repo clone 0xcjl/crypto-research
cd crypto-research
python3 scripts/install.py
```

Install into a **new** user-level skill directory:

```bash
# Codex
python3 scripts/install.py --target "$HOME/.codex/skills/crypto-research"

# Hermes default profile
python3 scripts/install.py --target "$HOME/.hermes/skills/crypto-research"
```

The installer checks `SHA256SUMS` and refuses an existing different version. Preserve that version before upgrading. Hermes isolated profiles can use separate skill roots; confirm the active profile before installing. Cloud hosts may require native skill registration in addition to copying files.

Codex can discover the skill on the next turn. Open a fresh Hermes session to refresh its skill index.

## Use

Codex:

```text
$crypto-research 研究 Base 上的[代币名或地址]，先排雷，再看流动性、注意力和筹码变化。
```

Hermes:

```text
/skill crypto-research
```

Then ask a research question. Natural-language examples:

```text
帮我快速了解这个项目，它做什么、发展到哪了？
研究这个还没发币的项目，把官方计划与传闻分开。
只看这个币的筹码和最近链上变化，注明来源与时间。
更新上次报告，说明哪些事实和复查条件发生了变化。
```

See [SKILL.md](SKILL.md), [CLI reference](references/cli.md), [chain scope](references/chains.md), and [review methodology](references/review.md).

## Runtime and source access

Keep research reports, raw evidence, caches, and the judgment ledger **outside** the installed skill directory. For example, pass `--runtime "$HOME/.local/share/crypto-research/runtime"` to commands that accept it. Do not commit runtime data or credentials.

Free public data is preferred. Credential-based sources are optional. An X Premium subscription does not itself provide a script API credential or unlimited access; native search tools must be verified separately for each host. Do not copy a cloud host's transport configuration to another machine.

Automatic review scheduling requires the host's scheduler and separate configuration. Installing this skill does not create a local scheduled job.

## Verification

```bash
python3 scripts/install.py
python3 -m unittest discover -s tests -v
python3 scripts/research.py doctor --network
```

Version 0.1.2 passed 23 regression tests in the local Codex and Hermes installations and in the target Grok cloud environment. Actual public-source collection and Robinhood/Sui identity/checkpoint probes were exercised. These checks establish implementation behavior and source access at the recorded time; they do not establish investment performance or complete indexing of every chain.

Fully isolated, fresh-conversation natural-language selection is not yet verified. Thirty-/ninety-day real-world review outcomes were not yet due at initial publication. See [CHANGELOG.md](CHANGELOG.md).

## Method references

This skill was independently written; it does not vendor or execute the referenced repositories' trading runtimes or installation scripts.

- [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents): research dimensions, opposing arguments, and risk review.
- [zubair-trabzada/ai-crypto-claude](https://github.com/zubair-trabzada/ai-crypto-claude): a unified entry point and specialized research dimensions.
- [CnxLuc/token-analysis-skill](https://github.com/CnxLuc/token-analysis-skill): early project, team, narrative, and market-structure questions.

Detailed adaptation choices are in [references/sources.md](references/sources.md).
