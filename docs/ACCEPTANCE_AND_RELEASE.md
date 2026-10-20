# DriveEvidenceLab｜验收、质量门与 GitHub 开源清单

## A. 多 Agent 真实性
- [ ] 提供成员列表、角色、各自上下文/会话或独立任务的实证
- [ ] 共享任务板记录每个任务的负责人、依赖与状态
- [ ] 可追溯的 reviewer 审查和修复记录；并行时避免同文件覆盖
- [ ] 若本机版本不支持真实多 Agent，明确声明及替代实施方式

## B. 工程可用性
- [ ] 清洁环境安装成功，适用于至少一个明确注明版本的 Windows 或 Linux 环境
- [ ] README 的 copy-paste quickstart 在空工作区真实成功
- [ ] `doctor` 报环境诊断，不提供虚假绿色
- [ ] `run` 使用真实仿真器运行，产生可复现实验的原始 evidence pack
- [ ] `replay` 成功复现**至少一项被观察结果**，失败差异需如实披露
- [ ] 可安装包有版本、许可证、源码分发和测试
- [ ] CI 有单测、性质测试、协议校验、lint/typecheck，真实仿真集成测试有独立标签

## C. 研究可信度
- [ ] 相关工作与新贡献边界有真实可点击、可核验的来源
- [ ] 事前注册的假设、种子、主指标、预算、失败计费、holdout
- [ ] 冻结协议之后才执行正式实验，不 cherry-pick seeds
- [ ] 记录所有已发起 episode 及失败/未知/取消
- [ ] 主要表格和图可以从已存 evidence 一键重生成
- [ ] 采用独立 holdout；区分探索性与验证性发现
- [ ] 主结论带置信区间/适当不确定性描述与足够样本信息
- [ ] 报告真实零结果、局限和不可比较条件
- [ ] 第二个仿真器要有实际执行证据，否则显式标为后续功能

## D. 数据、许可证、隐私与开源
- [ ] 全新 repository、干净 Git 历史，不复用私有研究档案的 `.git`
- [ ] `.gitignore` 排除 `.env`、keys、credentials、raw private runs、虚拟环境、模型大权重、cache
- [ ] 本地静态扫描和 git 全历史扫描：Token / 邮箱隐私 / 本机绝对路径 / 私人研究内容
- [ ] Apache-2.0（或经依赖审计后的合理许可）、CITATION.cff、THIRD_PARTY_NOTICES
- [ ] README 中英文、CONTRIBUTING、SECURITY、CHANGELOG、docs/PROVENANCE.md
- [ ] 任何第三方资产/数据集有合法分发依据，不能直接拷贝大数据
- [ ] tag 与 Release notes 对应实际验证 commit
- [ ] 首次创建公开仓库/公开 push 前需要一次明确用户确认
- [ ] 只有 GitHub 返回可访问 URL 后才算“已公开发布”

## E. 实验成本与硬件资源门槛
- [ ] 对 GPU、磁盘、时长、API 费用做估算并设默认硬上限
- [ ] 超限先暂停申请批准，不能把工程量不限解释为无限付费
- [ ] 失败自动恢复有限次数，所有重试计费
- [ ] 主/附加实验失败时，保留原始证据并用 NOT COMPLETED 标记

## F. 完成定义（Definition of Done）
- 软件真实可安装可运行；核心任务结果有真实 evidence。
- 不夸大技术或科研结论；项目执行范围清楚。
- GitHub Public Repo、不可变 tag 和 Release 发布成功且 URL 可访问。
- 完成 `docs/FINAL_REPORT.zh-CN.md`，写明真实数值、错误数、限制、运行成本与复现步骤。
- 没完成上述项目时就如实报告，不能自行给出“全部完成”。
