# 方法来源和迁移边界

本包为独立新技能，名称为 `mkt-max-1`，当前版本以包根目录的 `version.json` 为准。业务仍分研究定向、完整内容生产两个阶段。

## 本地方法来源

采用当前工作区 ceyuan2 的研究、关键词、原料与反证，ceyuan3 的条件路由、模块契约、专业和履约接口，ceyuan4 的内容、系列与反馈方法。重新组织为按真实需求触发的参考资源，不复制三个旧入口和固定暂停点。旧版本保留。详细采用、改写和验证记录在建设目录的 `docs/method-mapping.md` 与 `docs/requirements-map.md`；这些建设文档不作为用户运行本技能的依赖。

原方法仓库为 MIT 许可，原许可及版权声明完整保存于本包 `LICENSE`。没有把旧客户资料、项目事实、账号信息或测试运行数据打包。

## 外部机制来源

以下固定版本来自已有研究基线，本轮用于方法落地。此处列出可定位来源，不声称本轮重新全文审查这些仓库，也不采用其自评作为本系统验证结论。

| 固定来源 | 本包采用 | 适用边界 |
|---|---|---|
| [Agent Skills](https://github.com/agentskills/agentskills/blob/69ef37e9424c0a7ea9dd2293b559e43ec8176379/docs/specification.mdx) | 元数据、轻入口、条件读取 | token建议不是宿主安全容量 |
| [Deep Agents](https://github.com/langchain-ai/deepagents/blob/44bd956bf8ca86c7cf0831132d69d38e06dd1573/libs/deepagents/deepagents/middleware/filesystem.py) | 大结果可靠保存后给预览和准确回读入口 | 保存前的截断不能伪称完整；不引入框架依赖 |
| [OpenSpec](https://github.com/Fission-AI/OpenSpec/blob/2500d6da971336167548b53731a35b2127df35ac/docs/concepts.md) | 当前权威版本、候选和依赖区分 | 不增加固定软件式审批流程 |
| [GSD Core](https://github.com/open-gsd/gsd-core/blob/6bc785c14e3e98e0c679c90221c951e57dd5e2d6/docs/explanation/context-engineering.md) | 限定任务、文件检查点、宿主能力预检 | 不承诺自动清空历史或不存在的启动钩子 |
| [Aider](https://github.com/Aider-AI/aider/blob/5dc9490bb35f9729ef2c95d00a19ccd30c26339c/aider/repomap.py) | 有预算的任务相关地图 | 代码符号优先级不能判断策划资料的重要性 |

本包独立实现标准库运行协议；没有复制这些第三方仓库的实现代码，没有安装上述框架。
