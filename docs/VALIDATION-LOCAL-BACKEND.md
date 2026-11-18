# Cognee 本地后端验证记录

时间：2026-11-18。范围：本机 macOS ARM64，Cognee 1.6.5 + Ollama，合成数据。

## 配置

| 项 | 值 |
|---|---|
| 运行时 | `~/.cognee-plugin/venv`（`cognee[ollama]==1.6.5`，368 个包，1.1 GB） |
| 后端 | `launchd` 服务 `local.cognee.server`，`127.0.0.1:8011` |
| 模型 | `ollama/llama3.2:3b`（LLM）、`nomic-embed-text`（embedding，768 维） |
| 配置 | `~/.cognee/.env`（0600，13 键） |
| 认证 | 主账号 API key 已由默认用户登录生成并缓存于 `~/.cognee-plugin/api_key.json` |

## 走过的弯路

1. `uv pip install` 卡在环境代理 `HTTP_PROXY=127.0.0.1:17891`，速度接近零；改用直连 + 镜像后完成。
2. `LLM_MODEL` 缺 `ollama/` 前缀 → `LLM Provider NOT provided`。
3. `LLM_ENDPOINT` 带 `/v1` → `OllamaException - 404 page not found`（litellm 原生框架要求裸 base）。
4. `NO_PROXY` 含 `[::1]` → httpx `InvalidURL: Invalid port: ':1]'`，所有模型调用在发出前就失败。
   这是插件缺陷，已在 `_env_file.normalize_no_proxy()` 修复并加 6 项测试。
5. 首次 `flush` 时模型冷启动导致 30s 连接测试超时；预热后正常。

## 结果

- `test_llm_connection()` 通过；`test_embedding_connection()` 返回 768 维。
- 完整链路：`begin` → `stage` → `flush`，阶段 `staged` → `submitted` → `indexed`。
- 另一个进程 `recall` 读回同一签名摘要，项目隔离与 HMAC 校验通过。
- `doctor.py --json`：`reachable=true`，`cognee_local=1.6.5`，`cognee_server=1.6.5`。
- 离线测试 32 项通过；`check_release.py` 无发现。

## 未验证

- 云端模式、多机 key 配额、Codex 桌面端自动钩子（仍需原生 `/hooks` 审核）。
- DSH 侧只用显式命令链验证，未在 DSH 会话内自动召回。
