# configs/skills/ — Finer-Skill 可调面配置

本目录存放[自进化 Skill 模式](../../docs/specs/2026-06-30-self-evolving-skill-pattern.md)中、当前**硬编码在 Python 里、待外置**的 Skill 可调参数（F2 / F3-F4-F5）。

约定：

- 已有 YAML 化的 Skill（`dpo` / `kol_scorer` / `backtest`）继续留在 `configs/ml_models.yaml`，**不搬到这里**。本目录只收当前硬编码的阈值。
- 本目录文件是**可调面声明**：当前值镜像源码硬编码值，并以 `# SOURCE:` 注释指向真相位置。
- ⚠️ **尚未 wire**：这些文件目前**没有任何代码读取**。把源码改成从这里加载是模式路线图 M3 的工作，迁一个验证一个，不得一次性切换。
- 迁移某个阈值时：先让源码从这里加载（保持默认值不变、行为不变），再把该阈值从「硬编码」标记改为「已 wire」，并补一个「config 值 == 旧硬编码值」的回归测试。

| 文件 | Skill | 覆盖 |
|---|---|---|
| `f2-entity-anchoring.yaml` | `f2-entity-anchoring` | LLM 候选提议元参 + 命中率基线 + stoplist 真相源指针 |
| `f3f4-policy.yaml` | `f3f4f5-policy` | F3 conviction/confidence 阈值 + F4 仓位桶/风控阈值 |
