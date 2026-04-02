import tkinter as tk
from tkinter import ttk, messagebox
from utils.config import ConfigManager

class SettingsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True, padx=20, pady=20)
        self.vars = {}
        self.setup_ui()
        self.refresh()

    def setup_ui(self):
        def add_row(parent, label, key, row):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=5)
            var = tk.StringVar()
            ttk.Entry(parent, textvariable=var, width=40).grid(row=row, column=1, sticky='w', padx=10)
            self.vars[key] = var

        grp_api = ttk.LabelFrame(self, text="LLM API")
        grp_api.pack(fill='x', pady=10)
        add_row(grp_api, "Base URL:", "llm.base_url", 0)
        add_row(grp_api, "API Key:", "llm.api_key", 1)
        add_row(grp_api, "Model Name:", "llm.model", 2)

        grp_run = ttk.LabelFrame(self, text="运行参数")
        grp_run.pack(fill='x', pady=10)
        add_row(grp_run, "最大并发:", "llm.ai_max_workers", 0) # 将LLM并发移到LLM配置下
        add_row(grp_run, "每批数量:", "llm.max_blocks", 1)   # 将LLM批次数量移到LLM配置下
        add_row(grp_run, "单批最大字数:", "llm.max_chars", 2) # 将LLM单批最大字数移到LLM配置下
        add_row(grp_run, "重试等待(秒):", "llm.time_wait", 3) # 将LLM重试等待移到LLM配置下
        add_row(grp_run, "超时时间(秒):", "llm.timeout", 4)  # 将LLM超时时间移到LLM配置下

        grp_ocr = ttk.LabelFrame(self, text="OCR 设置")
        grp_ocr.pack(fill='x', pady=10)
        add_row(grp_ocr, "Paddle URL:", "ocr.api_url", 0)
        add_row(grp_ocr, "Paddle Token:", "ocr.token", 1)

        ttk.Button(self, text="保存配置", command=self.save).pack(pady=20)

    def refresh(self):
        cfg_mgr = ConfigManager()
        for key, var in self.vars.items():
            val = cfg_mgr.get(key, "")
            var.set(str(val))

    def save(self):
        try:
            cfg_mgr = ConfigManager()
            # 直接使用ConfigManager的set方法，它会自动处理嵌套路径
            for key, var in self.vars.items():
                val = var.get().strip()
                
                if key in ["llm.ai_max_workers", "llm.max_blocks", "llm.max_chars", "llm.time_wait", "llm.timeout"]:
                    if val.isdigit(): val = int(val)
                
                cfg_mgr.set(key, val)
            cfg_mgr.save()
            messagebox.showinfo("Success", "Configuration saved.")
            self.refresh()
        except Exception as e:
            messagebox.showerror("Error", str(e))