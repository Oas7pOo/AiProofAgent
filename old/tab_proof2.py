import os
import glob
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import logging
import json
from typing import Optional

from utils.config import ConfigManager
from workflows.proofread2_flow import Proofread2Workflow
from core.format_converter import FormatConverter

DEFAULT_DIR_NAME = "archives"


def find_latest_proof2_archive(archives_dir: str = "archives") -> Optional[str]:
    """
    自动搜索最近一次二校存档：
    1) 优先匹配 *_p2.json
    2) 兜底：扫描 .json 且包含二校数据
    """
    if not os.path.isdir(archives_dir):
        return None

    # 1) 文件名约定优先
    cand = []
    for fn in os.listdir(archives_dir):
        if fn.lower().endswith("_p2.json"):
            cand.append(os.path.join(archives_dir, fn))
    if cand:
        cand.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return cand[0]

    # 2) 兜底：扫描所有 json 文件
    pat = os.path.join(archives_dir, "*.json")
    files = glob.glob(pat)
    if not files:
        return None

    # 过滤掉最终导出文件和术语文件
    valid = [f for f in files if "_final" not in f and "_new_terms" not in f and "_paratranz" not in f]
    if not valid:
        return None

    # 按修改时间排序，返回最新的
    latest = max(valid, key=os.path.getmtime)
    return latest


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
        self.workflow: Proofread2Workflow = None

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
        # 1. 任务模式（与一校统一）
        mode_frame = ttk.LabelFrame(self, text="任务模式")
        mode_frame.pack(fill="x", padx=10, pady=5)
        ttk.Radiobutton(
            mode_frame, text="新任务", variable=self.mode_var, value="new",
            command=self._on_mode_change
        ).pack(side="left", padx=20, pady=10)
        ttk.Radiobutton(
            mode_frame, text="继续任务 (从存档)", variable=self.mode_var, value="resume",
            command=self._on_mode_change
        ).pack(side="left", padx=20, pady=10)

        # 2. 文件配置
        self.grp_files = ttk.LabelFrame(self, text="文件配置")
        self.grp_files.pack(fill="x", padx=10, pady=5)

        # 一校结果文件
        self.lbl_stage1 = ttk.Label(self.grp_files, text="一校结果文件:")
        self.ent_stage1 = ttk.Entry(self.grp_files, width=50, textvariable=self.stage1_path)
        self.btn_stage1 = ttk.Button(
            self.grp_files, text="...", width=4,
            command=lambda: self._sel_file(self.ent_stage1, [("JSON", "*.json")])
        )

        # 旧术语表
        self.lbl_old_terms = ttk.Label(self.grp_files, text="旧术语表:")
        self.ent_old_terms = ttk.Entry(self.grp_files, width=50, textvariable=self.old_terms_path)
        self.btn_old_terms = ttk.Button(
            self.grp_files, text="...", width=4,
            command=lambda: self._sel_file(self.ent_old_terms, [("CSV/JSON", "*.csv *.json")])
        )

        # 新术语表（可选）
        self.lbl_new_terms = ttk.Label(self.grp_files, text="新术语表(可选):")
        self.ent_new_terms = ttk.Entry(self.grp_files, width=50, textvariable=self.new_terms_path)
        self.btn_new_terms = ttk.Button(
            self.grp_files, text="...", width=4,
            command=lambda: self._sel_file(self.ent_new_terms, [("CSV/JSON", "*.csv *.json")])
        )

        # 存档路径
        self.lbl_arc = ttk.Label(self.grp_files, text="二校存档:")
        self.ent_arc = ttk.Entry(self.grp_files, width=50, textvariable=self.arc_path_var)
        self.btn_arc = ttk.Button(self.grp_files, text="...", width=4)

        self.grp_files.columnconfigure(1, weight=1)

        # 3. 按钮区
        btn_fr = ttk.Frame(self, padding=(0, 10))
        btn_fr.pack(fill="x", padx=10)

        self.btn_start = ttk.Button(btn_fr, text="开始校对", command=self.on_start)
        self.btn_start.pack(side="left", padx=5)

        self.btn_auto = ttk.Button(btn_fr, text="自动校对", command=self.on_auto)
        self.btn_auto.pack(side="left", padx=5)

        self.btn_batch = ttk.Button(btn_fr, text="批量校对", command=self.on_batch)
        self.btn_batch.pack(side="left", padx=5)

        self.btn_export_json = ttk.Button(btn_fr, text="导出JSON", command=self.on_export_json)
        self.btn_export_json.pack(side="left", padx=16)

        self.btn_export_para_json = ttk.Button(btn_fr, text="导出Paratranz JSON", command=self.export_para_json)
        self.btn_export_para_json.pack(side="left", padx=5)

        self.btn_export_para_csv = ttk.Button(btn_fr, text="导出Paratranz CSV", command=self.export_para_csv)
        self.btn_export_para_csv.pack(side="left", padx=5)

        self.btn_export_state_json = ttk.Button(btn_fr, text="导出内部状态JSON", command=self.export_state_json)
        self.btn_export_state_json.pack(side="left", padx=5)

        self.btn_export_doc = ttk.Button(btn_fr, text="导出DOC", command=self.on_export_doc)
        self.btn_export_doc.pack(side="left", padx=5)

        ttk.Label(btn_fr, textvariable=self.status_var).pack(side="left", padx=16)

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

        self.txt_prompt = scrolledtext.ScrolledText(left, height=20, wrap="word")
        self.txt_prompt.pack(fill="both", expand=True, padx=4, pady=4)
        self._set_text_readonly(self.txt_prompt, True)

        # right
        right = ttk.Frame(paned)
        right_top = ttk.Frame(right)
        right_top.pack(fill="x", pady=4)
        ttk.Label(right_top, text="RightPane：AI结果（可编辑）").pack(side="left", padx=4)
        self.btn_apply = ttk.Button(right_top, text="应用", command=self.on_apply)
        self.btn_apply.pack(side="right", padx=4)

        self.txt_resp = scrolledtext.ScrolledText(right, height=20, wrap="word")
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
        self.btn_batch.config(state=state)
        self.btn_apply.config(state=state)
        self.btn_copy.config(state=state)

    def _set_export_enabled(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        self.btn_export_json.config(state=state)
        self.btn_export_para_json.config(state=state)
        self.btn_export_para_csv.config(state=state)
        self.btn_export_state_json.config(state=state)
        self.btn_export_doc.config(state=state)

    def _on_mode_change(self, *args):
        mode = self.mode_var.get()

        # 清除所有控件的布局
        for w in self.grp_files.winfo_children():
            w.grid_forget()

        self._set_export_enabled(False)
        self._set_ui_ready(False)

        if mode == "new":
            # 新任务模式：显示所有输入框
            self.lbl_stage1.grid(row=0, column=0, padx=5, pady=5, sticky="w")
            self.ent_stage1.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
            self.btn_stage1.grid(row=0, column=2, padx=5, pady=5)

            self.lbl_old_terms.grid(row=1, column=0, padx=5, pady=5, sticky="w")
            self.ent_old_terms.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
            self.btn_old_terms.grid(row=1, column=2, padx=5, pady=5)

            self.lbl_new_terms.grid(row=2, column=0, padx=5, pady=5, sticky="w")
            self.ent_new_terms.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
            self.btn_new_terms.grid(row=2, column=2, padx=5, pady=5)

            self.lbl_arc.config(text="生成存档:")
            self.lbl_arc.grid(row=3, column=0, padx=5, pady=5, sticky="w")
            self.ent_arc.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
            self.btn_arc.config(
                command=lambda: self._sel_file(
                    self.ent_arc, [("JSON", "*.json")],
                    save=True, init_dir=DEFAULT_DIR_NAME
                )
            )
            self.btn_arc.grid(row=3, column=2, padx=5, pady=5)

        else:  # resume
            # 继续任务模式：只显示存档选择框
            self.lbl_arc.config(text="选择存档:")
            self.lbl_arc.grid(row=0, column=0, padx=5, pady=5, sticky="w")
            self.ent_arc.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
            self.btn_arc.config(
                command=lambda: self._sel_file(
                    self.ent_arc, [("JSON", "*.json")],
                    save=False, init_dir=DEFAULT_DIR_NAME
                )
            )
            self.btn_arc.grid(row=0, column=2, padx=5, pady=5)

            # 自动加载最新存档
            latest = find_latest_proof2_archive(DEFAULT_DIR_NAME)
            if latest:
                self.arc_path_var.set(latest)

    def _sel_file(self, entry, filetypes, save=False, init_dir=None):
        """辅助方法：选择文件"""
        kw = {"filetypes": filetypes}
        if init_dir and os.path.exists(init_dir):
            kw["initialdir"] = init_dir

        default_ext = ""
        if save and filetypes:
            pat = str(filetypes[0][1]).strip()
            if pat.startswith("*.") and " " not in pat:
                default_ext = pat[1:]
                kw["defaultextension"] = default_ext

        f = filedialog.asksaveasfilename if save else filedialog.askopenfilename
        p = f(**kw)
        if p:
            if save and default_ext and not os.path.splitext(p)[1]:
                p += default_ext
            entry.delete(0, tk.END)
            entry.insert(0, p)

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
            self.cfg = ConfigManager()
            
            # 读取配置参数
            max_workers = int(self.cfg.get("llm.ai_max_workers", 1))
            delay_seconds = int(self.cfg.get("llm.time_wait", 10))
            max_blocks = int(self.cfg.get("llm.max_blocks", 10))
            max_chars = int(self.cfg.get("llm.max_chars", 8000))
            
            # 开始校对和自动校对模式使用1并发
            start_auto_max_workers = 1
            
            # 初始化工作流，传递配置参数
            self.workflow = Proofread2Workflow(
                max_workers=start_auto_max_workers,
                delay_seconds=delay_seconds,
                max_blocks=max_blocks,
                max_chars=max_chars
            )

            mode = self.mode_var.get()
            arc = self.arc_path_var.get().strip()

            if mode == "resume":
                if not arc or not os.path.exists(arc):
                    raise ValueError("续校模式：二校存档不存在。")
                self.archive_path = arc
                # 从二校存档加载
                self.workflow.init_session(arc)
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

                self.archive_path = arc

                # 初始化二校工作流
                self.workflow.init_session(arc, stage1, old_terms, new_terms)

            self._rebuild_batches_and_show_first()

        except Exception as e:
            messagebox.showerror("开始失败", str(e))

    def _rebuild_batches_and_show_first(self):
        if not self.workflow:
            return

        # 使用工作流实例的配置参数
        max_blocks = self.workflow.max_blocks
        max_chars = self.workflow.max_chars

        # 构建批次
        batch_count = self.workflow.build_batches(max_blocks=max_blocks, max_chars=max_chars)
        self.batch_queue = self.workflow.pending_queue

        if not self.batch_queue:
            # 已完成
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
            self.status_var.set("已完成（全部二校完成）")
            self._set_export_enabled(True)
            self._set_ui_ready(False)
            return

        batch = self.batch_queue[0]
        # 构建prompt
        prompt = self.workflow.build_prompt_for_batch(batch)

        self._set_prompt_text(prompt)
        self._set_resp_text("")
        self.status_var.set(f"当前批次：{len(batch)} 块 | 剩余批次：{len(self.batch_queue)}")

    def on_auto(self):
        if self.auto_running:
            return
        if not self.workflow or not self.batch_queue:
            messagebox.showwarning("提示", "请先点击“开始校对”加载项目。")
            return

        self.auto_running = True
        self.btn_auto.config(state="disabled")
        self.btn_start.config(state="disabled")

        t = threading.Thread(target=self._auto_loop, daemon=True)
        t.start()

    def on_batch(self):
        if not self.workflow or not self.batch_queue:
            messagebox.showwarning("提示", "请先点击“开始校对”加载项目。")
            return

        # 获取配置中的参数
        max_workers = int(self.cfg.get("llm.ai_max_workers", 1))
        delay_seconds = int(self.cfg.get("llm.time_wait", 10))
        max_blocks = int(self.cfg.get("llm.max_blocks", 10))
        max_chars = int(self.cfg.get("llm.max_chars", 8000))

        if max_workers <= 0:
            max_workers = 1

        # 禁用按钮，避免重复点击
        self.btn_batch.config(state="disabled")
        self.btn_start.config(state="disabled")
        self.btn_auto.config(state="disabled")

        # 在后台线程中执行批量校对
        def batch_task():
            try:
                # 创建一个新的工作流实例，使用配置的并发数
                batch_workflow = Proofread2Workflow(
                    max_workers=max_workers,
                    delay_seconds=delay_seconds,
                    max_blocks=max_blocks,
                    max_chars=max_chars
                )
                
                # 加载数据
                batch_workflow.init_session(self.archive_path)
                
                total_batches = len(batch_workflow.pending_queue)
                self.status_var.set(f"开始批量校对，并发数: {max_workers}，总批次: {total_batches}")
                
                # 定义进度更新回调
                def update_progress(processed, total):
                    self.after(0, lambda: self.status_var.set(f"批量校对中: {processed}/{total} 批次"))
                
                # 调用 Proofread2Workflow 的 run_bulk_async 方法
                batch_workflow.run_bulk_async(
                    progress_callback=update_progress,
                    done_callback=lambda blocks: self.after(0, self._rebuild_batches_and_show_first),
                    error_callback=lambda e: self.after(0, lambda: messagebox.showerror("批量校对异常", str(e)))
                )
                # 校对完成后更新 UI
                self.after(0, lambda: self.status_var.set("批量校对完成"))
                self.after(0, lambda: self._rebuild_batches_and_show_first())
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("批量校对异常", str(e)))
                self.after(0, lambda: self.status_var.set(f"批量校对失败: {str(e)}"))
            finally:
                # 恢复按钮状态
                self.after(0, lambda: self.btn_batch.config(state="normal"))
                self.after(0, lambda: self.btn_start.config(state="normal"))
                self.after(0, lambda: self.btn_auto.config(state="normal"))

        t = threading.Thread(target=batch_task, daemon=True)
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
        last_err = ""

        for _ in range(3):
            try:
                # 构建prompt
                prompt = self.workflow.build_prompt_for_batch(batch)
                # 发送请求
                response = self.workflow.request_llm(prompt)
                last_raw = response
                # 验证结果
                valid, msg, data = self.workflow.parse_and_validate(batch, response)
                if not valid:
                    last_err = msg
                    continue

                self.after(0, lambda txt=response: self._set_resp_text(txt))

                # 应用结果
                self.workflow.apply_batch(batch, data)

                # pop batch + show next
                self.batch_queue.pop(0)
                self.after(0, self._show_current_batch)
                return True

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
        if not self.workflow or not self.batch_queue:
            return

        raw = self.txt_resp.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("提示", "右侧内容为空。")
            return

        batch = self.batch_queue[0]
        # 解析和验证结果
        valid, msg, data = self.workflow.parse_and_validate(batch, raw)
        if not valid:
            messagebox.showerror("应用失败", msg)
            return

        # 应用结果
        self.workflow.apply_batch(batch, data)

        # 从队列中移除已处理的批次
        self.batch_queue.pop(0)
        self._show_current_batch()

    # ================= export =================

    def _ensure_completed(self):
        if not self.workflow:
            raise ValueError("未加载二校项目。")

    def on_export_json(self):
        try:
            if not self.workflow:
                raise ValueError("未加载二校项目。")

            out = self._ask_save_path("json")
            if not out:
                return

            # 导出最终 JSON
            FormatConverter.export_final_json(self.workflow.blocks, out)
            messagebox.showinfo("导出成功", f"已导出 JSON:\n{os.path.basename(out)}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def on_export_doc(self):
        try:
            if not self.workflow:
                raise ValueError("未加载二校项目。")

            out = self._ask_save_path("doc")
            if not out:
                return

            # 1. 生成 Markdown 内容
            from core.md2doc import parse_and_convert
            md_content = self._generate_markdown_content(self.workflow.blocks, is_proof2=True)
            
            # 2. 转换为 DOC
            parse_and_convert(md_content, out)
            messagebox.showinfo("导出成功", f"已导出 DOC:\n{os.path.basename(out)}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_para_json(self):
        try:
            if not self.workflow:
                raise ValueError("未加载二校项目。")

            out = self._ask_save_path("para_json")
            if not out:
                return

            # 导出 Paratranz JSON
            paratranz_data = []
            for b in self.workflow.blocks:
                translation = b.proofread_zh or b.proofread1_zh or b.zh_block or ""
                paratranz_data.append({
                    "key": b.key,
                    "original": b.en_block,
                    "translation": translation,
                    "stage": b.stage
                })
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(paratranz_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"已导出 Paratranz JSON：\n{os.path.basename(out)}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_para_csv(self):
        try:
            if not self.workflow:
                raise ValueError("未加载二校项目。")

            out = self._ask_save_path("para_csv")
            if not out:
                return

            # 导出 Paratranz CSV
            import csv
            with open(out, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                for b in self.workflow.blocks:
                    translation = b.proofread_zh or b.proofread1_zh or b.zh_block or ""
                    writer.writerow([b.key, b.en_block, translation])
            messagebox.showinfo("成功", f"已导出 Paratranz CSV：\n{os.path.basename(out)}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_state_json(self):
        try:
            if not self.workflow:
                raise ValueError("未加载二校项目。")

            out = self._ask_save_path("state_json")
            if not out:
                return

            # 导出内部状态 JSON
            simple_data = []
            for block in self.workflow.blocks:
                simple_data.append({
                    "key": block.key,
                    "en_block": block.en_block,
                    "zh_block": block.zh_block,
                    "proofread1_zh": block.proofread1_zh,
                    "proofread1_note": block.proofread1_note,
                    "proofread_zh": block.proofread_zh,
                    "proofread_note": block.proofread_note
                })
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(simple_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"已导出内部状态 JSON：\n{os.path.basename(out)}")

        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _suggest_export(self, kind: str):
        """根据导出类型生成默认文件名和路径"""
        if not self.workflow or not self.archive_path:
            base = "export"
        else:
            base = os.path.splitext(os.path.basename(self.archive_path))[0]

        # 默认目录：优先“上次导出目录”，否则用存档所在目录，否则 archives
        out_dir = getattr(self, "_last_export_dir", "") or \
                  (os.path.dirname(os.path.abspath(self.archive_path)) if self.archive_path else "") or \
                  os.path.abspath(DEFAULT_DIR_NAME)

        if kind == "para_json":
            return out_dir, f"{base}_paratranz.json", [("JSON", "*.json")], ".json"
        if kind == "para_csv":
            return out_dir, f"{base}_paratranz.csv", [("CSV", "*.csv")], ".csv"
        if kind == "doc":
            return out_dir, f"{base}_final.docx", [("Word Document", "*.docx")], ".docx"
        if kind == "state_json":
            return out_dir, f"{base}_state.json", [("JSON", "*.json")], ".json"
        if kind == "json":
            return out_dir, f"{base}_final.json", [("JSON", "*.json")], ".json"
        raise ValueError(f"unknown export kind: {kind}")

    def _generate_markdown_content(self, blocks, is_proof2=False):
        """生成 Markdown 内容字符串"""
        import re
        header_pat = re.compile(r"^(#{1,6})\s+(.*)", re.DOTALL)
        clean_pat = re.compile(r"^#+\s*")
        
        lines = []
        lines.append("# 校对报告\n")
        lines.append("> 目录结构基于原文 Markdown 标记还原\n")
        
        for block in blocks:
            original = block.en_block.strip()
            key = block.key
            
            # 获取原始译文（一校结果）
            original_translation = block.proofread1_zh or block.zh_block or ""
            original_translation = original_translation.strip()
            
            # 根据是一校还是二校选择对应的校对译文和注释
            if is_proof2:
                proof = block.proofread_zh or block.proofread1_zh or ""
                note = block.proofread_note or ""
            else:
                proof = block.proofread1_zh or ""
                note = block.proofread1_note or ""
            
            proof = proof.strip()
            note = note.strip()
            
            match = header_pat.match(original)
            
            if match:
                hashes = match.group(1)
                clean_original = match.group(2).strip()
                
                clean_proof = clean_pat.sub("", proof).strip()
                display_title = clean_proof if clean_proof else clean_original
                
                lines.append(f"\n{hashes} {display_title}\n")
                lines.append(f"*{clean_original}* `[{key}]`\n")
                
                if original_translation:
                    lines.append(f"> 原始译文: {original_translation}\n")
                
                if note:
                    lines.append(f"> 标题建议: {note}\n")
            else:
                lines.append(f"\n**[{key}]**\n")
                lines.append(f"> 原文: {original}\n")
                
                if original_translation:
                    lines.append(f"> 原始译文: {original_translation}\n")
                
                if proof:
                    lines.append(f"> 校对: **{proof}**\n")
                
                if note:
                    lines.append(f"> *建议: {note}*\n")
        
        return "\n".join(lines)

    def _ask_save_path(self, kind: str) -> str | None:
        """弹出保存对话框，自动填写默认文件名"""
        out_dir, default_name, filetypes, ext = self._suggest_export(kind)
        os.makedirs(out_dir, exist_ok=True)

        p = filedialog.asksaveasfilename(
            initialdir=out_dir,
            initialfile=default_name,
            defaultextension=ext,
            filetypes=filetypes,
        )
        if not p:
            return None

        p = os.path.abspath(p)
        if os.path.exists(p):
            ok = messagebox.askyesno("确认覆盖", f"文件已存在，是否覆盖？\n{p}")
            if not ok:
                return None

        # 记录上次导出目录
        self._last_export_dir = os.path.dirname(p)
        return p

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