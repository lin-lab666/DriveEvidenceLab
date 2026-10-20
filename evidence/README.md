# DriveEvidenceLab 证据束（Evidence Bundle）

本目录存放可公开分发的实验证据，供第三方独立核验。
原始 `runs/` 目录不入库（体积大且可由脚本重新生成）；这里给出的是**压缩后的完整证据包**。

## 文件

| 文件 | 内容 | 大小 |
|---|---|---|
| `gateE-v2p1-full.tar.gz` | 协议 v2.1（`builtin/1.1`）正式实验的**完整**证据包：128 份 discovery 报告、128 份 holdout 明细、384 份扰动运行记录、归档 episodes、`ledger.jsonl`、`manifest.json`、`summary.json`、`selection.json`、`audit.json`、`seed_coupling.json`、`report.md` | ~784 KB |
| `gateE-v1-holdout-summaries.tar.gz` | 协议 v1 的 holdout 明细（逐候选 `summary.json` 与逐种子记录），用于独立复核「1716/1716 候选在 3 个"独立"种子下逐位相同」这一审计结论 | ~591 KB |
| `SHA256SUMS` | 上述两个压缩包的 SHA-256 | — |

两个压缩包都是**确定性**的：条目按路径排序，所有条目 `mtime=0`、`uid=gid=0`、属主名清空，
gzip 头 `mtime=0`。因此从相同输入重建会得到**逐位相同**的 SHA-256，发布物可被独立复算。

## 一条命令核验

```bash
python scripts/verify_evidence_bundle.py
```

该脚本会：

1. 校验 `SHA256SUMS`；
2. 解压到临时目录（不污染工作区）；
3. 重走 `ledger.jsonl` 哈希链；
4. 逐文件比对 `manifest.json`；
5. 从原始逐 seed 报告与逐候选明细**重算** discovery yield、stable yield、Wilson 区间、Fisher 精确检验、Newcombe 区间、Holm 校正，并与 `summary.json` 的记录值比对，任一漂移即 FAIL；
6. 重算 v1 holdout 的「逐位相同」候选数（若为 0 则判定证据包缺数据并 FAIL）；
7. 打印 T1（内部一致性）/ T2（方法学有效性）/ T3（外部复现）三层结论，末尾给出 H1/H2/H3 的支持与否。

## 从零重新生成（而不是核验）

```bash
PYTHONPATH=src python scripts/run_formal_experiment_v2.py --out runs/formal_experiment_v2p1
PYTHONPATH=src python scripts/audit_scientific_validity.py
PYTHONPATH=src python scripts/audit_seed_coupling.py
python scripts/build_evidence_bundle.py            # 重建两个压缩包与 SHA256SUMS
python scripts/build_evidence_bundle.py --check    # 只校验磁盘上的包是否等于新构建结果
```

在同一环境下应得到逐位相同的 `summary.json` 数值（bootstrap 固定 seed=2026）与逐位相同的压缩包哈希。

> 注意：证据束中的 v2.1 结果是在 `builtin/1.1` 下产生的。若用 `builtin/1.0` 重跑，会复现
> v2.0 的数值（random 0.9375 / mutation 0.9531），因为 1.0 的 `NEAR_MISS` 分支不可达（D017）。
> 两次运行均保留在 `runs/` 中，未覆盖、未择优。

## 边界声明

- 证据束证明的是**内部一致性**（T1）与**本机可复现性**，不证明结论已被外部独立验证（T3）。
- 哈希链完整 ≠ 实验为真 ≠ 方法有效。三者是不同层级，详见 `docs/SCIENTIFIC_AUDIT.zh-CN.md`。
- 两方法搜索 RNG 存在耦合（4/64 对完全退化、median 16/64 场景重合），已在
  `seed_coupling.json` 与审计报告 §10.4 中披露；偏差方向使 H3 更保守。
