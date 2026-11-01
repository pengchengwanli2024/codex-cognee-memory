# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 codex-cognee-memory contributors
"""Finite, offline verification of retained Cognee budget/name answers.

Only the supplied objects are read.  This module neither changes those objects
nor claims to verify that a live generative backend was used.
"""
import re
import unicodedata


_NUM = r"(?:[+-]?\d+|(?:[零〇○一二两三四五六七八九十百千亿]|万(?!元))+)"
_UNIT = r"(?:万元(?:人民币)?)?"
_TOTAL = r"(?:预算总额|预算总计|预算合计|合计预算|总计预算|总预算|总金额|总额|合计|总计|共计|合起来|两项(?:预算)?相加)"
_BASE = r"(?:一期(?:的)?预算|首期预算|基础预算|初始预算|原始预算|原预算)"
_EXTRA = r"(?:追加(?:的)?预算|新增预算|补充预算|追加金额)"
_LINK = r"(?:为|是|共|共为|共计|合计|应为|达到|人民币|约为|为人民币|是人民币|[:=])*"
_ROLE = "(?:" + _TOTAL + "|" + _BASE + "|" + _EXTRA + ")"
_OPERAND = r"(?:" + _ROLE + _LINK + r")?(" + _NUM + r")" + _UNIT
_EQUATION = re.compile(_OPERAND + r"(?:\+|加上|加)" + _OPERAND + r"(?:=|等于)" + _OPERAND)
_EXPR = re.compile(r"(" + _NUM + r")" + _UNIT + r"(?:(\+|加上|加)(?:" + _ROLE + _LINK + r")?(" + _NUM + r")" + _UNIT + r")?(?:(?:=|等于)(?:" + _ROLE + _LINK + r")?(" + _NUM + r")" + _UNIT + r")?")
_CN_DIGITS = {char: n for n, chars in enumerate(("零〇○", "一", "二两", "三", "四", "五", "六", "七", "八", "九")) for char in chars}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
_ID_KEYS = ("dataset_id", "data_id", "chunk_id", "source_ref_key")


def _integer(token):
    if re.fullmatch(r"[+-]?\d+", token):
        return int(token)
    if not token or any(c not in _CN_DIGITS and c not in _CN_UNITS for c in token):
        raise ValueError("not an integer")
    if all(c in _CN_DIGITS for c in token):
        return int("".join(str(_CN_DIGITS[c]) for c in token))
    total = section = digit = 0
    for char in token:
        if char in _CN_DIGITS:
            digit = _CN_DIGITS[char]
        else:
            unit = _CN_UNITS[char]
            if unit < 10000:
                section += (digit or 1) * unit
            else:
                section += digit
                if unit == 10000:
                    total += section * unit
                else:
                    total = (total + section) * unit
                section = 0
            digit = 0
    return total + section + digit


def _items(value):
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        return value
    return None


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _identity(evidence, dataset):
    if not isinstance(evidence, dict) or not all(_nonempty(evidence.get(k)) for k in _ID_KEYS):
        return None
    if evidence["dataset_id"] != dataset:
        return None
    if evidence["source_ref_key"] != "source_ref:v1:" + dataset + ":" + evidence["data_id"]:
        return None
    if "artifact_id" in evidence and evidence["artifact_id"] != evidence["chunk_id"]:
        return None
    return tuple(evidence[k] for k in _ID_KEYS)


def _body(text):
    # An appendix label must begin its own line, not occur inside a sentence.
    lines = text.splitlines()
    kept = []
    for line in lines:
        label = re.sub(r"^[ \t]*#{1,6}[ \t]*", "", line).strip()
        label = label.replace("**", "").replace("__", "")
        if re.fullmatch(r"Evidence\s*(?:[:：].*)?", label, re.IGNORECASE):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _normalized(text):
    text = unicodedata.normalize("NFKC", text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:#{1,6}\s*|[-*+]\s+|\d+[.)、]\s+)", "", line)
        lines.append(line)
    text = "\n".join(lines).replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"(?<=[\d零〇一二两三四五六七八九十百千万亿])\s+(?=[\d零〇一二两三四五六七八九十百千万亿])", "", text)
    return text


def _compact(text):
    return re.sub(r"\s+", "", _normalized(text))


def _money_claims(text, label):
    """Read values immediately governed by a budget label, not loose numbers."""
    claims = []
    malformed = False
    for match in re.finditer(label + _LINK, text):
        tail = text[match.end():]
        expr = _EXPR.match(tail)
        if not expr:
            continue  # A mention/question is not a numeric assertion.
        a, op, b, result = expr.groups()
        a = _integer(a)
        b = _integer(b) if b is not None else None
        result = _integer(result) if result is not None else None
        value = (result if result is not None else a + b if op else a) if label == _TOTAL else a
        arithmetic_ok = not (result is not None and op and a + b != result)
        # A redundant scalar equality is also an explicit equality claim.
        if result is not None and not op:
            arithmetic_ok = arithmetic_ok and (a == result or (label != _TOTAL and bool(re.search(r"(?:=|等于)" + _TOTAL, expr.group(0)))))
        claims.append((value, arithmetic_ok, (a, b) if op and label == _TOTAL else None))
        # Alternatives attached to the same value are still claims of this label.
        remaining = tail[expr.end():]
        for alternate in re.finditer(r"^(?:[,，、]?)(?:或(?:者)?|以及|并且|和|及|另为|也为)" + _LINK + r"(" + _NUM + r")万元", remaining):
            claims.append((_integer(alternate.group(1)), True, None))
    # Inverted wording, e.g. "100万元为总预算".
    for match in re.finditer(r"(" + _NUM + r")万元(?:为|是)" + label, text):
        claims.append((_integer(match.group(1)), True, None))
    return claims, not malformed


def _city_checks(text, city):
    label = r"(?:所在地(?:点|城市)?|所在城市|城市|位于|地处|坐落于)"
    assertions = []
    for match in re.finditer(label + r"(?:为|是|在|:|=)*", text):
        tail = text[match.end():]
        value_match = re.match(r"[\u3400-\u9fff]+", tail)
        if not value_match:
            continue
        value = value_match.group(0)
        value = re.split(r"(?:审批|批准|预算|一期|追加|并且|而且|同时|但是|但|且|也位于|也在)", value)[0]
        if value:
            assertions.append(value)
    def equal(value):
        return bool(re.fullmatch(r"(?:中国)?(?:[\u3400-\u9fff]{2,10}(?:省|自治区))?" + re.escape(city) + (r"市?" if not city.endswith("市") else ""), value))
    # A concise answer may put the named city in its own field without a label.
    present = bool(re.search(re.escape(city) + (r"市?" if not city.endswith("市") else ""), text))
    return present, all(equal(value) for value in assertions)


def _marker_checks(text, marker):
    marker_re = re.escape(marker)
    present = bool(re.search(r"(?<![A-Za-z0-9_-])" + marker_re + r"(?![A-Za-z0-9_-])", text))
    claims = []
    for match in re.finditer(r"(?:审批码|审批代码|审批编号|批准码|批准代码)(?:为|是|:|=)*", text):
        tail = text[match.end():]
        token = re.match(r"[A-Za-z0-9][A-Za-z0-9_./:-]*", tail)
        if token:
            claims.append(token.group(0))
        elif tail and not re.match(r"(?:未|没有|不详|未知|无法)", tail):
            claims.append(None)
    # Catch a second code of the same explicit code family, even when the label
    # is elided.  The family is derived from facts, never a sample constant.
    if "-" in marker:
        family = marker.split("-", 1)[0] + "-"
        claims.extend(re.findall(r"(?<![A-Za-z0-9_-])" + re.escape(family) + r"[A-Za-z0-9_-]+", text))
    return present, all(code == marker for code in claims)


def _unknown_checks(text):
    original = text
    text = re.sub(r"\s+", "", text)
    # Subject words can occur on either side of an ordinary lack-of-information
    # construction.  A bare, conventional source refusal is also sufficient.
    refusal = bool(re.search(
        r"(?:未(?:曾)?(?:提供|给出|提及|说明|披露|记录|记载|注明|明确)|"
        r"没有(?:提供|给出|提到|提及|说明|披露|记录|记载|注明)|"
        r"无(?:法|从)(?:从[^。;；]{0,16})?(?:确定|确认|判断|得知|获知|知晓)|"
        r"不能(?:从[^。;；]{0,16})?(?:确定|确认|判断|得知)|"
        r"(?:资料|材料|信息|记忆)[^。;；]{0,10}(?:不包含|不含|未含|缺少|没有)[^。;；]{0,8}(?:姓名|名字|负责人)|"
        r"(?:姓名|名字)[^。;；]{0,8}(?:不详|未知|无法确定|无法确认|未披露|未提供))", text))
    invented = False
    patterns = [
        r"(?:负责人(?:的)?(?:姓名|名字)?|姓名|名字)(?:可能|也许|大概|应该|应当|据说|实际|猜测)?(?:是|为|叫做|叫|:|=)([\u3400-\u9fff]{2,8}|[A-Za-z][A-Za-z .-]{1,30})",
        r"(?:可能是|也许是|应该是|大概是|推测为|猜测为|猜是|实际是|应该叫)([\u3400-\u9fff]{2,8}|[A-Za-z][A-Za-z .-]{1,30})",
        r"([\u3400-\u9fff]{2,4})(?:担任|是)(?:该项目的?|项目的?|承包商的?)?负责人",
        r"(?:由)([\u3400-\u9fff]{2,4})(?:负责|担任负责人)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = match.group(1)
            if not re.match(r"(?:未|不|无|没有|资料|材料|记忆|未知|无法|尚未|暂未|不能|现有|什么|谁|何人|哪个)", value):
                invented = True
    # Appended standalone names cannot be rescued by an earlier disclaimer.
    safe_short = {"未提供", "未提及", "未披露", "不详", "未知", "无法确定", "无法确认", "资料未提供", "记忆资料中未提供"}
    for sentence in re.split(r"[。!！?？;；\n]+", original):
        sentence = sentence.strip(" ,，:：\"'“”‘’()（）")
        if re.fullmatch(r"[\u3400-\u9fff]{2,4}|[A-Za-z]+(?:[ -][A-Za-z]+){0,2}", sentence) and sentence not in safe_short:
            invented = True
    return refusal, not invented


def validate(context, response, facts):
    """Return nonempty boolean diagnostics; malformed input fails closed."""
    checks = {}
    try:
        facts_ok = (isinstance(facts, dict)
                    and all(type(facts.get(k)) is int for k in ("base_budget", "additional_budget"))
                    and all(_nonempty(facts.get(k)) for k in ("city", "marker", "dataset_id"))
                    and type(facts.get("unknown_fact")) is bool)
        checks["facts_structure"] = facts_ok
        contexts, responses = _items(context), _items(response)
        checks["context_structure"] = contexts is not None
        checks["response_structure"] = responses is not None
        if not all(checks.values()):
            return {"ok": False, "checks": checks}
        dataset = facts["dataset_id"]
        known_sources = set()
        for item in contexts:
            if not isinstance(item.get("text"), str):
                checks["context_structure"] = False
            evidence = item.get("metadata", {}).get("evidence") if isinstance(item.get("metadata"), dict) else None
            if isinstance(evidence, list) and item.get("dataset_id") == dataset:
                for entry in evidence:
                    identity = _identity(entry, dataset)
                    if identity is not None:
                        known_sources.add(identity)
        checks["context_sources"] = bool(known_sources)
        total = facts["base_budget"] + facts["additional_budget"]
        context_bodies = {_compact(_body(item["text"])) for item in contexts if isinstance(item.get("text"), str)}
        for index, item in enumerate(responses):
            prefix = "response_" + str(index) + "_"
            text = item.get("text")
            checks[prefix + "text"] = isinstance(text, str) and bool(text.strip())
            checks[prefix + "dataset"] = item.get("dataset_id") == dataset
            metadata = item.get("metadata")
            evidence = metadata.get("evidence") if isinstance(metadata, dict) else None
            checks[prefix + "evidence"] = (isinstance(evidence, list) and bool(evidence)
                and all(_identity(entry, dataset) in known_sources and _identity(entry, dataset) is not None for entry in evidence))
            if not checks[prefix + "text"]:
                continue
            body = _body(text)
            normal = _normalized(body)
            compact = re.sub(r"\s+", "", normal)
            checks[prefix + "body"] = bool(compact)
            checks[prefix + "not_context_echo"] = compact not in context_bodies
            if facts["unknown_fact"]:
                refusal, no_name = _unknown_checks(normal)
                checks[prefix + "source_lacks_name"] = refusal
                checks[prefix + "no_invented_name"] = no_name
                continue
            total_claims, parsed = _money_claims(compact, _TOTAL)
            base_claims, _ = _money_claims(compact, _BASE)
            extra_claims, _ = _money_claims(compact, _EXTRA)
            equations = []
            for equation in _EQUATION.finditer(compact):
                a, b, c = map(_integer, equation.groups())
                equations.append((a, b, c))
            checks[prefix + "total_present"] = bool(total_claims) or any(c == total for _, _, c in equations)
            checks[prefix + "totals_consistent"] = parsed and all(value == total and arithmetic for value, arithmetic, _ in total_claims)
            checks[prefix + "components_consistent"] = (all(value == facts["base_budget"] and arithmetic for value, arithmetic, _ in base_claims)
                and all(value == facts["additional_budget"] and arithmetic for value, arithmetic, _ in extra_claims))
            checks[prefix + "equations_consistent"] = all(a + b == c and c == total and sorted((a, b)) == sorted((facts["base_budget"], facts["additional_budget"])) for a, b, c in equations)
            checks[prefix + "total_operands_consistent"] = all(operands is None or sorted(operands) == sorted((facts["base_budget"], facts["additional_budget"])) for _, _, operands in total_claims)
            city_present, city_consistent = _city_checks(compact, facts["city"])
            code_present, code_consistent = _marker_checks(compact, facts["marker"])
            checks[prefix + "city_present"] = city_present
            checks[prefix + "cities_consistent"] = city_consistent
            checks[prefix + "code_present"] = code_present
            checks[prefix + "codes_consistent"] = code_consistent
        return {"ok": bool(checks) and all(checks.values()), "checks": checks}
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError, RecursionError):
        checks["malformed_input"] = False
        return {"ok": False, "checks": checks}
