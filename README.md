[简体中文](README.md) | [English](README.en.md)

![MKT Max 1 — 从研究判断到完整内容与项目接续](assets/readme-hero.png)

# MKT Max 1

**面向活动项目的 Agent 技能与本地文件运行工具：研究、确定方针、写出完整内容，并让下一次对话接得上。**

适用于策划人员、活动负责人，以及需要审阅或接手方案的内容、设计、执行与商业协作人员。它把需求、来源、决定、正文和变更记录放在可回读的项目文件中，通过一个短中枢导航，而不是依靠聊天摘要保存全部项目知识。

> **当前版本：实验性 1.1.0。** 版本以 [version.json](version.json) 为准。已确认的权限传播、提交状态与单元失效问题尚未修复；使用前请阅读下方「当前状态与已知问题」。当前验证不构成真实岗位、受众或市场效果的证明。

## 解决什么问题

- **研究能交给成稿阶段。** 保留来源原件入口、实际读取范围、有效方针、成立条件和未决问题，避免只交一段无法复核的总结。
- **交付有实质内容。** 根据委托写出完整场景、流程、规则、稿件和接手工作件；目录、排期、状态表和代表稿不能代替约定的全量正文。
- **项目可以接续和局部修改。** 用版本绑定的任务包定位当前正文与依据，沿已登记依赖识别需要重核的内容，保留候选和历史。
- **范围随项目变化。** 初始化不创建一套固定营销模块；先判断什么现在需要、后续需要、本次不需要、尚不能判断，再安排工作。

本包包含技能指令、17 份按需参考文件和 7 个 Python 脚本。**脚本不调用模型、不自动启动 Agent、不提供联网搜索，也不生成原生 Word、PowerPoint 或设计源文件。** 搜索、阅读、判断、创作、图片观察及其他格式制作取决于宿主实际提供的能力。

## 适用范围与按需模块

支持线上、线下、混合活动，单场与系列项目，也支持已有方案的局部交付、审查和修订。研究深度、正文深度与交接方式由接收人的用途决定。

| 项目需要 | 对应工作 |
|---|---|
| 新项目、方向不清或原料不足 | 需求澄清、研究核验、比较、反证、方针与阶段交接 |
| 已有方向，需要能审阅或接手的方案 | 内容单元、参与体验、具体场景、机制规则、完整稿件 |
| 要招募、传播或提供线上服务 | 按实际渠道、入口、承接与服务条件生产工作件 |
| 涉及人员、场地、技术或制作 | 角色与产能、班次、设计交接、执行接口、失败处理 |
| 涉及报价、票务、销售、合作或赞助 | 按需处理费用、交易条件、权益、库存与履约 |
| 多场次、多期内容或共享资源 | 系列关系、日历、资源与成本关联、改期影响 |
| 要评估、收尾或复用经验 | 指标口径、证据、反馈、成立条件与可复用记录 |

营销、销售、Slogan、兼职人员、全套设计、票务、赞助和系列统筹都由真实需求触发。某个案例中的做法不会自动成为所有项目的必选模块。它也不是自动运营、自动发布或自动执行活动的系统。

## 两阶段、中枢与实际正文

**第一阶段：研究、判断与方针确定。** 从委托、人群需要和原料出发，核验关键声明，比较选择，提出最强反证，判断材料是否充分。交接有效方针、原文入口、读取覆盖、条件、未决和第二阶段任务。

**第二阶段：完整内容生产与交付。** 按约定任务写真实正文，说明发生什么、服务谁、看听做什么、如何开始和完成、获得什么，以及依赖与失败处理。已有效的方针直接接续；只有新事实推翻相关判断时，才返回对应研究与决定。

收尾与反馈属于原项目的后续工作，不额外增加第三个写案审批阶段。

项目同时保留三个层次：

| 层次 | 用途 |
|---|---|
| 短中枢 `项目中枢.md` | 当前阶段、模块状态、关键条件和文件入口；用于导航 |
| 原始资料、实际正文与接手文件 | 支撑研究、创作、复核与交付；大正文不全部塞进任务包 |
| 版本、依赖与任务包 | 记录当前基线、输入指纹、变化影响和下一次接续所需入口 |

摘要不能替代原文，目录覆盖不能证明已经阅读。事实、用户决定、创作拟案与效果假设分别表达；文字完成、资源落实、用户批准、外部执行和实绩也分别核验。判断使用高／中／低／未知置信度，模型自评分不作为市场效果证据。

## 安装与运行前提

需要 **Python 3.10 或更高版本**；脚本仅用标准库，无需 `pip install`。通过下列方式获取源码需要 Git，也可以下载仓库归档后解压。

宿主 Agent 还需要：读取完整技能及参考文件、读写项目工作目录、执行本地 Python；开展联网研究时，需要宿主另行提供可用的搜索和页面读取工具。只有文本对话而没有这些能力时，可以参考方法，但不能声称文件已保存、任务包已恢复或命令已执行。

### 1. 获取完整目录

```shell
git clone https://github.com/DONGaOtang/mkt-max-.git mkt-max-1
cd mkt-max-1
python --version
```

本地目录使用 `mkt-max-1`，与 [SKILL.md](SKILL.md) 中的技能名称一致。按宿主自身的技能安装规则，把**完整目录**放入其 skills 目录；或者直接让 Agent 读取本机完整绝对路径下的 `SKILL.md`，例如 `C:/your-path/mkt-max-1/SKILL.md`，并按任务读取相邻参考文件。不同平台的安装、发现与工具权限机制不同，本仓库不提供通用的一键安装器。

### 2. 创建个人配置

以下命令均在仓库根目录运行。[config.example.json](config.example.json) 的 `workspace_root` 是占位值，不能直接用于运行。首次配置执行下面这一整行；它保留示例中的其他字段，将工作根设为用户主目录下的绝对路径，创建目录，并写入已被 Git 忽略的 `config.json`。

```shell
python -c "import json; from pathlib import Path; p = Path.home().joinpath('mkt-max-workspace').resolve(); p.mkdir(parents=True, exist_ok=True); c = json.loads(Path('config.example.json').read_text(encoding='utf-8-sig')); c['workspace_root'] = str(p); Path('config.json').write_text(json.dumps(c, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'); print(p)"
```

该单行命令可在 PowerShell、Windows 命令提示符及常见 POSIX shell 中使用。重新执行会覆盖个人 `config.json`，已有配置请直接保留或编辑。也可自选工作目录，但 `workspace_root` 必须是绝对路径；不要把真实项目资料提交到公开仓库。

### 3. 初始化并读取接续入口

下面两条可以在完成配置后直接运行：

```shell
python scripts/start_agent.py init --name "Demo workshop" --id demo-workshop --config config.json
python scripts/start_agent.py resume --project demo-workshop --config config.json
```

`init` 创建项目和初始版本，不生成方案。`resume` 写出任务包与检查点，返回 JSON 中的 `current_revision`、`context_path`、`context_json_path` 等入口；随后由 Agent 实际读取相应文件并开展工作。`start_agent.py` 这个文件名不代表它会启动 Agent。

项目文件位于 `<workspace_root>/projects/demo-workshop/`。有实际 Brief 时，可在首次初始化命令中增加 `--brief "C:/your-path/brief.md"`。默认原始来源与 Brief 仅进入 `master` 范围；角色字段是任务包过滤规则，不能代替文件系统权限。

## 日常 CLI：接续、回写、回滚与组装

完整字段和返回契约见 [运行协议](references/runtime-protocol.md)。命令的 JSON 返回值包含状态、当前版本、文件入口、警告和后续动作；退出码 0 只表示相应机械操作成功或同请求已应用。

### 按任务接续

```shell
python scripts/start_agent.py resume --project demo-workshop --task "Review the current brief and identify missing inputs" --page 1 --page-size 40 --config config.json
```

模块已登记后可加 `--module`。任务包默认每页 40 项，最大 100 项；按返回的覆盖信息读取后续页和必要原文。`--task` 不会触发语义搜索，也不能保证自动找齐资料。

本轮需要尚未列入当前任务依赖的对象时，可重复传入 `--required-ref`。例如 `--required-ref source:YOUR_REGISTERED_SOURCE_ID` **只适用于该来源 ID 已在本项目真实登记的情况**；把示例名称替换为真实 ID。显式必读不会永久登记依赖，正文采用后还须通过回写的 `source_ids` 或 `depends_on` 保存关系。

### 保存真实原件与正文

回写类型包括 `source`、`contract`、`handoff`、`module`、`change`、`review`。每份 JSON 载荷均需通过 `file` 指向真实且非空的文件；各类型另有必填字段，按运行协议生成载荷，而不是直接改权威快照。

以下是**需要替换参数的命令模板**，不是初始化后即可执行的演示：

```shell
python scripts/writeback.py source --project demo-workshop --base CURRENT_REVISION --operation-id register-source-001 --payload "C:/your-path/source-payload.json" --config config.json
python scripts/writeback.py module --project demo-workshop --base CURRENT_REVISION --operation-id revise-module-001 --payload "C:/your-path/module-payload.json" --config config.json
```

将 `CURRENT_REVISION` 替换为本次 `resume` 返回的真实版本，路径替换为实际载荷文件。模块必须已在契约中登记，生产前须满足对应交接条件。每次成功提交都会产生新版本，下一次提交应重新核对基线。`operation-id` 标识一次请求：同 ID、同请求可幂等重试；不同内容应使用新 ID。

基础版本冲突时，运行工具会保留候选。重新读取当前版本，比较并修订内容，再用新操作 ID 提交；仅更换 `--base` 不能代替核对。`reviewable` 表示可评审，不表示已经批准，且须人工复核下方已知状态问题。

### 恢复历史内容

先阅读下方回滚报告权限问题。以下仍是需替换真实版本的模板：

```shell
python scripts/rollback.py --project demo-workshop --base CURRENT_REVISION --operation-id restore-content-001 --to ANCESTOR_REVISION --reason "Restore the reviewed content for comparison" --config config.json
```

`ANCESTOR_REVISION` 必须是已提交的祖先版本。回滚创建一个新版本，恢复历史正文与资料引用，同时保留当前事实、当前决定和全部外部事件，并生成差异报告。它不会撤回现实中的消息、合同、采购或活动，也不会让历史批准自动重新生效。

### 组装交付与辅助检查

已有满足条件的契约模块和真实正文后运行：

```shell
python scripts/assemble.py --project demo-workshop --config config.json
python scripts/cost_check.py --project demo-workshop --config config.json
python scripts/repair.py --project demo-workshop --config config.json
```

`assemble` 默认依契约顺序组装 `now` 模块，输出 `deliverables/<revision>/complete-plan.md` 及输入指纹清单；也可用 `--modules` 指定真实模块 ID。缺少正文、存在失效依赖或相关阻断时，组装会被阻止。它不补写内容、不判断内容质量，也不输出 `.docx` 或 `.pptx`。

`cost_check` 是已登记费用的只读结构与算术检查，不核验报价真实性。`repair` 重建中枢、目录等派生视图并报告诊断，不修复损坏的权威历史、不强制解锁。警告、阻断和未完成项需要按真实原因处理。

## 给 Agent 的三种任务示例

先让宿主加载完整技能，或将本机 `SKILL.md` 的绝对路径交给 Agent。下列项目 ID 需对应实际初始化的项目；资料路径、范围和用途应按真实委托填写。

**研究与方针：**

```text
使用 mkt-max-1，接续 demo-workshop，配置为本仓库 config.json。
这是一个面向首次参与者的工作坊项目，目标和资料以我提供的 Brief 为准。
先读任务包、Brief 和必要原文，核对受众需要、内容原料与关键条件。
完成研究、选择比较和最强反证；区分事实、拟案与待验证假设，注明置信度。
交付可审阅的方针及阶段交接，保存来源入口、读取范围、未决和成稿任务。
```

**完整成稿：**

```text
使用 mkt-max-1，接续 demo-workshop。沿用当前有效方针与契约。
先读取阶段交接和实际采用的原文，按契约中现在需要的模块写完整正文。
写清参与者的具体体验、场景、规则，以及约定的全量稿件和接手工作件。
按当前用途处理缺口；只暂停依赖实质决定的定稿，继续其他已授权工作。
逐项保存、交叉回读共同事实和接口，再组装 Markdown；准确列出未完成项。
```

**局部修订：**

```text
使用 mkt-max-1，接续 demo-workshop。我将提供新的场次日期和批准依据。
先核当前版本与原始内容，登记变更，检查受影响的内容、人员、资源、费用和稿件。
修改相关实际正文与接手文件，保留无关有效内容，并核对失效标记与未决问题。
按当前基线回写，输出修改说明、受影响范围和仍待确认事项，不直接修改快照。
```

## 文件结构

```text
mkt-max-1/
├── SKILL.md                 # 技能入口与工作协议
├── agents/openai.yaml       # Agent 界面元数据
├── references/              # 17 份按需参考，含运行协议与方法来源
├── scripts/
│   ├── start_agent.py       # init / resume
│   ├── writeback.py         # source / contract / handoff / module / change / review
│   ├── rollback.py          # 恢复内容为新版本
│   ├── assemble.py          # 组装实际 Markdown 正文
│   ├── cost_check.py        # 费用结构与算术检查
│   ├── repair.py            # 派生视图重建与诊断
│   └── hub_runtime.py       # 标准库运行实现
├── assets/readme-hero.png
├── config.example.json      # 可分发示例配置
├── config.json              # 个人配置，首次配置后生成，Git 忽略
├── version.json
├── LICENSE
├── README.md
└── README.en.md
```

配置工作根下的 `projects/<project-id>/` 保存 `项目中枢.md`、`HEAD.json`、`revisions/`、`assets/`、`candidates/`、`work/`、`operations/` 和 `deliverables/`。原件、历史与候选保存在项目中；公开仓库不包含真实项目资料。完整内容、历史版本和自己的原始输入应一并备份。

## 当前状态与已知问题

**1.1.0 为实验版本；以下三项已确认问题尚未修复。** 运行协议描述的检查与过滤不能视为当前实现无缺陷的保证。

| 已知问题 | 当前影响与使用边界 |
|---|---|
| 回滚差异报告未继承私有值权限 | `public` 任务包可能暴露完整报告入口，而报告可能含私有值。完整回滚报告仅在主控环境中使用；未经检查不要把回滚后的任务包分发给其他角色。任务包过滤不是操作系统级 ACL。 |
| 模块提交先检查旧 `unresolved`，后写入新的 `unresolved` | 同次提交可能出现 `reviewable` 与新增的 `blocking` 未决并存。提交后必须人工核对正文状态和全部新未决，不能以状态字段证明可定稿。 |
| `module.units` 同次提交的单元被误标为 `stale` | 新保存单元及其下游可能被阻断，需要检查实际对象、依据和影响。不要靠更改版本号或直接修改权威快照绕过。 |

验证还有两项明确边界：

- 盲稿验证器尚未充分校验 `source` 与 `anonymous` 稿件的一一对应关系。当前对 48 份稿件的核查未发现错配，但这不能证明验证器已覆盖该失败模式。
- 首包 token 计数排除了后续导航：记录中的首包比较为 7,304 与 6,832，完整两页计数为 7,659。不同读取范围不能直接作收益比较，本包不据此承诺 token 节省。

已有合成案例和模型评阅结果不替代真实岗位接手、实际受众体验或市场验证；历史上的 76 项测试也不能作为当前版本无缺陷的认证。脚本结构校验、内容审阅、权限检查与现实执行验证需要分别完成。

## 方法来源、许可与反馈

方法来自本工作区的 ceyuan2、ceyuan3、ceyuan4，重新整理为按需求触发的研究、条件推演、内容与交付流程。文件导航、任务包和版本机制参考了固定版本的 Agent Skills、Deep Agents、OpenSpec、GSD Core 与 Aider；采用范围和固定链接见 [方法来源](references/provenance.md)。运行工具以 Python 标准库独立实现，不要求安装这些框架。

代码与文档按 [MIT License](LICENSE) 发布。保留原许可与版权声明；第三方资料和用户项目原件不因使用本包而自动获得再分发许可。

反馈可通过 [GitHub Issues](https://github.com/DONGaOtang/mkt-max-/issues) 提交。报告问题时，请提供版本、最小复现命令、预期与实际结果，以及去除私有资料的示例输入；不要上传完整私有项目或含私有值的回滚报告。
