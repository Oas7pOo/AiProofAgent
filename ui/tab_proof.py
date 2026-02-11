# tab_run.py
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import sys
import os
import glob
import json
from datetime import datetime

from tools.proofread_service import ProofreadApp
from ai.alignment_service import AlignmentService
from utils.config_loader import load_config
from tools.export_manager import ExportManager

DEFAULT_DIR_NAME = "archives"


class TextRedirector:
    def __init__(self, widget):
        self.widget = widget

    def write(self, s):
        try:
            self.widget.after(0, self._append, s)
        except Exception:
            pass

    def _append(self, s):
        try:
            self.widget.config(state="normal")
            self.widget.insert(tk.END, s)
            self.widget.see(tk.END)
            self.widget.config(state="disabled")
        except Exception:
            pass

    def flush(self):
        pass


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
        self.btn_export_final = ttk.Button(self.export_actions_fr, text="导出最终JSON", command=self.export_final_json)
        self.btn_export_md = ttk.Button(self.export_actions_fr, text="导出报告MD", command=self.export_report_md)
        self.btn_export_terms = ttk.Button(self.export_actions_fr, text="导出新术语JSON", command=self.export_terms_json)
        self.btn_export_final.pack(side="left", padx=5, pady=8)
        self.btn_export_md.pack(side="left", padx=5, pady=8)
        self.btn_export_terms.pack(side="left", padx=5, pady=8)

        # 4. 控制
        btn_fr = ttk.Frame(self, padding=(0, 10))
        btn_fr.pack(fill="x")
        self.btn_start = ttk.Button(btn_fr, text="开始校对", command=self.start)
        self.btn_start.pack(side="left", padx=5)
        self.btn_stop = ttk.Button(btn_fr, text="停止", command=self.stop, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

        # 5. 日志（存起来，后面 pack(export) 需要 before=self.log_fr）
        self.log_fr = ttk.LabelFrame(self, text="日志")
        self.log_fr.pack(fill="both", expand=True, pady=5)
        self.log_text = scrolledtext.ScrolledText(self.log_fr, state="disabled", height=15)
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

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
                    self.ent_out, [("JSON", "*.json")],
                    save=False, init_dir=DEFAULT_DIR_NAME
                )
            )
            self.btn_out.grid(row=0, column=2, padx=5, pady=5)

            self.lbl_term.grid(row=1, column=0, padx=5, pady=5, sticky="w")
            self.ent_term.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
            self.btn_term.grid(row=1, column=2, padx=5, pady=5)

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
        self.arc_var.set(os.path.abspath(os.path.join(DEFAULT_DIR_NAME, f"{base}.json")))

    def _scan_latest_archive(self):
        pat = os.path.join(DEFAULT_DIR_NAME, "*.json")
        cands = glob.glob(pat)
        if not cands:
            return
        valid = [f for f in cands if "_final.json" not in f and "_new_terms.json" not in f]
        if not valid:
            return
        latest = max(valid, key=os.path.getmtime)
        self.arc_var.set(os.path.abspath(latest))
        print(f"[Auto] Loaded latest: {latest}")

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

        if kind == "final":
            return out_dir, f"{base}_final.json", [("JSON", "*.json")], ".json"
        if kind == "md":
            return out_dir, f"{base}_final.md", [("Markdown", "*.md")], ".md"
        if kind == "terms":
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
        old_out = sys.stdout
        sys.stdout = TextRedirector(self.log_text)
        try:
            print("=== 开始任务 ===")
            cfg = load_config()
            os.makedirs(os.path.dirname(os.path.abspath(f_arc)), exist_ok=True)

            name = os.path.basename(f_arc).split(".")[0]
            app = ProofreadApp(name, config=cfg)

            if mode == "resume":
                if not os.path.exists(f_arc):
                    print(f"[ERROR] 存档不存在: {f_arc}")
                    return
                app.load_project_json(f_arc)
            else:
                print(f"[INFO] 导入数据: {f_src}")
                if f_src.lower().endswith(".csv"):
                    app.import_from_csv(f_src)
                elif f_src.lower().endswith(".json"):
                    app.import_from_json(f_src)
                elif f_src.lower().endswith(".pdf"):
                    app.import_from_pdf(f_src)
                if os.path.exists(f_arc):
                    print(f"[WARN] 覆盖存档: {f_arc}")

            if f_term:
                app.load_terms(f_term)

            srv = AlignmentService(cfg)
            w = cfg.get("ai_max_workers")

            # 注意：必须等真正完成后才返回，否则会过早解锁导出
            app.run_alignment_batch_threaded(srv, f_arc, w)

            # 写“已完成标记”，用于 resume 时自动显示导出区
            self._mark_archive_completed(f_arc)

            print("[INFO] 任务完成")

            def _ui_done():
                self._run_completed = True
                self._set_export_visible(True)
                messagebox.showinfo("完成", "任务结束。已显示三个导出按钮，可按需导出。")

            self.after(0, _ui_done)

        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            self.after(0, lambda: messagebox.showerror("运行失败", str(e)))
        finally:
            sys.stdout = old_out
            self.after(0, lambda: self.btn_start.config(state="normal"))
            self.after(0, lambda: self.btn_stop.config(state="disabled"))
            self.is_running = False

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

    def export_final_json(self):
        err = self._ensure_can_export()
        if err:
            return messagebox.showwarning("提示", err)

        f_arc = self.arc_var.get().strip()
        out_final = self._ask_save_path("final")
        if not out_final:
            return

        try:
            exporter = ExportManager(
                f_arc,
                out_final_json=out_final,
                out_md=None,
                out_terms_json=None,
                default_dir=DEFAULT_DIR_NAME,
            )
            files = exporter.export_all(export_final=True, export_md=False, export_terms=False)
            messagebox.showinfo("成功", "已导出：\n" + "\n".join([os.path.basename(f) for f in files]))
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
            exporter = ExportManager(
                f_arc,
                out_final_json=None,
                out_md=out_md,
                out_terms_json=None,
                default_dir=DEFAULT_DIR_NAME,
            )
            files = exporter.export_all(export_final=False, export_md=True, export_terms=False)
            messagebox.showinfo("成功", "已导出：\n" + "\n".join([os.path.basename(f) for f in files]))
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def export_terms_json(self):
        err = self._ensure_can_export()
        if err:
            return messagebox.showwarning("提示", err)

        f_arc = self.arc_var.get().strip()
        out_terms = self._ask_save_path("terms")
        if not out_terms:
            return

        try:
            exporter = ExportManager(
                f_arc,
                out_final_json=None,
                out_md=None,
                out_terms_json=out_terms,
                default_dir=DEFAULT_DIR_NAME,
            )
            files = exporter.export_all(export_final=False, export_md=False, export_terms=True)
            messagebox.showinfo("成功", "已导出：\n" + "\n".join([os.path.basename(f) for f in files]))
        except Exception as e:
            messagebox.showerror("导出失败", str(e))
