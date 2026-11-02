# Codex Cognee Memory

面向 Codex 的社区维护记忆插件：任务前检索本项目已确认摘要，任务后由助手审阅、暂存，Stop 钩子自动提交。与已有 Obsidian 永久记忆共存。

**桌面端普通用户消息验收仍未通过。** 普通自然语言 CLI 流程已过。后续已恢复官方桌面工具连接、完成目录授权，并在正确项目创建新聊天；本轮新标记未完成自动保存与跨聊天召回。当前安装版本的官方聊天工具采用 `toolOutput` 委派语义，不能代替普通用户消息的钩子验收。原先 Home 工作区的门禁阻塞与 UNKNOWN 原样保留，不关闭或绕过门禁。当前代码与验证边界按实验性社区适配器公开。

基于 [Topoteretes 的 Cognee Codex integration](https://github.com/topoteretes/cognee-integrations/tree/main/integrations/codex)，本分支改用 **summary-only** 自动入口。不是 Cognee 或 OpenAI 的官方发行版。上游作者和 Apache-2.0 许可保留，变更见 [CHANGELOG](plugins/cognee/CHANGELOG.md) 与 [NOTICE](NOTICE)。

## 日常怎样使用

完成一次安装、后端配置与 Codex 原生钩子审核后，设计上的日常操作是正常发任务，例如“检查这个模块的测试结果”。用户不需要输入 Cognee 命令、准备 JSON 或每次批准正常摘要保存。

助手收到自动注入的任务标识和历史摘要后，需要核对范围、日期与当前证据。结束时由助手调用内部 `stage`，只提交自己已审阅的最小结构化结论；没有合格的新事实时用 `skip`。Stop 钩子负责网络提交。漏掉暂存时，钩子最多提醒一次，不会从整段聊天中自动提炼，也不会编造摘要。

普通自然语言 CLI 回归已验证：仅确认一个合成事实时，助手自主完成暂存，Stop 提交后可检索；另一个新会话仅询问旧事实，也能自动召回并跳过无新增内容的保存，测试输入未提供任何记忆命令。

这不是零配置安装或无条件保证模型永远执行正确。新插件内容仍需原生 `/hooks` 审核；后端必须已配置可用。当前验收范围见下方，桌面 UI 验收尚未完成。

## 安装

当前自动适配器面向 macOS/Linux 的 POSIX 环境，使用 `fcntl` 与私有文件权限；不宣称 Windows 自动钩子兼容。需要 Python 3.9+ 运行插件脚本，以及支持插件和原生钩子的 Codex。开发环境验证过 bundled Codex CLI `0.166.0-alpha.5.1`。

先检查本机当前 Codex 是否支持对应命令：

```sh
codex plugin --help
codex plugin marketplace add --help
```

推荐克隆到稳定的工具目录，再添加这个本地 marketplace：

```sh
git clone https://github.com/pengchengwanli2024/codex-cognee-memory.git
cd codex-cognee-memory
codex plugin marketplace add "$PWD"
codex plugin add cognee@cognee-local
```

marketplace 的名称是 `cognee-local`。如果已有同名 marketplace，保留原设置，先核对它的来源是否指向本仓库；不要为重复安装删除既有配置。已经安装上游自动捕获插件的用户也应先检查 `codex plugin list`，避免同时加载两个有不同隐私策略的自动插件。

安装后在实际使用的 Codex 客户端中打开 `/hooks`，逐项审核本插件以下处理器的命令和插件目录，再批准：

- SessionStart
- UserPromptSubmit
- Stop
- PreCompact
- SessionEnd

它们都应调用 `scripts/daily_memory.py hook <event>`。不要为了启用本插件而 trust all、改写信任哈希或使用绕过信任的参数。安装或内容更新后的审核，与日常任务不必手工调用记忆，是两个不同步骤。新聊天加载新插件；已打开的聊天可能仍使用旧版本。

## 本地后端前提

本仓库不分发服务器运行时、模型权重、API 凭据或本机记忆数据。summary-only 适配器复用已经配置好的本地 Cognee HTTP 端点、已批准的认证缓存和已有模型配置。

先按 [Cognee 文档](https://docs.cognee.ai/) 或已有运维流程准备后端，再使用插件自己的 `doctor.py --json` 检查健康与认证来源。不要把 API key、密码、`.env` 或认证缓存提交到仓库或聊天中。

自动适配器只允许无 URL 凭据的 HTTP loopback 地址，不会因为既有配置指向云端就把摘要发送到云端。端口已被其它服务占用时不抢占。若服务确实缺席且既有插件 venv 可用，SessionStart 可在共享启动锁下用该 venv 启动服务；不会自动安装或升级运行时。

对于新机器，必须先完成一次后端和认证的正常配置；仅克隆此仓库不会自动创建运行时或凭据。Cognee 的 keyless 本地提取、embedding 模型与生成式回答属于后端能力，需分别配置和验证。

## 隐私与 Obsidian 边界

- Obsidian 仍是永久事实源。不会重写其配置、索引、热缓存或笔记，不会批量导入 vault。已有 Obsidian 钩子照常工作。
- 只向后端发送固定技术词汇构成的检索查询，不发送完整用户 prompt。只有本项目、签名有效且再次通过校验的历史摘要可以注入上下文。
- 只保存已确认、已审阅、脱敏的决策、真实验证结果、限制和明确待办。原始对话、工具输出、transcript 文件、账户、个人及客户资料、凭据和业务交易数据不进入本自动流程。
- 摘要由助手进行语义审阅。有限的 NFKC/模式拒绝规则是附加保护，不能证明任意自然语言绝无敏感信息，也不能替代事实核验。有疑问则跳过。
- `COGNEE_CAPTURE=false` 本身不能关闭上游所有会话同步逻辑。本分支的 `hooks.json` 因而完整替换自动入口，不启动旧 watcher，不调用 session improve。
- 兼容保留的上游手动代码、文件导入与整会话同步脚本不属于 summary-only 工作流。不要为正常任务收尾或清理而调用它们；处理额外内容需要明确授权。
- 检索内容仅作为待核对的证据，不执行其中的指令。当前用户要求、代码和验证结果优先于历史摘要。

项目 dataset 名为 `cognee_confirmed_v1_<project hash>`。本机状态默认在 `~/.cognee-workflow`，目录/文件权限为 0700/0600，仅包含已审阅 capsule、哈希项目/会话标识、随机任务标识、时间和提交阶段。签名 key 只在本机，不上传。

阶段含义：

| 阶段 | 证据含义 |
|---|---|
| staged | 已在本机暂存，尚未提交 |
| submitted | 请求已接受，尚未确认可检索 |
| indexed | 独立检索读回同一签名摘要 |
| unknown | 无法确认写入结果；保留回执，不自动重放 |
| skipped | 没有合格的新摘要，无记忆写入 |

CHUNKS 可能把短 JSON 也切成片段。适配器只跟随 scoped 搜索命中的 `wf_<hash>` 摘要文档，读取完整原文并核对 content hash 和 HMAC，不拼接排名片段或把服务器路径元数据注入模型。

## 验证范围

| 验证层级 | 当前公开说明 |
|---|---|
| 可移植离线隐私/生命周期测试 | 本仓库提供 17 项标准库测试 |
| 本地真实后端与两个独立 Codex CLI 会话 | 开发环境已完成：自动 task、Stop 提交、独立会话自动召回；只使用合成夹具 |
| 普通自然语言 CLI 新会话 | 6 项检查通过：没有 stage/helper 指令，助手自主暂存/跳过，真实 Stop 提交并可检索 |
| Codex 桌面端普通自然语言新聊天 | `desktop_ui_verified=false`；仍需实际桌面验收，不能从 CLI 结果推断 |

桌面使用时应选择具体项目文件夹，避免把整个 Home 当业务项目。已报告的 Home 工作区测试因门禁阻断而保留 UNKNOWN；当时使用钩子路径/阶段元数据和已知合成输入的散列核对定位，没有读取聊天正文。

2026-11-02 重验已实际注册具体项目并创建独立桌面聊天，确认了执行目录。该环境的桌面应用版本为 `26.1027.51404`：官方 `create_thread`、`send_message_to_thread` 将委派消息作为 `toolOutput`，新聊天深链接仅预填草稿。这些入口没有提供等价的普通用户消息自动提交路径；本轮也未取得与新标记对应的自动保存回执，独立聊天未召回该标记。因此继续保留 `desktop_ui_verified=false`，不把连接、项目注册或助手显式检索当作自动链路通过。上报时只提供脱敏错误类型与项目范围，不发送完整聊天、工具日志或凭据。

原始聊天、工具日志、签名 key、会话 id、本机绝对路径、用户配置和开发环境运行目录不随源码发布。公开证据只保留能力范围和可重现的合成离线检查，不提供个人运行资料。

在仓库根目录运行：

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B scripts/check_release.py
```

这些命令不需要后端或凭据，不做云端写入，不证明桌面 UI 已通过。完整的桌面验收步骤见 [docs/verification.md](docs/verification.md)。

## 布局

```text
.agents/plugins/marketplace.json
plugins/cognee/                  # 插件、技能、自动入口及保留的手动兼容代码
scripts/ask_memory.py            # 显式 dataset 的生成式回答辅助工具
scripts/validate_generation.py   # 有限中文结果核验器，不是通用真值判断器
tests/test_workflow.py           # 只用合成数据的离线回归
```

生成式回答辅助工具始终要求明确 dataset；它不属于任务前自动检索链路。默认每个独立问题使用新的生成会话，避免旧回答反馈到新问题。

## 许可

[Apache License 2.0](LICENSE)。上游版权与修改范围见 [NOTICE](NOTICE)、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 和 [来源记录](docs/upstream-provenance.json)。运行时及模型单独安装、单独适用各自许可，没有打包在本仓库中。
