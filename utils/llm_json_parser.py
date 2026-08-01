# utils/llm_json_parser.py
from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Iterable, List, Sequence, Tuple


class LlmJsonParseError(ValueError):
    """LLM 返回内容无法安全恢复。"""


MERGE_NOTE_RE = re.compile(
    r"(?:合并|并入).{0,12}(?:前一段|前段|上一段)",
    re.IGNORECASE | re.DOTALL,
)


# BLOCK_ID 必须作为每个对象的第一个字段。
# 匹配双引号、单引号、中文引号和裸 ID。
BLOCK_ANCHOR_RE = re.compile(
    r'(?:^|[{\[,])\s*["\'“”]?BLOCK_ID["\'“”]?\s*:\s*'
    r'(?:"(?P<dq>(?:\\.|[^"\\])*)"'
    r"|\'(?P<sq>(?:\\.|[^\'\\])*)\'"
    r"|(?P<bare>[A-Za-z0-9_.:\-]+))",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def clean_llm_text(text: str) -> str:
    """清除 BOM、Markdown 围栏和 JSON 前后的说明文字。"""
    text = (text or "").lstrip("\ufeff").strip()

    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    decoder = json.JSONDecoder()
    for start, char in enumerate(text):
        if char != "[":
            continue

        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue

        if isinstance(value, list):
            return text[start:start + end]

    return text.strip()


def decode_backslash_escapes(value: str) -> str:
    """
    仅恢复 JSON 常见转义。

    不使用 unicode_escape 解码整个字符串，
    否则可能破坏原有中文。
    """
    result: List[str] = []
    index = 0

    mapping = {
        '"': '"',
        "'": "'",
        "\\": "\\",
        "/": "/",
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }

    while index < len(value):
        char = value[index]

        if char != "\\" or index + 1 >= len(value):
            result.append(char)
            index += 1
            continue

        next_char = value[index + 1]

        if next_char == "u" and index + 5 < len(value):
            digits = value[index + 2:index + 6]

            if re.fullmatch(r"[0-9a-fA-F]{4}", digits):
                result.append(chr(int(digits, 16)))
                index += 6
                continue

        if next_char in mapping:
            result.append(mapping[next_char])
            index += 2
            continue

        # 未识别转义原样保留。
        result.append("\\")
        result.append(next_char)
        index += 2

    return "".join(result)


def parse_loose_string(raw: str) -> str:
    """
    从某字段到下一字段之间的文本中恢复字符串。

    可容忍：
    - 正常 JSON 转义引号；
    - HTML 属性中未转义的双引号；
    - 换行；
    - 字符串内的大括号；
    - 字符串内的 JSON 相似内容。
    """
    raw = raw.strip()

    # 使用贪婪主体，选择字段末尾真正用于闭合值的最后一个引号。
    quoted = re.match(
        r'^\s*(?P<q>["\'“])'
        r'(?P<body>.*)'
        r'(?P<end>["\'”])'
        r'\s*,?\s*[}\]]*\s*$',
        raw,
        flags=re.DOTALL,
    )

    if quoted:
        start_quote = quoted.group("q")
        end_quote = quoted.group("end")
        expected_end = "”" if start_quote == "“" else start_quote

        if end_quote == expected_end:
            return decode_backslash_escapes(
                quoted.group("body")
            )

    # 不完整引号的最低限度容错。
    raw = re.sub(
        r"\s*,?\s*[}\]]*\s*$",
        "",
        raw,
        flags=re.DOTALL,
    ).strip()

    if raw[:1] in {'"', "'", "“"}:
        raw = raw[1:]

    return decode_backslash_escapes(raw)


def parse_loose_bool(raw: str) -> bool:
    match = re.match(
        r'^\s*["\']?'
        r"(true|false|1|0|yes|no|y|n|是|否)",
        raw,
        flags=re.IGNORECASE,
    )

    if not match:
        raise LlmJsonParseError(
            f"无法恢复布尔值: {raw[:100]}"
        )

    value = match.group(1).lower()
    return value in {"true", "1", "yes", "y", "是"}


def extract_balanced_list(raw: str) -> str:
    """从 new_terms 字段中提取第一个完整的数组。"""
    start = raw.find("[")

    if start < 0:
        raise LlmJsonParseError("未找到数组起始符")

    depth = 0
    quote = ""
    escaped = False

    for index in range(start, len(raw)):
        char = raw[index]

        if escaped:
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if quote:
            if char == quote:
                quote = ""
            continue

        if char in {'"', "'"}:
            quote = char
            continue

        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1

            if depth == 0:
                return raw[start:index + 1]

    raise LlmJsonParseError("new_terms 数组未闭合")


def parse_loose_list(raw: str) -> List[Dict[str, Any]]:
    raw = extract_balanced_list(raw)

    for loader in (json.loads, ast.literal_eval):
        try:
            value = loader(raw)

            if (
                isinstance(value, list)
                and all(isinstance(item, dict) for item in value)
            ):
                return value
        except Exception:
            continue

    raise LlmJsonParseError(
        "new_terms 不是可恢复的对象数组"
    )


def key_pattern(name: str) -> re.Pattern[str]:
    """
    字段名必须出现在对象起始或逗号之后。

    避免把译文中的普通文本误认为字段。
    """
    return re.compile(
        rf'(?:^|[{{,])\s*'
        rf'["\'“”]?{re.escape(name)}["\'“”]?\s*:',
        re.IGNORECASE | re.MULTILINE,
    )


def extract_fields_from_segment(
    segment: str,
    field_names: Sequence[str],
) -> Dict[str, str]:
    """
    先定位所有字段边界，再切取每个字段值。

    不使用 ([^"]*)，因此不会在 HTML 内部引号处提前结束。
    """
    positions: List[Tuple[int, int, str]] = []

    for field_name in field_names:
        match = key_pattern(field_name).search(segment)

        if match:
            positions.append(
                (match.start(), match.end(), field_name)
            )

    positions.sort(key=lambda item: item[0])
    values: Dict[str, str] = {}

    for index, (_, value_start, field_name) in enumerate(positions):
        if index + 1 < len(positions):
            value_end = positions[index + 1][0]
        else:
            value_end = len(segment)

        values[field_name] = segment[value_start:value_end]

    return values


def regex_extract_rows(
    text: str,
    *,
    include_new_terms: bool,
    allow_merge: bool,
) -> List[Dict[str, Any]]:
    """
    关键原则：

    先按 BLOCK_ID 把整个响应切成互不重叠的片段，
    再在片段内部提取字段。

    一个 BLOCK_ID 的字段绝不能跨到下一个 BLOCK_ID。
    """
    matches = list(BLOCK_ANCHOR_RE.finditer(text))

    if not matches:
        raise LlmJsonParseError(
            "正则容错未找到任何 BLOCK_ID"
        )

    rows: List[Dict[str, Any]] = []

    field_names = [
        "proofread_zh",
        "proofread_note",
    ]

    if include_new_terms:
        field_names.append("new_terms")

    if allow_merge:
        field_names.extend([
            "merge_to_prev",
            "merged_previous_zh",
        ])

    for index, match in enumerate(matches):
        block_id = (
            match.group("dq")
            or match.group("sq")
            or match.group("bare")
            or ""
        )
        block_id = decode_backslash_escapes(block_id).strip()

        if index + 1 < len(matches):
            segment_end = matches[index + 1].start()
        else:
            segment_end = len(text)

        # 每个块只处理自己的切片。
        segment = text[match.end():segment_end]

        raw_fields = extract_fields_from_segment(
            segment,
            field_names,
        )

        if (
            "proofread_zh" not in raw_fields
            or "proofread_note" not in raw_fields
        ):
            raise LlmJsonParseError(
                f"BLOCK_ID={block_id} 缺少必要字段"
            )

        row: Dict[str, Any] = {
            "BLOCK_ID": block_id,
            "proofread_zh": parse_loose_string(
                raw_fields["proofread_zh"]
            ),
            "proofread_note": parse_loose_string(
                raw_fields["proofread_note"]
            ),
        }

        if include_new_terms:
            if "new_terms" not in raw_fields:
                raise LlmJsonParseError(
                    f"BLOCK_ID={block_id} 缺少 new_terms"
                )

            row["new_terms"] = parse_loose_list(
                raw_fields["new_terms"]
            )

        if allow_merge:
            if "merge_to_prev" in raw_fields:
                row["merge_to_prev"] = parse_loose_bool(
                    raw_fields["merge_to_prev"]
                )
            else:
                # 兼容旧返回结构。
                row["merge_to_prev"] = bool(
                    not row["proofread_zh"].strip()
                    and MERGE_NOTE_RE.search(
                        row["proofread_note"]
                    )
                )

            if "merged_previous_zh" in raw_fields:
                row["merged_previous_zh"] = parse_loose_string(
                    raw_fields["merged_previous_zh"]
                )
            else:
                row["merged_previous_zh"] = ""

        rows.append(row)

    return rows


def normalize_and_validate(
    data: Any,
    expected_ids: Sequence[str],
    *,
    include_new_terms: bool,
    allow_merge: bool,
) -> List[Dict[str, Any]]:
    # 容忍 {"data": [...]} 等外层包装。
    if isinstance(data, dict):
        for wrapper_key in ("data", "results", "items"):
            wrapped = data.get(wrapper_key)

            if isinstance(wrapped, list):
                data = wrapped
                break

    if not isinstance(data, list):
        raise LlmJsonParseError(
            "顶层结构必须是 JSON 数组"
        )

    expected = [str(item) for item in expected_ids]
    expected_set = set(expected)

    if len(expected_set) != len(expected):
        raise LlmJsonParseError(
            "请求数据中存在重复 BLOCK_ID"
        )

    normalized: Dict[str, Dict[str, Any]] = {}

    for raw in data:
        if not isinstance(raw, dict):
            raise LlmJsonParseError(
                "数组中存在非对象条目"
            )

        block_id = str(
            raw.get("BLOCK_ID", "")
        ).strip()

        if not block_id:
            raise LlmJsonParseError(
                "存在缺少 BLOCK_ID 的对象"
            )

        if block_id not in expected_set:
            raise LlmJsonParseError(
                f"出现未知 BLOCK_ID: {block_id}"
            )

        if block_id in normalized:
            raise LlmJsonParseError(
                f"出现重复 BLOCK_ID: {block_id}"
            )

        proofread_zh = raw.get("proofread_zh", "")
        proofread_note = raw.get("proofread_note", "")

        if not isinstance(proofread_zh, str):
            raise LlmJsonParseError(
                f"{block_id}.proofread_zh 必须是字符串"
            )

        if not isinstance(proofread_note, str):
            raise LlmJsonParseError(
                f"{block_id}.proofread_note 必须是字符串"
            )

        row: Dict[str, Any] = {
            "BLOCK_ID": block_id,
            "proofread_zh": proofread_zh,
            "proofread_note": proofread_note,
        }

        if include_new_terms:
            new_terms = raw.get("new_terms", [])

            if (
                not isinstance(new_terms, list)
                or not all(
                    isinstance(item, dict)
                    for item in new_terms
                )
            ):
                raise LlmJsonParseError(
                    f"{block_id}.new_terms 必须是对象数组"
                )

            row["new_terms"] = new_terms

        if allow_merge:
            merge_value = raw.get("merge_to_prev")

            # 兼容旧模型输出。
            if merge_value is None:
                merge_value = bool(
                    not proofread_zh.strip()
                    and MERGE_NOTE_RE.search(proofread_note)
                )

            if not isinstance(merge_value, bool):
                raise LlmJsonParseError(
                    f"{block_id}.merge_to_prev 必须为布尔值"
                )

            merged_previous_zh = raw.get(
                "merged_previous_zh",
                "",
            )

            if not isinstance(merged_previous_zh, str):
                raise LlmJsonParseError(
                    f"{block_id}.merged_previous_zh 必须是字符串"
                )

            row["merge_to_prev"] = merge_value
            row["merged_previous_zh"] = merged_previous_zh

        normalized[block_id] = row

    missing = [
        block_id
        for block_id in expected
        if block_id not in normalized
    ]

    if missing:
        raise LlmJsonParseError(
            f"缺少 BLOCK_ID: {missing}"
        )

    if len(normalized) != len(expected):
        raise LlmJsonParseError(
            f"返回数量 {len(normalized)} 与"
            f"请求数量 {len(expected)} 不一致"
        )

    # 无论模型返回顺序如何，最终恢复为输入顺序。
    ordered = [
        normalized[block_id]
        for block_id in expected
    ]

    if allow_merge:
        for index, row in enumerate(ordered):
            is_merge = row["merge_to_prev"]

            if is_merge:
                if not MERGE_NOTE_RE.search(
                    row["proofread_note"]
                ):
                    raise LlmJsonParseError(
                        f"{row['BLOCK_ID']} 合并时备注必须"
                        f"明确说明“合并至前段”"
                    )

                if row["proofread_zh"].strip():
                    raise LlmJsonParseError(
                        f"{row['BLOCK_ID']} 合并时"
                        f" proofread_zh 必须为空"
                    )

                # 新格式应当提供完整合并文本。
                # 旧格式只有前一个对象本身已经包含合并结果时才兼容。
                if not row["merged_previous_zh"].strip():
                    if index == 0:
                        raise LlmJsonParseError(
                            f"{row['BLOCK_ID']} 位于当前返回首位，"
                            f"却缺少 merged_previous_zh"
                        )

                    previous_row = ordered[index - 1]

                    if previous_row["merge_to_prev"]:
                        raise LlmJsonParseError(
                            "不允许连续两块都合并至前段"
                        )

                    previous_text = previous_row[
                        "proofread_zh"
                    ].strip()

                    if not previous_text:
                        raise LlmJsonParseError(
                            f"{row['BLOCK_ID']} 无法恢复合并结果"
                        )

                    # 兼容旧结构：上一对象的译文已是合并全文。
                    row["merged_previous_zh"] = previous_text
            else:
                if not row["proofread_zh"].strip():
                    raise LlmJsonParseError(
                        f"{row['BLOCK_ID']} 未标记合并，"
                        f"但 proofread_zh 为空"
                    )

                row["merged_previous_zh"] = ""

        for index in range(1, len(ordered)):
            if (
                ordered[index]["merge_to_prev"]
                and ordered[index - 1]["merge_to_prev"]
            ):
                raise LlmJsonParseError(
                    "不允许出现连续合并链"
                )

    return ordered


def parse_llm_rows(
    text: str,
    expected_ids: Iterable[str],
    *,
    include_new_terms: bool = False,
    allow_merge: bool = False,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    返回：
        (规范化后的数据, 解析模式)

    解析顺序：
        JSON → Python literal → BLOCK_ID 隔离正则
    """
    cleaned = clean_llm_text(text)
    expected = [str(item) for item in expected_ids]
    errors: List[str] = []

    try:
        try:
            parsed = json.loads(cleaned)
            mode = "json"
        except Exception:
            parsed = ast.literal_eval(cleaned)
            mode = "python_literal"

        rows = normalize_and_validate(
            parsed,
            expected,
            include_new_terms=include_new_terms,
            allow_merge=allow_merge,
        )

        return rows, mode

    except Exception as exc:
        errors.append(
            f"结构化解析失败: {exc}"
        )

    try:
        extracted = regex_extract_rows(
            cleaned,
            include_new_terms=include_new_terms,
            allow_merge=allow_merge,
        )

        rows = normalize_and_validate(
            extracted,
            expected,
            include_new_terms=include_new_terms,
            allow_merge=allow_merge,
        )

        return rows, "regex"

    except Exception as exc:
        errors.append(
            f"正则容错失败: {exc}"
        )

    raise LlmJsonParseError(
        "；".join(errors)
    )
