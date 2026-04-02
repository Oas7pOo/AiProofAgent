import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys
import csv
import json

# 引入业务逻辑
from core.ocr_engine import PaddleOCREngine
from core.format_converter import FormatConverter
from utils.config import ConfigManager
from ui.gui_logger import setup_gui_logger
import logging

class PreprocessTab(ttk.Frame):
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
                    exts.add(token[1:])
        return list(exts)[0] if len(exts) == 1 else ""

    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True, padx=15, pady=15)
        
        # === 状态变量 ===
        self.mode_var = tk.StringVar(value="pdf") 
        self.pdf_fmt_var = tk.StringVar(value="json")
        
        # [监听] PDF 输出格式变化 -> 自动更新输出后缀
        self.pdf_fmt_var.trace("w", self._auto_fill_pdf_output)

        self.setup_ui()

    def setup_ui(self):
        # 使用 PanedWindow 或 Frame 分割上下两部分
        # 上部分：设置区域
        # 下部分：日志区域
        
        # === 上部容器 ===
        self.top_frame = ttk.Frame(self)
        self.top_frame.pack(fill='x', expand=False, side='top')

        # 1. 工作模式选择
        mode_frame = ttk.LabelFrame(self.top_frame, text="工作模式")
        mode_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Radiobutton(mode_frame, text="PDF 提取模式 (PDF -> JSON)", variable=self.mode_var, value="pdf", command=self._on_mode_change).pack(side='left', padx=20, pady=10)
        ttk.Radiobutton(mode_frame, text="Paratranz 转换 (CSV <-> JSON)", variable=self.mode_var, value="convert", command=self._on_mode_change).pack(side='left', padx=20, pady=10)

        # 2. 动态内容容器
        self.container_pdf = ttk.Frame(self.top_frame)
        self.container_conv = ttk.Frame(self.top_frame)

        self._init_pdf_ui()
        self._init_conv_ui()
        self._on_mode_change()

        # === 下部容器：日志区域 ===
        log_frame = ttk.LabelFrame(self, text="运行进度日志")
        log_frame.pack(fill='both', expand=True, pady=(10, 0), side='bottom')
        
        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', height=10, font=('Consolas', 9))
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)
        setup_gui_logger(self.log_text)

    def _init_pdf_ui(self):
        """初始化 PDF 模式界面"""
        frame = ttk.LabelFrame(self.container_pdf, text="PDF 提取设置")
        frame.pack(fill='x', expand=True)

        self.pdf_in = self._create_file_row(frame, "输入文件 (PDF):", 0, [("PDF Files", "*.pdf")])
        self.pdf_in.trace("w", self._auto_fill_pdf_output)

        ttk.Label(frame, text="输出格式:").grid(row=1, column=0, sticky='w', padx=10, pady=10)
        fmt_frame = ttk.Frame(frame)
        fmt_frame.grid(row=1, column=1, sticky='w')
        ttk.Radiobutton(fmt_frame, text="Paratranz JSON", variable=self.pdf_fmt_var, value="json").pack(side='left', padx=5)
        ttk.Radiobutton(fmt_frame, text="Paratranz CSV", variable=self.pdf_fmt_var, value="csv").pack(side='left', padx=5)
        
        self.pdf_out = self._create_file_row(frame, "输出路径:", 2, [("Data Files", "*.json *.csv")], is_save=True)

        self.btn_run_pdf = ttk.Button(frame, text="▶ 开始提取 (PDF -> Paratranz)", command=self.run_pdf_task)
        self.btn_run_pdf.grid(row=3, column=1, pady=20, sticky='w')

    def _init_conv_ui(self):
        frame = ttk.LabelFrame(self.container_conv, text="Paratranz 格式转换设置")
        frame.pack(fill='x', expand=True)

        ttk.Label(frame, text="转换方向:").grid(row=0, column=0, sticky='w', padx=10, pady=10)
        dir_frame = ttk.Frame(frame)
        dir_frame.grid(row=0, column=1, sticky='w')
        self.conv_dir_var = tk.StringVar(value="csv2json")
        ttk.Radiobutton(dir_frame, text="CSV 转 JSON", variable=self.conv_dir_var, value="csv2json").pack(side='left', padx=5)
        ttk.Radiobutton(dir_frame, text="JSON 转 CSV", variable=self.conv_dir_var, value="json2csv").pack(side='left', padx=5)

        self.conv_in = self._create_file_row(frame, "输入文件:", 1, [("Data Files", "*.csv *.json")])
        self.conv_in_var = self.conv_in  # 兼容
        self.conv_in_var.trace("w", self._auto_fill_conv_output)

        self.conv_out = self._create_file_row(frame, "输出文件:", 2, [("Data Files", "*.csv *.json")], is_save=True)
        self.conv_out_var = self.conv_out

        self.btn_run_conv = ttk.Button(frame, text="▶ 执行转换", command=self.run_convert_task)
        self.btn_run_conv.grid(row=3, column=1, pady=20, sticky='w')

    # === 自动化逻辑 ===

    def _auto_fill_pdf_output(self, *args):
        in_path = self.pdf_in.get()
        if not in_path: return
        base_path = os.path.splitext(in_path)[0]
        target_ext = "." + self.pdf_fmt_var.get()
        self.pdf_out.set(base_path + target_ext)

    def _auto_fill_conv_output(self, *args):
        in_path = self.conv_in_var.get()
        if not in_path: return
        lower_path = in_path.lower()
        base_path = os.path.splitext(in_path)[0]
        target_ext = ""
        if lower_path.endswith(".csv"):
            self.conv_dir_var.set("csv2json")
            target_ext = ".json"
        elif lower_path.endswith(".json"):
            self.conv_dir_var.set("json2csv")
            target_ext = ".csv"
        if target_ext:
            self.conv_out_var.set(base_path + target_ext)

    def _create_file_row(self, parent, label_text, row, file_types, is_save=False):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky='w', padx=10, pady=5)
        var = tk.StringVar()
        entry = ttk.Entry(parent, textvariable=var, width=50)
        entry.grid(row=row, column=1, sticky='w', padx=5, pady=5)
        def _action():
            if is_save:
                ext = self._unique_ext_from_filetypes(file_types)
                path = filedialog.asksaveasfilename(filetypes=file_types, defaultextension=ext or None)
                path = self._ensure_ext(path, ext)
            else:
                path = filedialog.askopenfilename(filetypes=file_types)
            if path: var.set(path)
        ttk.Button(parent, text="浏览...", width=8, command=_action).grid(row=row, column=2, padx=5, pady=5)
        return var

    def _on_mode_change(self):
        mode = self.mode_var.get()
        if mode == "pdf":
            self.container_conv.pack_forget()
            self.container_pdf.pack(fill='both', expand=True)
        else:
            self.container_pdf.pack_forget()
            self.container_conv.pack(fill='both', expand=True)

    # === [核心修复] 任务执行与日志重定向 ===

    def _toggle_ui_state(self, is_running):
        state = 'disabled' if is_running else 'normal'
        self.btn_run_pdf.config(state=state)
        if hasattr(self, 'btn_run_conv'):
            self.btn_run_conv.config(state=state)
        
        # 运行时清空日志并启用
        if is_running:
            self.log_text.config(state='normal')
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state='disabled')

    def run_pdf_task(self):
        p_in = self.pdf_in.get().strip()
        p_out = self.pdf_out.get().strip()
        fmt = self.pdf_fmt_var.get()

        if not p_in or not p_out:
            messagebox.showwarning("提示", "请完整选择输入和输出路径")
            return
        
        expected_ext = f".{fmt}"
        if not p_out.lower().endswith(expected_ext):
            p_out += expected_ext
            self.pdf_out.set(p_out)

        def _task():
            logger = logging.getLogger("AiProofAgent.Preprocess")
            
            try:
                logger.info("=== 开始 PDF 任务 ===")
                logger.info(f"输入: {p_in}")
                logger.info("正在初始化 OCR 引擎...")
                
                ocr_engine = PaddleOCREngine()
                blocks = ocr_engine.process_pdf(p_in)
                
                if fmt == "json":
                    out_data = [{"key": b.key, "original": b.en_block, "translation": "", "context": ""} for b in blocks]
                    with open(p_out, 'w', encoding='utf-8') as f:
                        json.dump(out_data, f, ensure_ascii=False, indent=2)
                else:
                    with open(p_out, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.writer(f)
                        for b in blocks:
                            writer.writerow([b.key, b.en_block, "", ""])
                
                logger.info("=== 任务完成 ===")
                logger.info(f"共提取: {len(blocks)} 个块")
                logger.info(f"已保存: {p_out}")
                self.after(0, lambda: messagebox.showinfo("完成", f"PDF 提取成功！\n共提取 {len(blocks)} 个块。"))
                
            except Exception as e:
                logger.error(f"处理失败: {e}", exc_info=True)
                self.after(0, lambda: messagebox.showerror("错误", f"处理失败:\n{str(e)}"))
            finally:
                self.after(0, lambda: self._toggle_ui_state(False))
        
        self._toggle_ui_state(True)
        threading.Thread(target=_task, daemon=True).start()

    def run_convert_task(self):
        f_in = self.conv_in_var.get().strip()
        f_out = self.conv_out_var.get().strip()
        direction = self.conv_dir_var.get()

        if not f_in or not f_out:
            return messagebox.showwarning("提示", "请完整选择输入和输出路径")

        def _task():
            logger = logging.getLogger("AiProofAgent.Preprocess")
            try:
                logger.info("=== 开始 Paratranz 格式转换 ===")
                if direction == "csv2json":
                    with open(f_in, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    data_lines = [l for l in lines if not l.startswith('#')]
                    reader = csv.reader(data_lines)
                    out = []
                    for r in reader:
                        if len(r) >= 2:
                            out.append({
                                "key": r[0],
                                "original": r[1],
                                "translation": r[2] if len(r) > 2 else "",
                                "context": r[3] if len(r) > 3 else ""
                            })
                    
                    with open(f_out, 'w', encoding='utf-8') as f:
                        json.dump(out, f, ensure_ascii=False, indent=2)
                    count = len(out)
                else:
                    with open(f_in, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    with open(f_out, 'w', encoding='utf-8', newline='') as f:
                        writer = csv.writer(f)
                        count = 0
                        for item in data:
                            # 兼容内部模型(en_block/proofread_zh)和Paratranz模型(original/translation)
                            key = item.get("key", "")
                            original = item.get("original", item.get("en_block", ""))
                            translation = item.get("translation", item.get("proofread_zh", item.get("proofread1_zh", item.get("zh_block", ""))))
                            context = item.get("context", "")
                            writer.writerow([key, original, translation, context])
                            count += 1
                
                logger.info(f"转换完成，共处理 {count} 条数据，输出至 {f_out}")
                self.after(0, lambda: messagebox.showinfo("完成", f"转换成功！\n处理: {count} 条"))
            except Exception as e:
                logger.error(f"转换失败: {e}", exc_info=True)
                self.after(0, lambda: messagebox.showerror("错误", f"转换失败:\n{str(e)}"))
            finally:
                self.after(0, lambda: self._toggle_ui_state(False))

        self._toggle_ui_state(True)
        threading.Thread(target=_task, daemon=True).start()
