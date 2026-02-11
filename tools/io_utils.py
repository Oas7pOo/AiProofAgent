from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Union

import pandas as pd
import json
import os
from typing import Any, List, Optional

DEFAULT_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")

def _sniff_delimiter(sample: str) -> str:
    # 常见分隔符：逗号 / Tab / 分号 / 竖线
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=[",", "\t", ";", "|"])
        return dialect.delimiter
    except Exception:
        # 兜底：Tab 多就认为是 TSV，否则 CSV
        return "\t" if sample.count("\t") > sample.count(",") else ","


def _pick_encoding(file_path: str, encodings: Iterable[str]) -> str:
    p = Path(file_path)
    with p.open("rb") as f:
        head = f.read(8192)
    last = None
    for enc in encodings:
        try:
            head.decode(enc)
            return enc
        except UnicodeDecodeError as e:
            last = e
    raise ValueError(f"无法用候选编码解码文件头部: {file_path}. last_error={last}")


def _looks_like_header_row(row0: List[str]) -> bool:
    # 你们常见表头关键词（按需加）
    joined = " ".join((c or "").strip().lower() for c in row0[:6])
    header_tokens = ("key", "original", "translation", "stage", "en", "zh", "id", "block")
    return any(tok in joined for tok in header_tokens)


def _normalize_header_name(x: str) -> str:
    x = (x or "").strip()
    x = x.lstrip("\ufeff")  # 去 BOM
    return x


def read_csv_raw(
    file_path: str,
    *,
    encodings: Iterable[str] = DEFAULT_ENCODINGS,
    delimiter: Optional[str] = None,
    strict: bool = True,
) -> pd.DataFrame:
    """
    只负责“读进来”，不做业务列映射。
    - 永远 header=None（避免把第一列/第一行搞没）
    - dtype=str + 不产生 NaN
    - 自动嗅探分隔符
    """
    encoding = _pick_encoding(file_path, encodings)

    # 嗅探分隔符（用文件头部）
    if delimiter is None:
        with open(file_path, "r", encoding=encoding, errors="strict") as f:
            sample = f.read(8192)
        delimiter = _sniff_delimiter(sample)

    on_bad_lines = "error" if strict else "warn"

    try:
        df = pd.read_csv(
            file_path,
            sep=delimiter,
            header=None,
            dtype=str,
            engine="python",
            keep_default_na=False,
            na_filter=False,
            on_bad_lines=on_bad_lines,
            encoding=encoding,
        )
    except pd.errors.ParserError as e:
        raise ValueError(
            f"CSV 解析失败（列数不一致/引号未闭合/分隔符误判）。"
            f" file={file_path}, sep={repr(delimiter)}, encoding={encoding}, detail={e}"
        ) from e

    return df.fillna("")


SchemaType = Union[Sequence[str], Mapping[str, int]]


def read_csv_schema(
    file_path: str,
    schema: Optional[SchemaType] = None,
    *,
    drop_first_row: Union[bool, str] = "auto",
    treat_first_row_as_header: Union[bool, str] = "auto",
    encodings: Iterable[str] = DEFAULT_ENCODINGS,
    delimiter: Optional[str] = None,
    strict: bool = True,
) -> pd.DataFrame:
    """
    在 raw 的基础上做“业务视角”的列映射：
    - 可自动识别并丢掉表头/垃圾首行
    - schema 支持：
        * ["key","en","zh"]  => 按位置取前 N 列；不足补空；多余忽略
        * {"key":0,"en":1,"zh":2} => 按位置精确取列
    """
    df = read_csv_raw(
        file_path,
        encodings=encodings,
        delimiter=delimiter,
        strict=strict,
    )

    # 自动把第一行当表头（仅当你没给 schema，或者你明确想利用表头）
    if treat_first_row_as_header == "auto":
        use_header = _looks_like_header_row(df.iloc[0].tolist()) if not df.empty else False
    else:
        use_header = bool(treat_first_row_as_header)

    if use_header and not df.empty:
        header = [_normalize_header_name(x) for x in df.iloc[0].tolist()]
        df = df.iloc[1:].reset_index(drop=True)
        df.columns = header

    # 自动丢首行：表头已丢过就不再丢；否则按需要丢“垃圾首行”
    if drop_first_row == "auto":
        # 如果没用表头，则：首行像表头就丢；或者首行第一格就是 "key"/"id" 也丢
        if not use_header and not df.empty:
            c0 = str(df.iat[0, 0]).strip().lower() if df.shape[1] > 0 else ""
            if c0 in ("key", "id", "index") or _looks_like_header_row(df.iloc[0].tolist()):
                df = df.iloc[1:].reset_index(drop=True)
    elif drop_first_row is True:
        df = df.iloc[1:].reset_index(drop=True)

    # 业务列映射
    if schema is None:
        return df.fillna("")

    if isinstance(schema, Mapping):
        out = {}
        for name, idx in schema.items():
            idx = int(idx)
            out[name] = df.iloc[:, idx] if idx < df.shape[1] else ""
        return pd.DataFrame(out).fillna("")

    # schema 是 list[str]：按位置取前 N 列；不足补空
    names = list(schema)
    out_cols = {}
    for i, name in enumerate(names):
        out_cols[name] = df.iloc[:, i] if i < df.shape[1] else ""
    return pd.DataFrame(out_cols).fillna("")

def load_json(file_path: str) -> Any:
    """通用 JSON 读取"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        # JSON 格式错也必须炸
        raise ValueError(f"JSON 格式损坏: {file_path}\n错误: {e}")

def save_json(file_path: str, data: Any) -> None:
    """通用 JSON 写入"""
    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)