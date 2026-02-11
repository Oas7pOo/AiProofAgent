# ui/tab_proof2.py
import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from utils.config_loader import load_config
from ai.alignment_service import AlignmentService  # 复用 align_batch 的请求/解析方式 :contentReference[oaicite:8]{index=8}
from tools.export_manager import ExportManager
from tools.proofread2_service import Proofread2Project, find_latest_proof2_archive


DEFAULT_DIR_NAME = "archives"


class Proof2Tab(ttk.Frame):
    @staticmethod
    def _ensure_ext(path: str, default_ext: str) -> str:
        if not path or not default_ext:
            return path
        _, ext = os.path.splitext(path)
        if ext:
            return path
        return path + default_ext

    @staticmethod
    def _unique_ext_from_filetypes(filetypes) -> str:
        exts = set()
        for ft in filetypes or []:
            if not ft or len(ft) < 2:
                continue
            pat = str(ft[1])
            for token in pat.split():
                token = token.strip()
                if token.startswith("*.") and " " not in token:
                    # "*.json" -> ".json"
                    exts.add(token[1:])
        return list(exts)[0] if len(exts) == 1 else ""

    def __init__(self, parent):
        super().__init__(parent)

        # ---------------- state ----------------
        self.cfg = None
        self.srv: AlignmentService = None
        self.project: Proofread2Project = None

        self.archive_path = None
        self.batch_queue = []  # List[List[Proof2Item]]
        self.auto_running = False

        # ---------------- ui vars ----------------
        self.mode_var = tk.StringVar(value="new")

        self.stage1_path = tk.StringVar()
        self.old_terms_path = tk.StringVar()
        self.new_terms_path = tk.StringVar()
        self.arc_path_var = tk.StringVar()

        self.status_var = tk.StringVar(value="未开始")

        # ---------------- layout ----------------
        self._build_top_controls()
        self._build_main_panes()

        self._set_ui_ready(False)

        # 新建模式：根据一校文件自动填存档名
        self.stage1_path.trace("w", self._auto_fill_archive_name)
        self.mode_var.trace("w", self._on_mode_change)
        self._on_mode_change()

    # ================= UI =================

    def _build_top_controls(self):
        frm = ttk.LabelFrame(self, text="二校 - 初始化")
        frm.pack(fill="x", padx=10, pady=10)

        # mode
        row0 = ttk.Frame(frm)
        row0.grid(row=0, column=0, columnspan=3, sticky="w", padx=8, pady=6)
        ttk.Label(row0, text="模式:").pack(side="left")
        ttk.Radiobutton(row0, text="新建", variable=self.mode_var, value="new").pack(side="left", padx=6)
        ttk.Radiobutton(row0, text="从存档读取", variable=self.mode_var, value="resume").pack(side="left", padx=6)

        # file rows
        self._row_stage1 = self._create_file_row(frm, "一校结果文件:", 1, self.stage1_path, [("JSON", "*.json")])
        self._row_old_terms = self._create_file_row(frm, "旧术语表:", 2, self.old_terms_path, [("CSV/JSON", "*.csv *.json")])
        self._row_new_terms = self._create_file_row(frm, "新术语表(可选):", 3, self.new_terms_path, [("CSV/JSON", "*.csv *.json")])

        # archive row (save path / load path)
        self._row_arc = self._create_file_row(
            frm, "二校存档:", 4, self.arc_path_var, [("JSON", "*.json")], is_save=True, allow_open_when_resume=True
        )

        # buttons
        btns = ttk.Frame(frm)
        btns.grid(row=5, column=0, columnspan=3, sticky="w", padx=8, pady=10)

        self.btn_start = ttk.Button(btns, text="开始校对", command=self.on_start)
        self.btn_start.pack(side="left", padx=4)

        self.btn_auto = ttk.Button(btns, text="自动校对", command=self.on_auto)
        self.btn_auto.pack(side="left", padx=4)

        self.btn_export_json = ttk.Button(btns, text="导出JSON", command=self.on_export_json)
        self.btn_export_json.pack(side="left", padx=16)

        self.btn_export_md = ttk.Button(btns, text="导出MD", command=self.on_export_md)
        self.btn_export_md.pack(side="left", padx=4)

        ttk.Label(btns, textvariable=self.status_var).pack(side="left", padx=16)

        frm.columnconfigure(1, weight=1)

    def _build_main_panes(self):
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # left
        left = ttk.Frame(paned)
        left_top = ttk.Frame(left)
        left_top.pack(fill="x", pady=4)
        ttk.Label(left_top, text="LeftPane：Prompt（只读）").pack(side="left", padx=4)
        self.btn_copy = ttk.Button(left_top, text="复制Prompt", command=self.on_copy_prompt)
        self.btn_copy.pack(side="right", padx=4)

        self.txt_prompt = tk.scrolledtext.ScrolledText(left, height=20, wrap="word")
        self.txt_prompt.pack(fill="both", expand=True, padx=4, pady=4)
        self._set_text_readonly(self.txt_prompt, True)

        # right
        right = ttk.Frame(paned)
        right_top = ttk.Frame(right)
        right_top.pack(fill="x", pady=4)
        ttk.Label(right_top, text="RightPane：AI结果（可编辑）").pack(side="left", padx=4)
        self.btn_apply = ttk.Button(right_top, text="应用", command=self.on_apply)
        self.btn_apply.pack(side="right", padx=4)

        self.txt_resp = tk.scrolledtext.ScrolledText(right, height=20, wrap="word")
        self.txt_resp.pack(fill="both", expand=True, padx=4, pady=4)

        paned.add(left, weight=1)
        paned.add(right, weight=1)

    def _create_file_row(self, parent, label, row, var, filetypes, is_save=False, allow_open_when_resume=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=4)
        ent = ttk.Entry(parent, textvariable=var, width=60)
        ent.grid(row=row, column=1, sticky="we", padx=6, pady=4)

        def _browse():
            mode = self.mode_var.get()
            if mode == "resume" and allow_open_when_resume:
                path = filedialog.askopenfilename(filetypes=filetypes)
            else:
                if is_save:
                    ext = self._unique_ext_from_filetypes(filetypes)
                    path = filedialog.asksaveasfilename(filetypes=filetypes, defaultextension=ext or None)
                    path = self._ensure_ext(path, ext)
                else:
                    path = filedialog.askopenfilename(filetypes=filetypes)
            if path:
                var.set(path)

        ttk.Button(parent, text="浏览.", width=8, command=_browse).grid(row=row, column=2, padx=6, pady=4)
        return (ent,)

    def _set_text_readonly(self, widget, ro: bool):
        widget.config(state="normal")
        if ro:
            widget.config(state="disabled")

    def _set_ui_ready(self, ready: bool):
        state = "normal" if ready else "disabled"
        self.btn_auto.config(state=state)
        self.btn_apply.config(state=state)
        self.btn_copy.config(state=state)

    def _set_export_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_export_json.config(state=state)
        self.btn_export_md.config(state=state)

    def _on_mode_change(self, *args):
        mode = self.mode_var.get()
        if mode == "resume":
            # 自动填最近存档
            latest = find_latest_proof2_archive(DEFAULT_DIR_NAME)
            if latest:
                self.arc_path_var.set(latest)
        self._set_export_enabled(False)
        self._set_ui_ready(False)

    def _auto_fill_archive_name(self, *args):
        if self.mode_var.get() != "new":
            return
        p = self.stage1_path.get().strip()
        if not p:
            return
        base = os.path.splitext(os.path.basename(p))[0]
        out = os.path.join(DEFAULT_DIR_NAME, base + "_p2.json")
        self.arc_path_var.set(out)

    # ================= workflow =================

    def on_start(self):
        """
        - 新建：读取一校结果 + 旧术语 + (可选)新术语；创建二校存档并入内存；构建第一批并显示 prompt
        - 续校：自动加载最近二校存档；构建待处理批次并显示 prompt
        """
        try:
            self.cfg = load_config()
            self.srv = AlignmentService(self.cfg)

            mode = self.mode_var.get()
            arc = self.arc_path_var.get().strip()

            if mode == "resume":
                if not arc or not os.path.exists(arc):
                    raise ValueError("续校模式：二校存档不存在。")
                self.archive_path = arc
                name = os.path.splitext(os.path.basename(arc))[0]
                self.project = Proofread2Project(name)
                self.project.load_archive(arc)
            else:
                stage1 = self.stage1_path.get().strip()
                old_terms = self.old_terms_path.get().strip()
                new_terms = self.new_terms_path.get().strip()

                if not stage1:
                    raise ValueError("新建模式：必须选择一校结果文件。")
                if not old_terms:
                    raise ValueError("新建模式：必须选择旧术语表。")
                if not arc:
                    raise ValueError("新建模式：必须指定二校存档路径。")

                os.makedirs(os.path.dirname(os.path.abspath(arc)), exist_ok=True)

                name = os.path.splitext(os.path.basename(arc))[0]
                self.archive_path = arc
                self.project = Proofread2Project(name)

                self.project.import_from_stage1_any(stage1)
                self.project.load_terms_old(old_terms)
                self.project.load_terms_new_optional(new_terms if new_terms else None)

                # 初始落盘（存档自包含）
                self.project.run_status = {"proofread2_completed": False}
                self.project.save_archive(arc)

            self._rebuild_batches_and_show_first()

        except Exception as e:
            messagebox.showerror("开始失败", str(e))

    def _rebuild_batches_and_show_first(self):
        if not self.project:
            return

        max_blocks = int(self.cfg.get("max_blocks"))
        max_chars = int(self.cfg.get("max_chars"))

        self.batch_queue = self.project.build_batches(max_blocks=max_blocks, max_chars=max_chars)

        if not self.batch_queue:
            # 已完成
            self.project.mark_completed()
            if self.archive_path:
                self.project.save_archive(self.archive_path)
            self.status_var.set("已完成（无待二校项）")
            self._set_export_enabled(True)
            self._set_ui_ready(False)
            self._set_prompt_text("")
            self._set_resp_text("")
            return

        self.status_var.set(f"已加载：待处理批次 {len(self.batch_queue)}")
        self._set_ui_ready(True)
        self._set_export_enabled(False)
        self._show_current_batch()

    def _show_current_batch(self):
        if not self.batch_queue:
            self.project.mark_completed()
            if self.archive_path:
                self.project.save_archive(self.archive_path)
            self.status_var.set("已完成（全部二校完成）")
            self._set_export_enabled(True)
            self._set_ui_ready(False)
            return

        batch = self.batch_queue[0]
        old_hits, new_hits = self.project.match_terms_for_batch(batch)
        prompt = self.project.build_prompt(batch, old_hits, new_hits)

        self._set_prompt_text(prompt)
        self._set_resp_text("")
        self.status_var.set(f"当前批次：{len(batch)} 块 | 剩余批次：{len(self.batch_queue)}")

    def on_auto(self):
        if self.auto_running:
            return
        if not self.project or not self.batch_queue:
            messagebox.showwarning("提示", "请先点击“开始校对”加载项目。")
            return

        self.auto_running = True
        self.btn_auto.config(state="disabled")
        self.btn_start.config(state="disabled")

        t = threading.Thread(target=self._auto_loop, daemon=True)
        t.start()

    def _auto_loop(self):
        """
        自动校对：
        - 每批最多尝试 3 次
        - 失败后减半 batch（切成两段，前段先处理）
        - 直到 batch=1 仍失败：暂停等待用户手动修改右侧文本框并点击“应用”
        """
        try:
            while self.auto_running and self.batch_queue:
                batch = self.batch_queue[0]

                ok = self._auto_process_one_batch(batch)
                if ok:
                    continue  # 下一批
                else:
                    # 暂停等待人工
                    self.auto_running = False
                    self.after(0, lambda: self.status_var.set("自动校对暂停：等待人工修正并点击“应用”"))
                    self.after(0, lambda: self.btn_start.config(state="normal"))
                    return

            # 全部处理完成
            self.auto_running = False
            self.after(0, lambda: self.btn_start.config(state="normal"))

        except Exception as e:
            self.auto_running = False
            self.after(0, lambda: messagebox.showerror("自动校对异常", str(e)))
            self.after(0, lambda: self.btn_start.config(state="normal"))

    def _auto_process_one_batch(self, batch):
        # 1) 尝试 3 次
        last_raw = ""
        last_parsed = None
        last_err = ""

        for _ in range(3):
            try:
                old_hits, new_hits = self.project.match_terms_for_batch(batch)
                prompt = self.project.build_prompt(batch, old_hits, new_hits)

                payload = {
                    "model": self.cfg["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": self.cfg.get("max_tokens"),
                }
                resp = self.srv.session.post(
                    f"{self.cfg['base_url']}/chat/completions",
                    json=payload,
                    timeout=self.cfg.get("timeout"),
                )

                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}: {resp.text}"
                    continue

                result = resp.json()
                content = result["choices"][0]["message"]["content"]
                last_raw = content
                parsed = self.srv.parser.clean_and_parse_batch_json(content)  # 复用你现有解析器 :contentReference[oaicite:9]{index=9}
                last_parsed = parsed

                self.after(0, lambda txt=content: self._set_resp_text(txt))

                ok, msg = self.project.validate_results(batch, parsed)
                if ok:
                    self.project.apply_results(parsed)
                    self.project.save_archive(self.archive_path)

                    # pop batch + show next
                    self.batch_queue.pop(0)
                    self.after(0, self._show_current_batch)
                    return True
                else:
                    last_err = msg

            except Exception as e:
                last_err = str(e)

        # 2) 仍失败：减半或暂停
        self.after(0, lambda txt=last_raw: self._set_resp_text(txt))
        if len(batch) > 1:
            mid = max(1, len(batch) // 2)
            first = batch[:mid]
            second = batch[mid:]

            # 替换当前 batch 为 first，并把 second 插到后面
            self.batch_queue[0] = first
            if second:
                self.batch_queue.insert(1, second)

            self.after(0, lambda: self.status_var.set(f"自动校对失败，已减半：{len(batch)} -> {len(first)} + {len(second)}"))
            self.after(0, self._show_current_batch)
            return True

        # len==1 仍失败：暂停等待人工
        self.after(0, lambda: messagebox.showwarning("自动校对暂停", f"单块仍失败：{last_err}\n请在右侧手动修正 JSON 后点击“应用”。"))
        self.after(0, lambda: self.btn_auto.config(state="normal"))
        return False

    def on_apply(self):
        if not self.project or not self.batch_queue:
            return

        raw = self.txt_resp.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("提示", "右侧内容为空。")
            return

        batch = self.batch_queue[0]
        parsed = self.srv.parser.clean_and_parse_batch_json(raw)
        ok, msg = self.project.validate_results(batch, parsed)
        if not ok:
            messagebox.showerror("应用失败", msg)
            return

        self.project.apply_results(parsed)
        self.project.save_archive(self.archive_path)

        self.batch_queue.pop(0)
        self._show_current_batch()

    # ================= export =================

    def _ensure_completed(self):
        if not self.project:
            raise ValueError("未加载二校项目。")
        if not self.project.is_completed():
            raise ValueError("二校尚未完成，不能导出。")

    def on_export_json(self):
        try:
            self._ensure_completed()

            out = filedialog.asksaveasfilename(filetypes=[("JSON", "*.json")], defaultextension=".json")
            out = self._ensure_ext(out, ".json")
            if not out:
                return

            exporter = ExportManager(
                archive_path=self.archive_path,
                out_final_json=out,
                out_md=None,
                out_terms_json=None,
            )
            # 二校不导出术语
            exporter.export_all(export_final=True, export_md=False, export_terms=False)
            messagebox.showinfo("导出成功", f"已导出 JSON:\n{out}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def on_export_md(self):
        try:
            self._ensure_completed()

            out = filedialog.asksaveasfilename(filetypes=[("Markdown", "*.md")], defaultextension=".md")
            out = self._ensure_ext(out, ".md")
            if not out:
                return

            exporter = ExportManager(
                archive_path=self.archive_path,
                out_final_json=None,
                out_md=out,
                out_terms_json=None,
            )
            exporter.export_all(export_final=False, export_md=True, export_terms=False)
            messagebox.showinfo("导出成功", f"已导出 MD:\n{out}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ================= misc =================

    def on_copy_prompt(self):
        try:
            txt = self.txt_prompt.get("1.0", tk.END)
            self.clipboard_clear()
            self.clipboard_append(txt)
        except Exception as e:
            messagebox.showerror("复制失败", str(e))

    def _set_prompt_text(self, text: str):
        self.txt_prompt.config(state="normal")
        self.txt_prompt.delete("1.0", tk.END)
        self.txt_prompt.insert(tk.END, text)
        self.txt_prompt.see(tk.END)
        self.txt_prompt.config(state="disabled")

    def _set_resp_text(self, text: str):
        self.txt_resp.config(state="normal")
        self.txt_resp.delete("1.0", tk.END)
        self.txt_resp.insert(tk.END, text)
        self.txt_resp.see(tk.END)
