# Hermes 宿主安装说明

Hermes 没有 Codex 的 SessionStart / UserPromptSubmit / Stop 钩子，所以自动召回与自动提交都不存在：
改为由技能要求模型在任务开始与结束时**显式**调用同一个适配器。隐私校验、签名、项目隔离、
UNKNOWN 语义完全不变。

## 安装

把 `plugins/cognee/scripts/` 与合并后的 `plugins/cognee/skills/hermes-memory/SKILL.md`
一起装成一个 Hermes 技能（一个技能覆盖上游 11 个细分技能，避免抢触发词）：

```bash
DEST=~/.hermes/skills/productivity/cognee-memory
mkdir -p "$DEST"
cp -R plugins/cognee/scripts "$DEST/scripts"
cp plugins/cognee/skills/hermes-memory/SKILL.md "$DEST/SKILL.md"
```

## 后端

复用本机已有运行时，不需要二次配置：

- 运行时：`~/.cognee-plugin/venv`（Cognee 1.6.5，Python 3.14）
- 配置：`~/.cognee/.env`（0600，`COGNEE_BACKEND=local`，模型走本机 Ollama）
- 服务：`http://localhost:8011`（`~/.cognee-plugin/api_key.json` 持密钥）

## 验证

```bash
SKILL=~/.hermes/skills/productivity/cognee-memory
python3 "$SKILL/scripts/list-datasets.py"        # 能列出数据集 = 认证与服务正常
python3 "$SKILL/scripts/daily_memory.py" --project "$PWD" --task "验证" --session probe begin
python3 "$SKILL/scripts/daily_memory.py" --project "$PWD" recall
```

- `begin` 离线可用；`recall` 对没有历史数据的新项目会返回
  `operation_rejected_or_unavailable`（底层是 dataset 404），这是"本项目暂无记忆"，
  不是安装失败。
- 401/403 才是后端/密钥问题。
- `~/.cognee-plugin/server-ready.json` 可能是旧的 `auth_failed` 快照，以当前命令为准。
