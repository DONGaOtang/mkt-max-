# 本地运行协议（schema_version 1，fingerprint_version 2）

运行库为 `scripts/hub_runtime.py`，Python 3.10+，仅标准库。`HubRuntime(workspace_root: Path | str)` 暴露 `init`、`resume`、`submit`、`rollback`、`repair`，异常为 `HubError`，含 `exit_code` 和 `response`。所有写入限制在配置工作根目录；指定外部原件仅作只读输入。目录名、ID、相对路径拒绝 `..`、Windows 保留名称、符号链接和 junction。

## 公共调用与退出码

以下相对命令以skill包目录为工作目录。实际调用也可用脚本的绝对路径；项目工作根目录由配置决定，不能因当前Shell目录改变。新项目显式调用init，接续调用resume；这些命令不启动Agent或安装宿主钩子。

```text
python scripts/start_agent.py init --name NAME [--id ID] [--brief FILE]
    [--brief-allowed-roles ROLE ROLE ...] [--config FILE]
python scripts/start_agent.py resume --project ID_OR_PATH [--module ID] [--task TEXT]
    [--page 1] [--page-size 40] [--role master] [--required-ref source:S1] [--required-ref fact:F1] [--config FILE]
python scripts/writeback.py source|contract|handoff|module|change|review
    --project ID_OR_PATH --base REV --operation-id ID --payload JSON_FILE [--config FILE]
python scripts/rollback.py --project ID_OR_PATH --base REV --operation-id ID
    --to REV --reason TEXT [--config FILE]
python scripts/repair.py --project ID_OR_PATH [--config FILE]
python scripts/assemble.py --project ID_OR_PATH [--view editor|client] [--modules ID ID ...] [--config FILE]
python scripts/cost_check.py --project ID_OR_PATH [--config FILE]
```

`--config` 可放在任意参数位置；配置 JSON 的 `workspace_root` 必须是绝对路径。JSON 输入接受 UTF-8 BOM。stdout 只输出一份 JSON；错误也符合返回契约。退出码：0 成功或同请求已应用，2 参数/结构/引用，3 基线或操作ID冲突，4 路径/缺文件/完整性，5 锁占用，6 存储/发布失败，7 当前业务前提不满足。

具体分类：缺结构字段/非法引用/依赖环为2；复核输入指纹过期或old_value不符为3；不安全ID、越界、缺输入文件和损坏为4；真实空文件/纯标题正文、交接目录覆盖缺口、条件交接缺未决、未满足交接或相关定稿阻断为7。API错误抛 `HubError` 并附完整返回dict；成功及带过滤包的角色阻断返回dict。

返回至少包含 `status, project_id, current_revision, operation_id, artifact_paths, context_path, warnings, next_actions, error`。成功状态为 `success`，幂等为 `already_applied`，业务阻断为 `blocked`，其余为 `error`。冲突返回 `candidate_path`、最新版本及重读动作。发布后派生视图失败仍返回0和警告；可运行 `repair.py` 重建，禁止因此重放提交。`resume` 的完整 `packet` 仅由API返回并可靠落盘；CLI默认只输出文件入口、分页摘要及负担提示，以免重复注入完整机器包。

## 结构与正文

所有提交载荷是 JSON object，必须提供 `file`（绝对路径或工作根目录内相对路径），指向真实原件或真实正文；文件必须存在且非空。JSON拒绝NaN/Infinity及重复键，参数返回2，权威文件损坏返回4。正文类提交必须为 UTF-8 文本，拒绝纯标题/目录/空白占位。结构通过只代表文件、引用和依赖一致，不证明内容完整、事实为真、用户批准或外部执行。

ID：1—80个 ASCII 字母、数字、下划线或短横线，首位为字母或数字，禁止 Windows 保留名。生成产物ID超长时使用稳定前缀、截短及SHA256片段，保留合法80字符外部ID。`project_id` 若写入载荷，须与目标项目相同。引用格式为 `source:S1`、`fact:date`、`decision:D1`、`module:M1`、`artifact:A1`、`question:Q1`、`resource:R1`、`cost:C1`、`event:E1`、`review:V1`、`unit:U1`、`session:SS1`、`contract:current`、`handoff:current`。`depends_on` 为上述引用列表，方向是“本对象依赖谁”；拒绝不存在引用、自依赖和环。依赖图由显式关系及来源/决定/事实/产物关联生成。

`applicability` 为 `now | later | not_needed | unknown`，四者独立于正文成熟度和用户决定。`content_status` 为 `outline | draft | reviewable | needs_review | blocked | archived`；`reviewable` 仅表示可评审，绝不等于批准。初始化不生成固定模块。

### 新项目怎样记录三次实际选择

新建持久化项目使用 `workflow_mode=collaborative`。单次轻量讨论在对话中照样给人看候选稿；需要保存时，委托原文可作初始化 Brief，分流简报或供选原型可作当前契约的 Markdown 正文。运行库的 `research`、`production` 只描述工作阶段。给策划人看过、同意当前方向、同意交付某节、发给客户、现场执行分别留证。

| 人要决定的事 | 写入和核验 | 未决时给人看什么 |
|---|---|---|
| A 核对委托和分流 | 把经核对的对象、首要目标、参与者动作、主路径及本轮用途用一句话写在 `contract.brief_scope`。交 `change`，其中 `entity="decision",status="confirmed",new_value={"gate":"brief","scope":"同一句话"}`。用用户原话已明确授权的部分即可。 | 显示简报、主次分流的依据及最影响内容的一个问题。 |
| B 选择要深化的方针 | 另一条已确认决定采用 `new_value={"gate":"direction","policy":"选中的方向及适用条件"}`，`decision_ids` 引用 A。正式 `handoff` 的 `policy` 与 B 一致，同时引用 A 和 B，`sufficiency` 为 `ready` 或有明确未决影响的 `conditional`。 | 给可读原型、推荐理由和代价。仅登记为 `proposed` 的决定可继续讨论。 |
| C 采纳实际阅读的内容 | 保留 `--view client` 实际导出的 Markdown 和同版 manifest。收到明确反馈后登记 `gate="delivery"`，引用展示版本、文件 SHA256 和实际采纳范围。 | 给客户审阅稿；编辑意见记入待改事项；等待采纳的内容保持待审。 |

三类决定都使用原有的 `file,source_ids,decision_ids,old_value,new_value,reason,impact` 字段。`file` 留决定人原话、所审版本/文件、选定范围及保留意见；A/B/C 登记为 `confirmed` 时，`source_ids` 必须引用至少一条对应回复或原委托来源。A 确认前必须已有范围相符、有效的当前契约。`confirmation:{actor,at,evidence}` 写实际决定人、时间和可追溯消息位置。研究者、模型角色或脚本产出的评价只作建议。运行库核对声明、依赖和文件指纹；人员身份、实际阅读及授权范围须靠真实回复核实。

同一委托中，B 记主创实际选择的方针。预算、资源或公开说法若另待决定，可另留普通 `decision` 或 `question`，用 `impact` 指向依赖放行的承诺。例如未获批费用会卡下单，供老板比较费用的判断稿仍可提交审阅。判断稿引用的是估算和业务事实，这些依据一变就要复核该稿。使用 `conditional` 交接时，写明阻断对象、解除条件和仍可写的章。确认状态以当事人原话、其实际权限和适用范围为据。

主方针或委托确实改选时，更新同一条 A/B 或先将原决定登记为 `superseded`。改变委托重点会使旧 A 和引用它的 B 待复核。撤销、失效或与当前方针不符时，交接、依赖该方针的正式模块提交和客户版组装均会阻断。回滚仍保留后续真实决定。重新进入生产前，用当前有效的 A、B 重交交接，更新受影响的正文。研究阶段可用编辑视图看当前讨论稿；已提出的其他想法继续作为可逆草案。

**C 的记录示例。** 一份完整客户审阅稿含“项目缘起”和“现场体验”两个模块。用户只说“现场体验里这句保留”，记录的 `new_value` 如下。示例中的版本和指纹须换成实物 manifest 的值。

```json
{
  "gate": "delivery",
  "review_revision": "r000012-example",
  "review_sha256": "实际展示的客户审阅稿SHA256",
  "accepted_sections": [{"module_id":"Experience","quote":"给同伴留一道线索。"}]
}
```

整章获采纳可填 `accepted_modules:["Experience"]`；只采纳某句话或段落，`accepted_sections` 的逐字摘录须在该模块展示文字中唯一匹配。可混合记录不同模块的整章和片段。仅有片段时 `accepted_modules` 保存为空。用户明确同意整个展示稿时可省略两项。原本展示的是 `--modules Intro Experience` 选集才加 `modules:["Intro","Experience"]`；看的是全稿就省略 `modules`，不用另造一份子集稿。

回复在后续版本收到也能登记。脚本回读已提交祖先上的原稿及同版 manifest，与权威快照重建的版本、读者视图、模块范围、输入指纹、状态及成稿字节逐项核对，再核当前正文及成立条件。未采纳章节独立修订、另行登记回复来源均可保留。获采纳模块已修改，即使只摘录一句，也先保留原话并让用户核对新版上下文。后续重交同一方向的交接，或增改结构化问题，只对影响该采纳范围的条件重新核对。原话和看过的版本仍可回读。

**恢复讨论。** 用 `resume --required-ref decision:A --required-ref decision:B`（把 A、B 换成本项目真实 ID），或加上相应的 C 决定。读返回的 `current_decisions`、对应决定原文、来源原件，以及 C 的 `review_revision` 目录内的阅读稿和 manifest。跨页查看完整记录，从原话复述上轮选择和待办。历史项目没有 `workflow_mode` 时，继续用原交接、写回及默认组装契约；重开讨论仍按本技能的 A/B/C 节奏核对当前取舍。

### source

必填：`file, source_id, title, producer, locator, published_at, occurred_at, accessed_at, version, access_status, read_scope, supports, limitations`。

`published_at, occurred_at` 可为 null（未知）；`accessed_at` 是非空时间描述。`access_status` 为 `full | partial | restricted | unavailable`，表示取得状态。`read_scope` 为 `{status: unread|partial|full, ranges: [精确页/段/时间/章节描述], limitations: [限制]}`，表示提交者申报的实际读取。`supports`、`limitations` 为列表，允许为空但必须明确提供。可选 `dynamic: bool, recheck_trigger: str, same_origin_ids: [source ID], depends_on: [typed refs]`。同源ID需存在，可以双向标注；同源是独立的出处关系，**不作为有向前置依赖**。脚本核原件字节完整性并绑定来源声明元数据指纹，读取申报不等于已验证读取。原件按 SHA256 在 `assets/` 去重；源版本、定位和读取记录在快照内。

```json
{"file":"inputs/source.txt","source_id":"S1","title":"合成研究原件","producer":"测试夹具","locator":"fixture:S1","published_at":null,"occurred_at":null,"accessed_at":"2026-10-08","version":"fixture-v1","access_status":"full","read_scope":{"status":"partial","ranges":["第1—2段"],"limitations":["后半段尚未读"]},"supports":["内容原料"],"limitations":["合成输入"],"dynamic":false}
```

### contract

必填：`file, requirements, author_role, recipient_role, document_use, modules`。`requirements` 可为非空字符串或非空数组。模块来自真实需求，`modules` 可为空。每项必填：`module_id, applicability, purpose, author_role, recipient_role, delivery_depth, depends_on, source_ids, decision_ids, acceptance, unresolved`。`acceptance` 非空字符串或非空数组；`unresolved` 为列表。可选 `fact_ids`、`content_status`（默认 outline）、`trigger`（后续/未知项）、`not_needed_reason`。本次不需要项只登记判断，不生成空正文。更新契约保留已有模块正文及成熟度，实质契约变化标相关项待复核；不能在契约中借状态覆盖已写正文。

### handoff

必填：`file, policy, decision_ids, source_ids, inventory_source_ids, sufficiency, unresolved`。`policy` 非空文本；`sufficiency` 为 `ready | conditional | blocked`。`inventory_source_ids` 覆盖当前全部来源ID（目录识别），`source_ids` 为本交接采用来源。可选 `module_ids, artifact_ids, depends_on`，用于登记本交接已经采用的上游成果。`unresolved` 每项为 `{question, impact:[typed refs], blocking:bool, owner_role, next_action, finalization_boundary}`。新项目 `blocked` 直接阻断正式交接；`conditional` 须有未决及影响，且 A、B 均有效。旧项目保留历史处理。进入 production 后，具体未决按影响约束相应模块。

`blocking` 判断**当前契约document_use及delivery_depth**是否允许提交可评审正文/组装，不把已披露的后续执行限制一律套在当前评审稿。例：日期未知但只交概念/文字评审案，写 `blocking:false`，边界仍明确“正式邀请发送前由主办核真实日期和入口”；契约改为发送就绪或执行交接时，该必要信息未取得写 `blocking:true`。`finalization_boundary` 是作者给接手人的说明，脚本不解析它来自动识别用途，也不判断实际发送授权。核心内容缺失仍阻断相应评审，不得借未来条件稿为名跳过正文。

### module

必填：`file, module_id, source_ids, decision_ids, changes, impact, content_status, acceptance_evidence`。模块须在当前契约中存在，适用为 `now` 或 `later`；`unknown` 不允许写成已就绪内容，`not_needed` 不生产正文。`changes` 非空说明或非空列表，`impact` 为 typed refs 列表。`acceptance_evidence` 非空文本或非空列表，是作者说明，脚本不认证语义。可选 `depends_on, fact_ids, unresolved, units, handoff_artifacts`。`handoff_artifacts` 每项含 `artifact_id,file,recipient_role,purpose,content_status`，保存实际接手文件；`units` 每项含 `unit_id,title,artifact_id`，引用本模块真实产物。`reviewable` 在相关 blocking 未决或失效依赖未处理时拒绝；draft 可条件推进。`source_ids/decision_ids/fact_ids` 与契约及提交关系合并，不能通过省略引用摆脱既有依赖。

契约更新保留正文实际采用的追加依据、依赖与单元，`contract_spec` 单独记录当前约定。重写正文后可用 `remove_dependencies: [typed ref]` 显式移除已经不采用的旧关系；仍由当前契约要求或本次重新采用的关系不得移除，省略字段不等于删除。历史版本仍保留原依据。

### change

必填：`file, entity, id, old_value, new_value, reason, source_ids, decision_ids, impact`。`entity` 为 `fact | decision | resource | cost | question | event | unit | session`；`old_value` 是当前对象的 `value`（新对象为 null），不相符返回3。`new_value` 是 JSON值，不能为 null。新增事实/决定必须有来源或决定依据。可选 `status, valid_conditions, dynamic, recheck_trigger, depends_on`。事实状态 `asserted | verified | unknown | needs_review`；决定状态 `proposed | confirmed | rejected | superseded | needs_review`；资源、费用、问题、事件的状态是明确文本。`confirmed` 必须提供 `confirmation:{actor,at,evidence}`，记录申报的真实决定出处，文件操作不会自行批准。事件保留真实外部发生记录，不以回滚撤销。变化记录同时保存为真实正文；按显式依赖传播 stale/needs_review，不自动改写自然语言。

`unit` 保存到 `content_units`，`new_value` 必填 `{title,module_id,artifact_id}`，模块和真实产物必须存在且owner相同；模块提交的 `units` 也注册为一等 `unit:` 对象。单元自动依赖其实际模块和产物。`session` 保存到 `sessions`，`new_value` 必填 `{title,unit_ids,date,time,resource_ids,cost_ids}`，列表可为空，日期/时间未知用 null。场次引用真实单元/资源/费用并自动形成依赖；下游模块可显式依赖 `session:SS1`，改期使其待复核。此结构验证对象归属与已登记关系，跨期叙事、排期合理性和现场可行性仍需实际核查。

### review

必填：`file, review_id, targets, input_fingerprints, reviewer, method, result, evidence`。`targets` 非空 typed refs 列表；`input_fingerprints` 为 `{typed_ref: SHA256}`，至少覆盖 targets 及其必要传递依赖，指纹必须等于当前版本。产物 `artifact:` 用文件 SHA256；来源 `source:` 的v2指纹同时绑定原件SHA256与来源声明元数据（包括读取范围、出处、版本、限制及已登记关系），排除运行时的失效标记、产物定位ID、原始本地路径与更新时间；其他结构对象用规范JSON SHA256。来源目录的 `file_sha256` 保留原始字节指纹。`resume` 包中可取得当前v2 `fingerprints`，完整映射以包的 `fingerprints_path` 为准，不能把来源文件SHA256直接当作v2来源指纹。`reviewer/method` 为非空描述，`result` 为 `pass | fail | unknown`；`evidence` 为已存在产物ID列表，可为空（文件本身也是本次证据）。可选 `unresolved` 列表。运行时自动登记 `input_fingerprint_version:2`，调用方无须另传；新复核只接受当前v2映射，旧来源字节指纹返回3。成功复核不升级用户决定或外部执行。相关输入变化只让依赖该输入的复核 stale，无关复核保留。

### 费用实体与只读检查

`change.entity=cost` 的 `new_value` 必须保存 `quantity, unit, unit_price, amount, currency, tax_basis, source, status, shared_or_incremental`。未知数值/币种/含税口径用 null，不能用0替代；`source` 为来源ID或来源ID列表，必须存在并同时列入载荷 `source_ids`。`quantity/unit_price/amount` 为有限非负数或可精确解析的十进制字符串；都已知时校验数量×单价与金额（金额误差容许0.01）。`shared_or_incremental` 为 `shared | incremental | allocation | unknown`。`allocation` 必填 `master_cost_id`，引用一个非失效的 `shared` 主成本，币种/含税口径须相同，并由该字段自动形成主项依赖。候选金额加同主项非失效兄弟分摊的全部已知金额，不得超过已知主项金额；null只表示完整合计未知，不取消已知金额的上限校验。引用失效主项返回7。主项的金额、币税口径、类型或依据更改后，分摊及下游自动失效。先修正主项，再逐项重写分摊；旧失效分摊保留为待核记录，不参与当前有效分摊的上限，避免旧值阻止合法的逐项修复。

`HubRuntime.cost_audit(project)` / `cost_check.py` 只读检查按币种和含税口径分组的总额、未知项及分摊入口；分摊不重复增加主账，失效或未知金额不当0计入。保留 `totals, unknown_cost_ids, allocations`；每个分摊增补 `stale, validation_status, issues`，校验状态为 `current | unknown | stale | invalid`。失效、未知或结构/金额关系失配的分摊也列入 `unknown_cost_ids` 待核，`amount` 保留原登记值且 `added_to_total` 始终为false，不能把这条金额解释为当前有效分摊。结构及算术检查不证明市场价/报价已核实。

## 事务、损坏与恢复

提交在 `work/` 构造完整暂存版本，从暂存文件渲染版本内中枢，链接指向最终发布版本。`manifest.json` 记录所有快照文件及资产引用的 SHA256/大小，记录父版本和父manifest指纹；HEAD 记录当前manifest指纹。读取当前版本时验证完整已提交父链，祖先损坏同样拒绝。未发布孤立版本不计为已提交操作。

指纹算法独立于schema版本：缺少 `state.fingerprint_version` 的历史快照严格按v1验证原有 `fingerprints.json`，v2快照严格按v2验证，未知版本返回4；不采用任一算法匹配即可通过的降级方式。init、submit和rollback的下一次成功发布均登记 `fingerprint_version:2`，回滚至v1祖先仍生成v2新子版本。旧快照、manifest和复核输入不改写，失败或已应用请求的幂等重试不会生成迁移版本。旧HEAD的resume将当前v2完整映射另存为派生文件，历史快照中的v1映射仍仅代表该历史版本。旧复核缺 `input_fingerprint_version` 时按1解释；目录标明 `source_metadata_coverage:not_bound`，表示该复核未绑定来源声明元数据，应按当前v2指纹重新复核。算法升级本身不伪造旧复核失效；相关输入变化及回滚仍按原有规则传播stale。

单项目锁记录本机host/PID/创建时间/操作ID。占用或异常锁返回5；`repair` 仅诊断，绝不强制解锁。进程已退出的残留锁需人工核暂存/HEAD后处置。候选、暂存和孤立完整版本不会因失败自动删除。

操作指纹包含类型、base、载荷和输入文件字节指纹。同ID同请求返回已应用，包括回滚后重试；同ID异请求返回3并保留候选。基础版本冲突保留请求和输入文件，要求读取当前基线、比较、修订并使用新操作ID；仅换base不能代替内容核对。

回滚目标必须为已提交祖先。回滚创建新版本，父版本仍是当前版本；恢复目标单独记录。整体恢复目标正文与资料引用，同时保留当前事实、当前决定和全部外部事件，输出差异报告。恢复的历史批准不当当前有效批准；动态条件及与当前条件不同的相关正文、摘要和复核标 stale/needs_review。真实执行、消息、合同和采购不会被本地恢复撤销。

## 有界接续、组装和实际能力

`resume(project, module_id=None, task=None, page=1, page_size=40, role="master", required_refs=None)` 生成版本绑定的 Markdown/JSON任务包，默认40项、最大100项，目录、必读与决定分别分页。可用 `required_refs:[typed ref]` 或重复CLI `--required-ref` 显式指定本次任务需要的来源/对象；去重后与当前任务根合并，按原有传递依赖、产物入口、分页及角色权限生成必读集合。非法或不存在的本项目引用返回2，受限引用仍按阻断协议处理，不能借显式指定绕过权限。显式必读不修改永久依赖；正文实际采用后，须通过提交的 `source_ids/depends_on` 等关系登记。此接口不做语义检索，不保证自动找齐内容相关资料。包包含当前任务、契约入口、阶段交接、相关直接/传递依赖的原件和正文入口、指纹、读取申报、未读、例外、阻断、下一步。大正文不内嵌；长政策或未决在包内给短预览和原文/完整索引入口，明确截断。返回目录覆盖区间和总量只证明本页已列出，绝不证明原文阅读。上下文遥测和token用量为 unknown，字符数只是机械大小。

未指定模块的项目级接续将已登记初始化Brief、当前完整契约及交接作为必读上下文；这些入口不因目录翻页而丢失，仍服从角色限制。指定模块时，该模块的已登记依赖闭包、实际产物及显式 `required_refs` 是必要输入，受限即阻断；与它没有已登记依赖关系的Brief、完整契约和完整交接属于附带导航，只补充角色可见项。混合权限完整契约受限，不会仅因其中存在无关私有兄弟模块而阻断独立公开模块。若工作确实需要原始Brief或完整契约，须显式登记依赖或用 `required_refs` 指定，不能靠省略必要关系绕过约束。

任务包JSON即版本绑定的接续检查点，返回 `checkpoint_path` 与 `context_json_path` 指向同一文件，记录已过滤的 `required_refs` 和 `fingerprint_version:2`。不覆盖项目中由作者或演示脚本维护的其他 `work/checkpoint.json`。角色受限时只保存可见的必读引用及受限数量，不回显受限模块ID；后续需由有权角色重新指定完整任务。

任务包可使用 `allowed_roles: [角色名]` 限定来源、契约、模块、变化对象、复核和接手产物。**原始来源和初始化Brief默认 `master` 范围**；未分类资料不会自动分发公开角色。来源要共享必须显式登记 `allowed_roles`；Brief要共享用API可选 `brief_allowed_roles=[...]` 或CLI `--brief-allowed-roles ...`。其余新对象未指定时保持开放并继承依赖限制，已有对象更新时省略此字段保留原限制，master可维护全量。早期schema-1原始资料未记录范围时也按master处理，不改不可变历史。

限制经登记的前置依赖、模块契约和产物owner继承，以拒绝集合沿反向依赖传播至固定点计算，权限关系中的合法循环不会因遍历顺序放开受限对象；公开角色的目录、原件入口、决定预览与指纹文件均过滤；全量state/指纹入口不会交给该角色。包含混合权限模块的完整契约、含受限资料清单的完整交接保持受限，主控需提供获授权的脱敏输入。受限必要输入返回 `blocked`（API仍含过滤后的packet，CLI退出7），仅显示受限数量/处理动作，不显示私有标题、值、路径或指纹。这是**包范围过滤**，不宣称文件系统ACL、身份认证或语义自动脱敏。

**编辑阅读。** 新项目默认 `--view editor`，输出 `editor-review.md`。研究阶段装入契约讨论正文，尚无契约时采用 Brief；B 通过、当期还没写模块时装入已确认方针交接。已有模块时按契约次序汇集当前已写正文与接手附件，显示草案、待复核及阻断事项。可用 `--modules` 单独审某一模块。编辑稿供内部讨论。

**客户阅读。** 契约模块显式填 `audience:"client"` 才能进入 `--view client` 的 `client-review.md`，默认未标模块用于内部。仅使用当期 `now`、`reviewable`、无失效和当前阻断的客户正文。整份契约、模块契约、当前模块和正文中显式的 `allowed_roles` 限制都须包含 `client`。若工作件含内部材料，在已明确可交客户的范围里另写独立正文并核准读者。组装不收接手附件；编辑仍须核对正文中的敏感信息、内部链接、未证承诺和客户必须知道的条件。项目标题统一在首行，模块开头的同名一级标题去重，其他模块一级标题降为二级。新稿和同版 `.manifest.json` 存在 `deliverables/<revision>/`，manifest 记录模块范围、原件指纹、实际稿件 SHA256 及 `awaiting_review`。部分组装文件名带选集后缀。

**旧项目接续。** 无模式标记的项目默认组装仍保留原 `complete-plan.md` 或 `selection-…md`、原字节格式与附件顺序；可显式选新阅读视图。旧默认稿供历史接续。Word、PPT 及现场交付分别验收。`repair` 重建中枢、目录及操作索引；历史或关键文件损坏须修复实际来源。
