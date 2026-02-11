# tools/export_manager.py
import os
import re
from .io_utils import load_json, save_json


class ExportManager:
    """
    支持三种导出产物分别指定输出路径：
      - out_final_json
      - out_md
      - out_terms_json
    未指定时：默认输出到 default_dir（默认 archives），文件名由存档名推导。

    新增：export_all 支持选择性导出（单独导出某一种文件）。
    """

    def __init__(
        self,
        archive_path: str,
        out_final_json: str | None = None,
        out_md: str | None = None,
        out_terms_json: str | None = None,
        default_dir: str = "archives",
    ):
        self.archive_path = archive_path
        if not os.path.exists(archive_path):
            raise FileNotFoundError(f"存档不存在: {archive_path}")

        self.default_dir = os.path.abspath(default_dir)
        os.makedirs(self.default_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(archive_path))[0]

        # 默认命名：与原实现保持一致
        self.out_final_json = out_final_json or os.path.join(self.default_dir, f"{base_name}_final.json")
        self.out_md = out_md or os.path.join(self.default_dir, f"{base_name}_final.md")
        self.out_terms_json = out_terms_json or os.path.join(self.default_dir, f"{base_name}_new_terms.json")

    def export_all(self, export_final: bool = True, export_md: bool = True, export_terms: bool = True):
        """
        选择性导出：
          export_final=True  -> 导出 final json
          export_md=True     -> 导出 md
          export_terms=True  -> 导出 new_terms json

        向后兼容：不传参时默认全导出（旧行为）。
        """
        if not (export_final or export_md or export_terms):
            raise ValueError("未选择任何导出类型")

        data = load_json(self.archive_path)
        if not data:
            raise ValueError("存档损坏")
        items = data.get("items", [])
        if not items:
            raise ValueError("无数据")

        generated_files = []

        if export_final:
            self._ensure_parent_dir(self.out_final_json)
            self._export_final_json(items, self.out_final_json)
            generated_files.append(self.out_final_json)

        if export_md:
            self._ensure_parent_dir(self.out_md)
            title = os.path.splitext(os.path.basename(self.archive_path))[0]
            self._export_markdown(items, title, self.out_md)
            generated_files.append(self.out_md)

        if export_terms:
            self._ensure_parent_dir(self.out_terms_json)
            self._export_terms(items, self.out_terms_json)
            generated_files.append(self.out_terms_json)

        return generated_files

    @staticmethod
    def _ensure_parent_dir(path: str):
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _export_final_json(self, items, path):
        final_list = []
        for it in items:
            final_list.append(
                {
                    "key": it.get("key", ""),
                    "original": it.get("en_block", ""),
                    "translation": it.get("zh_block", ""),
                    "proofread": it.get("proofread_zh", ""),
                    "suggestion": it.get("proofread_note", ""),
                }
            )
        save_json(path, final_list)

    def _export_markdown(self, items, title, path):
        """
        生成人类可读报告。
        逻辑优化：以原文层级为准，强制清洗译文中的 # 号，防止重复。
        """
        header_pat = re.compile(r"^(#{1,6})\s+(.*)", re.DOTALL)
        clean_pat = re.compile(r"^#+\s*")

        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 校对报告: {title}\n\n")
            f.write("> 目录结构基于原文 Markdown 标记还原\n\n")

            for it in items:
                original = it.get("en_block", "").strip()
                proof = it.get("proofread_zh", "").strip()
                note = it.get("proofread_note", "").strip()
                key = it.get("key", "")

                match = header_pat.match(original)

                if match:
                    hashes = match.group(1)
                    clean_original = match.group(2).strip()

                    clean_proof = clean_pat.sub("", proof).strip()
                    display_title = clean_proof if clean_proof else clean_original

                    f.write(f"{hashes} {display_title}\n\n")
                    f.write(f"*{clean_original}* `[{key}]`\n\n")

                    if note:
                        f.write(f"> 标题建议: {note}\n\n")
                else:
                    f.write(f"**[{key}]**\n")
                    f.write(f"> 原文: {original}\n")

                    clean_proof_body = clean_pat.sub("", proof).strip()
                    if clean_proof_body:
                        f.write(f"> 校对: **{clean_proof_body}**\n")

                    if note:
                        f.write(f"> *建议: {note}*\n")
                    f.write("\n")

    def _export_terms(self, items, path):
        all_terms = []
        for it in items:
            raw_terms = it.get("new_terms", [])
            if raw_terms and isinstance(raw_terms, list):
                all_terms.extend(raw_terms)

        seen = set()
        unique_terms = []
        for t in all_terms:
            if not isinstance(t, dict):
                continue

            term = t.get("term", "").strip()
            if not term:
                continue

            k = term.lower()
            if k in seen:
                continue  # 同一英文术语多次出现：只保留第一次
            seen.add(k)

            unique_terms.append({
                "term": term,
                "translation": t.get("translation", "").strip(),
                "note": t.get("note", "").strip(),
            })

        save_json(path, unique_terms)

