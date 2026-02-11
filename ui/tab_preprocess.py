import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import os
import sys

# 引入业务逻辑
from tools.data_converter import DataConverter
from utils.config_loader import load_config

# === 工具类：重定向输出 ===
class TextRedirector:
    def __init__(self, widget):
        self.widget = widget
    
    def write(self, str_val):
        try:
            self.widget.after(0, self._append_text, str_val)
        except:
            pass

    def _append_text(self, str_val):
        try:
            self.widget.configure(state='normal')
            self.widget.insert(tk.END, str_val)
            self.widget.see(tk.END)
            self.widget.configure(state='disabled')
        except:
            pass
            
    def flush(self):
        pass

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
        self.conv_dir_var = tk.StringVar(value="csv2json")
        
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
        
        ttk.Radiobutton(mode_frame, text="PDF 提取模式 (PDF -> Output)", variable=self.mode_var, value="pdf", command=self._on_mode_change).pack(side='left', padx=20, pady=10)
        ttk.Radiobutton(mode_frame, text="格式转换模式 (CSV <-> JSON)", variable=self.mode_var, value="convert", command=self._on_mode_change).pack(side='left', padx=20, pady=10)

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

    def _init_pdf_ui(self):
        """初始化 PDF 模式界面"""
        frame = ttk.LabelFrame(self.container_pdf, text="PDF 提取设置")
        frame.pack(fill='x', expand=True)

        self.pdf_in = self._create_file_row(frame, "输入文件 (PDF):", 0, [("PDF Files", "*.pdf")])
        self.pdf_in.trace("w", self._auto_fill_pdf_output)

        ttk.Label(frame, text="输出格式:").grid(row=1, column=0, sticky='w', padx=10, pady=10)
        fmt_frame = ttk.Frame(frame)
        fmt_frame.grid(row=1, column=1, sticky='w')
        ttk.Radiobutton(fmt_frame, text="JSON", variable=self.pdf_fmt_var, value="json").pack(side='left', padx=5)
        ttk.Radiobutton(fmt_frame, text="CSV", variable=self.pdf_fmt_var, value="csv").pack(side='left', padx=5)
        
        self.pdf_out = self._create_file_row(frame, "输出路径:", 2, [("JSON", "*.json"), ("CSV", "*.csv")], is_save=True)

        self.btn_run_pdf = ttk.Button(frame, text="▶ 开始处理 (PDF -> Output)", command=self.run_pdf_task)
        self.btn_run_pdf.grid(row=3, column=1, pady=20, sticky='w')

    def _init_conv_ui(self):
        """初始化 转换 模式界面"""
        frame = ttk.LabelFrame(self.container_conv, text="格式转换设置")
        frame.pack(fill='x', expand=True)

        ttk.Label(frame, text="转换方向:").grid(row=0, column=0, sticky='w', padx=10, pady=10)
        dir_frame = ttk.Frame(frame)
        dir_frame.grid(row=0, column=1, sticky='w')
        self.rb_c2j = ttk.Radiobutton(dir_frame, text="CSV 转 JSON", variable=self.conv_dir_var, value="csv2json")
        self.rb_c2j.pack(side='left', padx=5)
        self.rb_j2c = ttk.Radiobutton(dir_frame, text="JSON 转 CSV", variable=self.conv_dir_var, value="json2csv")
        self.rb_j2c.pack(side='left', padx=5)

        self.conv_in = self._create_file_row(frame, "输入文件:", 1, [("Data Files", "*.csv *.json")])
        self.conv_in.trace("w", self._auto_fill_conv_output)

        self.conv_out = self._create_file_row(frame, "输出文件:", 2, [("Data Files", "*.csv *.json")], is_save=True)

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
        in_path = self.conv_in.get()
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
            self.conv_out.set(base_path + target_ext)

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

        cfg = load_config()
        
        def _task():
            # 劫持标准输出
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_text)
            
            try:
                print(f"=== 开始 PDF 任务 ===")
                print(f"输入: {p_in}")
                print(f"正在初始化 OCR 引擎...")
                
                converter = DataConverter(cfg)
                count = converter.pdf_to_file(p_in, p_out, fmt)
                
                print(f"=== 任务完成 ===")
                print(f"共提取: {count} 条数据")
                print(f"已保存: {p_out}")
                messagebox.showinfo("完成", f"PDF 提取成功！\n共 {count} 条")
                
            except Exception as e:
                print(f"[ERROR] {e}")
                import traceback
                traceback.print_exc()
                messagebox.showerror("错误", f"处理失败:\n{str(e)}")
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._toggle_ui_state(False))
        
        self._toggle_ui_state(True)
        threading.Thread(target=_task, daemon=True).start()

    def run_convert_task(self):
        f_in = self.conv_in.get().strip()
        f_out = self.conv_out.get().strip()
        direction = self.conv_dir_var.get()

        if not f_in or not f_out:
            messagebox.showwarning("提示", "请完整选择输入和输出路径")
            return

        target_ext = ".json" if direction == "csv2json" else ".csv"
        if not f_out.lower().endswith(target_ext):
            f_out += target_ext
            self.conv_out.set(f_out)

        def _task():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_text)
            
            try:
                print(f"=== 开始格式转换 ===")
                print(f"输入: {f_in}")
                
                converter = DataConverter()
                count = 0
                if direction == "csv2json":
                    if not f_in.lower().endswith('.csv'): raise ValueError("输入文件必须是 CSV")
                    count = converter.csv_to_json(f_in, f_out)
                else:
                    if not f_in.lower().endswith('.json'): raise ValueError("输入文件必须是 JSON")
                    count = converter.json_to_csv(f_in, f_out)
                
                print(f"=== 转换完成 ===")
                print(f"处理数据: {count} 条")
                print(f"输出路径: {f_out}")
                messagebox.showinfo("完成", f"转换成功！\n处理: {count} 条")
                
            except Exception as e:
                print(f"[ERROR] {e}")
                messagebox.showerror("错误", f"转换失败:\n{str(e)}")
            finally:
                sys.stdout = old_stdout
                self.after(0, lambda: self._toggle_ui_state(False))

        self._toggle_ui_state(True)
        threading.Thread(target=_task, daemon=True).start()
