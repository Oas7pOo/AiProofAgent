# main.py
import sys
import argparse

def main():
    # 简单检查：如果有 --gui 参数，或者没有任何参数，就尝试启动 GUI
    # 否则进入 CLI 模式
    
    # 这里我们做一个简单的预判断，不使用 heavy argparse
    use_gui = "--gui" in sys.argv
    
    if use_gui:
        print("[INFO] Launching GUI...")
        try:
            # 懒加载：只有需要 GUI 时才导入 tkinter 依赖
            from ui.gui_app import ProofreadGUI
            app = ProofreadGUI()
            app.mainloop()
        except ImportError as e:
            print(f"[ERROR] GUI Import Failed: {e}")
            print("Ensure 'ui' folder exists and dependencies are installed.")
        except Exception as e:
            print(f"[CRITICAL] GUI Crash: {e}")
    else:
        # CLI 模式
        # 懒加载：CLI 逻辑
        from cli.cli_handler import run_cli_task
        run_cli_task()

if __name__ == "__main__":
    main()