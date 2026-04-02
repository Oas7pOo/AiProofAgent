import tkinter as tk
from tkinter import ttk, messagebox
from utils.config_loader import load_config, save_config

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
        add_row(grp_api, "Base URL:", "base_url", 0)
        add_row(grp_api, "API Key:", "api_key", 1)
        add_row(grp_api, "Model Name:", "model", 2)

        grp_run = ttk.LabelFrame(self, text="运行参数")
        grp_run.pack(fill='x', pady=10)
        add_row(grp_run, "最大并发:", "ai_max_workers", 0)
        add_row(grp_run, "每批数量:", "max_blocks", 1)
        add_row(grp_run, "单批最大字数:", "max_chars", 2)
        add_row(grp_run, "重试等待(秒):", "time_wait", 3)
        add_row(grp_run, "超时时间(秒):", "timeout", 4)

        grp_ocr = ttk.LabelFrame(self, text="OCR 设置")
        grp_ocr.pack(fill='x', pady=10)
        add_row(grp_ocr, "Paddle URL:", "ocr_api_url", 0)
        add_row(grp_ocr, "Paddle Token:", "ocr_token", 1)

        ttk.Button(self, text="保存配置", command=self.save).pack(pady=20)

    def refresh(self):
        cfg = load_config()
        for key, var in self.vars.items():
            val = ""
            if key == "ocr_api_url": val = cfg.get("ocr", {}).get("api_url", "")
            elif key == "ocr_token": val = cfg.get("ocr", {}).get("token", "")
            else: val = cfg.get(key, "")
            var.set(str(val))

    def save(self):
        try:
            current = load_config()
            if "ocr" not in current: current["ocr"] = {}
            for key, var in self.vars.items():
                val = var.get().strip()
                if key in ['ai_max_workers', 'max_blocks', 'max_chars', 'time_wait', 'timeout']:
                    if val.isdigit(): val = int(val)
                if key == "ocr_api_url": current["ocr"]["api_url"] = val
                elif key == "ocr_token": current["ocr"]["token"] = val
                else: current[key] = val
            save_config(current)
            messagebox.showinfo("Success", "Configuration saved.")
            self.refresh()
        except Exception as e: messagebox.showerror("Error", str(e))