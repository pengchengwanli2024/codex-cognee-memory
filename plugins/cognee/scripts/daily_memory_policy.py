# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 codex-cognee-memory contributors
"""Finite privacy guard for reviewed summaries; not a universal PII detector."""
from copy import deepcopy
import re
import unicodedata


_PREFIX = "已确认 决策 验证 待办"
_LABELS = ("Cognee", "Obsidian", "Python", "TypeScript", "API", "测试", "构建", "权限", "记忆", "工作流", "跨会话", "验收")
_FIELDS = {"schema", "reviewed", "confirmation", "status", "summary", "facts", "evidence"}
_BAD_COMPONENTS = ("auth", "credential", "secret", "transcript", "session", "customer", "contact", ".env", ".ssh", ".git", "node_modules", "logs")
_SENSITIVE = re.compile(
    r"[\w.+-]+@[\w.-]+\.[\w-]+|\d{7,}|(?:\d{1,3}\.){3}\d{1,3}|https?://"
    r"|[A-Za-z]:[\\/]|(?<![\w/])/[A-Za-z0-9._~-]"
    r"|[A-Za-z0-9_/+\-=]{24,}"
    r"|password|passwd|secret|token|api[_-]key|private\s+key|authorization|bearer|credential|cookie|email|phone|customer|contact|account"
    r"|密码|密钥|令牌|客户|联系人|电话|手机|邮箱|身份证|银行卡|住址|付款|订单|预算"
    r"|-----BEGIN|ignore\s+previous|system\s+prompt|忽略之前|忽略以上|系统提示",
    re.IGNORECASE,
)


def safe_query(prompt):
    """Return only fixed vocabulary, regardless of arbitrary prompt content."""
    if not isinstance(prompt, str):
        return _PREFIX
    lowered = prompt.casefold()
    matched = [label for label in _LABELS if label.casefold() in lowered][:6]
    return " ".join((_PREFIX, *matched))


def _text(value, limit):
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= limit
        and all(unicodedata.category(char) not in ("Cc", "Cf", "Cs", "Zl", "Zp") for char in value)
    )


def _artifact_path(value):
    if not _text(value, 160) or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        return False
    if not value.endswith((".json", ".md")):
        return False
    parts = value.split("/")
    return all(
        part and not part.startswith(".") and not any(term in part.lower() for term in _BAD_COMPONENTS)
        for part in parts
    )


def validate_summary(value):
    """Reject without echoing input; copy accepted data after every check passes."""
    def reject(reason):
        return {"ok": False, "reason": reason}

    if type(value) is not dict or set(value) != _FIELDS:
        return reject("record_shape")
    if value["schema"] != "confirmed-summary-v1" or value["reviewed"] is not True:
        return reject("review_required")
    if value["confirmation"] not in ("tool_verified", "user_confirmed"):
        return reject("confirmation")
    if value["status"] not in ("confirmed", "verified_local", "partial", "blocked"):
        return reject("status")
    if not _text(value["summary"], 300):
        return reject("summary_text")
    facts = value["facts"]
    if type(facts) is not list or not 1 <= len(facts) <= 6 or not all(_text(item, 180) for item in facts):
        return reject("facts_text")
    evidence = value["evidence"]
    if type(evidence) is not list or not 1 <= len(evidence) <= 6:
        return reject("evidence_shape")
    artifacts = []
    user_confirmed = False
    for item in evidence:
        if type(item) is not dict:
            return reject("evidence_shape")
        if item.get("kind") == "artifact":
            if set(item) != {"kind", "path", "sha256", "result"}:
                return reject("artifact_shape")
            if not _artifact_path(item["path"]):
                return reject("artifact_path")
            if not isinstance(item["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None:
                return reject("artifact_hash")
            if item["result"] not in ("passed", "failed", "blocked"):
                return reject("artifact_result")
            artifacts.append(item)
        elif item == {"kind": "user_confirmation", "reference": "current-task"}:
            user_confirmed = True
        else:
            return reject("evidence_shape")
    if value["confirmation"] == "tool_verified" and not artifacts:
        return reject("artifact_required")
    if value["confirmation"] == "user_confirmed" and not user_confirmed:
        return reject("user_confirmation_required")
    if value["status"] == "verified_local" and (not artifacts or any(item["result"] != "passed" for item in artifacts)):
        return reject("passed_artifact_required")
    for text in (value["summary"], *facts):
        if _SENSITIVE.search(unicodedata.normalize("NFKC", text)):
            return reject("sensitive_text")
    return {"ok": True, "reason": "accepted", "summary": deepcopy(value)}
