# tab_run.py
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import sys
import os
import glob
import json
from datetime import datetime
import logging

from workflows.proofread1_flow import Proofread1Workflow
from utils.config import ConfigManager
from core.format_converter import FormatConverter
from ui.gui_logger import setup_gui_logger

DEFAULT_DIR_NAME = "archives"
logger = logging.getLogger("AiProofAgent.RunTab")


class RunTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=10, pady=10)

        self.is_running = False
        self.mode_var = tk.StringVar(value="new")

        # 存档路径变量（project archive）
        self.arc_var = tk.StringVar()

        # 本次 UI 会话内：是否完成（用于控制导出区显示）
        self._run_completed = False

        # 记录上一次导出目录（用于 asksaveas 默认目录）
        self._last_export_dir = ""

        if not os.path.exists(DEFAULT_DIR_NAME):
            os.makedirs(DEFAULT_DIR_NAME)

        self.setup_ui()
        
        # 应用启动时自动扫描最近的存档
        self._scan_latest_archive()

    def setup_ui(self):
        # 1. 模式
        mode_frame = ttk.LabelFrame(self, text="任务模式")
        mode_frame.pack(fill="x", pady=5)
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
        self.grp_files.pack(fill="x", pady=5)

        self.lbl_in = ttk.Label(self.grp_files, text="源文件:")
        self.ent_in = ttk.Entry(self.grp_files, width=50)
        self.btn_in = ttk.Button(
            self.grp_files, text="...", width=4,
            command=lambda: self._sel_file(self.ent_in, [("Data", "*.csv *.json *.pdf")])
        )

        # 自动推导存档
        self.ent_in_var = tk.StringVar()
        self.ent_in.config(textvariable=self.ent_in_var)
        try:
            self.ent_in_var.trace_add("write", self._auto_set_archive_path)
        except Exception:
            self.ent_in_var.trace("w", self._auto_set_archive_path)

        self.lbl_out = ttk.Label(self.grp_files, text="存档路径:")
        self.ent_out = ttk.Entry(self.grp_files, width=50, textvariable=self.arc_var)
        self.btn_out = ttk.Button(self.grp_files, text="...", width=4)

        # 存档变化时：判断是否已完成从而显示/隐藏导出区
        try:
            self.arc_var.trace_add("write", self._on_archive_change)
        except Exception:
            self.arc_var.trace("w", self._on_archive_change)

        self.lbl_term = ttk.Label(self.grp_files, text="术语表:")
        self.ent_term = ttk.Entry(self.grp_files, width=50)
        self.btn_term = ttk.Button(
            self.grp_files, text="...", width=4,
            command=lambda: self._sel_file(self.ent_term, [("Terms", "*.csv *.json")])
        )

        self.grp_files.columnconfigure(1, weight=1)

        # 3. 导出按钮区（默认隐藏，任务完成后才显示）
        self.export_actions_fr = ttk.LabelFrame(self, text="导出（任务完成后可用）")
        self.btn_export_para_json = ttk.Button(self.export_actions_fr, text="导出Paratranz JSON", command=self.export_para_json)
        self.btn_export_para_csv = ttk.Button(self.export_actions_fr, text="导出Paratranz CSV", command=self.export_para_csv)
        self.btn_export_md = ttk.Button(self.export_actions_fr, text="导出报告MD", command=self.export_report_md)
        self.btn_export_state = ttk.Button(self.export_actions_fr, text="导出内部状态JSON", command=self.export_state_json)
        self.btn_export_new_terms = ttk.Button(self.export_actions_fr, text="导出新术语", command=self.export_new_terms)
        self.btn_export_para_json.pack(side="left", padx=5, pady=8)
        self.btn_export_para_csv.pack(side="left", padx=5, pady=8)
        self.btn_export_md.pack(side="left", padx=5, pady=8)
        self.btn_export_state.pack(side="left", padx=5, pady=8)
        self.btn_export_new_terms.pack(side="left", padx=5, pady=8)

        # 4. 控制
        btn_fr = ttk.Frame(self, padding=(0, 10))
        btn_fr.pack(fill="x")
        self.btn_start = ttk.Button(btn_fr, text="开始校对", command=self.start)
        self.btn_start.pack(side="left", padx=5)
        self.btn_stop = ttk.Button(btn_fr, text="停止", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        
        # 5. 进度显示
        self.progress_var = tk.StringVar(value="")
        progress_fr = ttk.LabelFrame(self, text="校对进度")
        progress_fr.pack(fill="x", pady=5)
        ttk.Label(progress_fr, textvariable=self.progress_var).pack(padx=10, pady=5, anchor="w")

        # 5. 日志（存起来，后面 pack(export) 需要 before=self.log_fr）
        self.log_fr = ttk.LabelFrame(self, text="日志")
        self.log_fr.pack(fill="both", expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(self.log_fr, state="disabled", height=15)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        setup_gui_logger(self.log_text)

        # 初始化布局
        self._on_mode_change()
        self._set_export_visible(False)

    # ---------------- 显示/隐藏导出区 ----------------

    def _set_export_visible(self, show: bool):
        try:
            self.export_actions_fr.pack_forget()
        except Exception:
            pass

        if show:
            # 显示在日志区之前
            self.export_actions_fr.pack(fill="x", pady=5, before=self.log_fr)

    def _on_mode_change(self):
        mode = self.mode_var.get()
        for w in self.grp_files.winfo_children():
            w.grid_forget()

        # 切模式先隐藏导出区
        self._run_completed = False
        self._set_export_visible(False)

        if mode == "new":
            self.lbl_in.grid(row=0, column=0, padx=5, pady=5, sticky="w")
            self.ent_in.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
            self.btn_in.grid(row=0, column=2, padx=5, pady=5)

            self.lbl_out.config(text="生成存档:")
            self.lbl_out.grid(row=1, column=0, padx=5, pady=5, sticky="w")
            self.ent_out.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
            self.btn_out.config(
                command=lambda: self._sel_file(
                    self.ent_out, [("JSON", "*.json")],
                    save=True, init_dir=DEFAULT_DIR_NAME
                )
            )
            self.btn_out.grid(row=1, column=2, padx=5, pady=5)

            self.lbl_term.grid(row=2, column=0, padx=5, pady=5, sticky="w")
            self.ent_term.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
            self.btn_term.grid(row=2, column=2, padx=5, pady=5)

        else:  # resume
            self.lbl_out.config(text="选择存档:")
            self.lbl_out.grid(row=0, column=0, padx=5, pady=5, sticky="w")
            self.ent_out.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
            self.btn_out.config(
                command=lambda: self._sel_file(
                    self.ent_out, ["JSON", "*.json"],
                    save=False, init_dir=DEFAULT_DIR_NAME
                )
            )
            self.btn_out.grid(row=0, column=2, padx=5, pady=5)

            # 从存档开始时不需要选择术语，因为术语已经包含在存档中
            # self.lbl_term.grid(row=1, column=0, padx=5, pady=5, sticky="w")
            # self.ent_term.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
            # self.btn_term.grid(row=1, column=2, padx=5, pady=5)

            self._scan_latest_archive()
            self._refresh_export_visibility()

    def _on_archive_change(self, *args):
        self._refresh_export_visibility()

    def _auto_set_archive_path(self, *args):
        if self.mode_var.get() != "new":
            return
        src = self.ent_in.get().strip()
        if not src:
            return
        base = os.path.splitext(os.path.basename(src))[0]
        # 确保 archives 目录存在
        if not os.path.exists(DEFAULT_DIR_NAME):
            os.makedirs(DEFAULT_DIR_NAME)
        # 使用相对路径，确保用户在选择文件夹时能看到存档文件
        archive_path = os.path.join(DEFAULT_DIR_NAME, f"{base}.json")
        self.arc_var.set(archive_path)

    def _scan_latest_archive(self):
        pat = os.path.join(DEFAULT_DIR_NAME, "*.json")
        cands = glob.glob(pat)
        if not cands:
            return
        valid = [f for f in cands if "_final.json" not in f and "_new_terms.json" not in f]
        if not valid:
            return
        latest = max(valid, key=os.path.getmtime)
        # 使用相对路径，确保用户在选择文件夹时能看到存档文件
        relative_path = os.path.relpath(latest, os.getcwd())
        self.arc_var.set(relative_path)
        logger.info(f"[Auto] Loaded latest archive: {latest}")

    def _sel_file(self, entry, types, save=False, init_dir=None):
        kw = {"filetypes": types}
        if init_dir and os.path.exists(init_dir):
            kw["initialdir"] = init_dir

        default_ext = ""
        if save and types:
            # 若 filetypes 只有一个明确后缀（例如 "*.json"），则补齐后缀
            pat = str(types[0][1]).strip()
            if pat.startswith("*.") and " " not in pat:
                default_ext = pat[1:]  # ".json"
                kw["defaultextension"] = default_ext

        f = filedialog.asksaveasfilename if save else filedialog.askopenfilename
        p = f(**kw)
        if p:
            if save and default_ext and not os.path.splitext(p)[1]:
                p += default_ext
            entry.delete(0, tk.END)
            entry.insert(0, p)

    # ---------------- 导出：保存对话框默认名/默认目录 ----------------

    def _suggest_export(self, kind: str):
        f_arc = self.arc_var.get().strip()
        base = os.path.splitext(os.path.basename(f_arc))[0] if f_arc else "export"

        # 默认目录：优先“上次导出目录”，否则用存档所在目录，否则 archives
        out_dir = self._last_export_dir or \
                  (os.path.dirname(os.path.abspath(f_arc)) if f_arc else "") or \
                  os.path.abspath(DEFAULT_DIR_NAME)

        if kind == "para_json":
            return out_dir, f"{base}_paratranz.json", [("JSON", "*.json")], ".json"
        if kind == "para_csv":
            return out_dir, f"{base}_paratranz.csv", [("CSV", "*.csv")], ".csv"
        if kind == "md":
            return out_dir, f"{base}_final.md", [("Markdown", "*.md")], ".md"
        if kind == "state_json":
            return out_dir, f"{base}_state.json", [("JSON", "*.json")], ".json"
        if kind == "new_terms":
            return out_dir, f"{base}_new_terms.json", [("JSON", "*.json")], ".json"
        raise ValueError(f"unknown export kind: {kind}")

    def _ask_save_path(self, kind: str) -> str | None:
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

        self._last_export_dir = os.path.dirname(p)
        return p

    # ---------------- 任务运行 ----------------

    def start(self):
        mode = self.mode_var.get()
        f_arc = self.arc_var.get().strip()
        f_src = self.ent_in.get().strip()
        f_term = self.ent_term.get().strip()

        if not f_arc:
            return messagebox.showwarning("提示", "未指定存档")
        if mode == "new" and not f_src:
            return messagebox.showwarning("提示", "未指定源文件")

        # 开始跑就隐藏导出区
        self._run_completed = False
        self._set_export_visible(False)

        self.is_running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")

        self.log_text.config(state="normal")
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state="disabled")

        threading.Thread(target=self._bg_run, args=(mode, f_src, f_arc, f_term), daemon=True).start()

    def stop(self):
        self.is_running = False
        messagebox.showinfo("Info", "停止信号已发送")
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")

    def _bg_run(self, mode, f_src, f_arc, f_term):
        workflow = Proofread1Workflow()

        def _done_cb(blocks):
            self._mark_archive_completed(f_arc)
            self.after(0, lambda: messagebox.showinfo("完成", "一校任务结束。可按需导出。"))
            self.after(0, lambda: self._set_export_visible(True))
            self.after(0, lambda: self.btn_start.config(state="normal"))
            self.after(0, lambda: self.progress_var.set(""))
            self.is_running = False
            
        def _err_cb(e):
            self.after(0, lambda: messagebox.showerror("运行失败", str(e)))
            self.after(0, lambda: self.btn_start.config(state="normal"))
            self.after(0, lambda: self.progress_var.set(""))
            self.is_running = False
        
        def _progress_cb(completed, total):
            self.after(0, lambda: self.progress_var.set(f"校对进度: {completed}/{total}"))

        is_pdf = (mode == "new" and f_src.lower().endswith(".pdf"))
        file_path = f_src if mode == "new" else f_arc
        
        # 从存档开始时不需要传递术语文件路径，因为术语已经包含在存档中
        old_terms_path = f_term if mode == "new" else ""
        new_terms_path = "" if mode == "new" else ""
        
        workflow.execute_async(
            file_path=file_path,
            out_path=f_arc,
            is_pdf=is_pdf,
            old_terms_path=old_terms_path,
            new_terms_path=new_terms_path,
            progress_callback=_progress_cb,
            done_callback=_done_cb,
            error_callback=_err_cb
        )

    # ---------------- 完成标记 / 可见性 ----------------

    def _archive_is_completed(self, f_arc: str) -> bool:
        try:
            with open(f_arc, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                return False
            rs = data.get("run_status")
            if isinstance(rs, dict) and rs.get("alignment_completed") is True:
                return True
            if data.get("alignment_completed") is True:
                return True
            if data.get("completed") is True:
                return True
        except Exception:
            return False
        return False

    def _mark_archive_completed(self, f_arc: str):
        try:
            with open(f_arc, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                return
            rs = data.get("run_status")
            if not isinstance(rs, dict):
                rs = {}
                data["run_status"] = rs
            rs["alignment_completed"] = True
            rs["completed_at"] = datetime.now().isoformat(timespec="seconds")

            with open(f_arc, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        except Exception:
            # 不阻断主流程
            pass

    def _refresh_export_visibility(self):
        f_arc = self.arc_var.get().strip()
        if self.is_running or (not f_arc) or (not os.path.exists(f_arc)):
            self._set_export_visible(False)
            return
        completed = self._archive_is_completed(f_arc)
        self._run_completed = bool(completed)
        self._set_export_visible(self._run_completed)

    def _ensure_can_export(self) -> str | None:
        if self.is_running:
            return "任务仍在运行中，禁止导出。"
        f_arc = self.arc_var.get().strip()
        if not f_arc:
            return "未选择存档。"
        if not os.path.exists(f_arc):
            return "存档文件不存在。"
        if not self._archive_is_completed(f_arc) and not self._run_completed:
            return "当前存档未标记为已完成，请先完成校对任务再导出。"
        return None

    # ---------------- 三个单独导出按钮（点击弹出另存为） ----------------

    def export_para_json(self):
        err = self._ensure_can_export()
        if err:
            return messagebox.showwarning("提示", err)

        f_arc = self.arc_var.get().strip()
        out_final = self._ask_save_path("para_json")
        if not out_final:
            return

        try:
            blocks, _, _ = FormatConverter.load_from_json(f_arc)
            paratranz_data = []
            for b in blocks:
                translation = b.proofread_zh or b.proofread1_zh or b.zh_block or ""
                paratranz_data.append({
                    "key": b.key,
                    "original": b.en_block,
                    "translation": translation,
                    "stage": b.stage
                })
            with open(out_final, 'w', encoding='utf-8') as f:
                json.dump(paratranz_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"已导出 Paratranz JSON：\n{os.path.basename(out_final)}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_para_csv(self):
        err = self._ensure_can_export()
        if err: return messagebox.showwarning("提示", err)
        f_arc = self.arc_var.get().strip()
        out_csv = self._ask_save_path("para_csv")
        if not out_csv: return
        try:
            blocks, _, _ = FormatConverter.load_from_json(f_arc)
            import csv
            with open(out_csv, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                # 直接写入数据，不添加注释行
                for b in blocks:
                    translation = b.proofread_zh or b.proofread1_zh or b.zh_block or ""
                    writer.writerow([b.key, b.en_block, translation])
            messagebox.showinfo("成功", f"已导出 Paratranz CSV：\n{os.path.basename(out_csv)}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_report_md(self):
        err = self._ensure_can_export()
        if err:
            return messagebox.showwarning("提示", err)

        f_arc = self.arc_var.get().strip()
        out_md = self._ask_save_path("md")
        if not out_md:
            return

        try:
            blocks, _, _ = FormatConverter.load_from_json(f_arc)
            FormatConverter.export_to_markdown(blocks, out_md)
            messagebox.showinfo("成功", f"已导出：\n{os.path.basename(out_md)}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_state_json(self):
        err = self._ensure_can_export()
        if err:
            return messagebox.showwarning("提示", err)

        f_arc = self.arc_var.get().strip()
        out_state = self._ask_save_path("state_json")
        if not out_state:
            return

        try:
            blocks, _, _ = FormatConverter.load_from_json(f_arc)
            # 构建简洁的导出格式
            simple_data = []
            for block in blocks:
                simple_data.append({
                    "key": block.key,
                    "en_block": block.en_block,
                    "zh_block": block.zh_block,
                    "proofread1_zh": block.proofread1_zh,
                    "proofread1_note": block.proofread1_note
                })
            # 直接写入简洁格式
            with open(out_state, 'w', encoding='utf-8') as f:
                json.dump(simple_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"已导出内部状态 JSON：\n{os.path.basename(out_state)}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_new_terms(self):
        err = self._ensure_can_export()
        if err:
            return messagebox.showwarning("提示", err)

        f_arc = self.arc_var.get().strip()
        out_terms = self._ask_save_path("new_terms")
        if not out_terms:
            return

        try:
            # 加载存档数据
            with open(f_arc, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取新术语
            new_terms = []
            if isinstance(data, dict):
                terms = data.get("terms", {})
                new_terms = terms.get("new_terms", [])
            
            # 去重
            seen_terms = set()
            unique_terms = []
            for term in new_terms:
                term_str = term.get("term", "").strip()
                if term_str and term_str not in seen_terms:
                    seen_terms.add(term_str)
                    unique_terms.append(term)
            
            with open(out_terms, 'w', encoding='utf-8') as f:
                json.dump(unique_terms, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", f"已导出新术语：\n{os.path.basename(out_terms)}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
