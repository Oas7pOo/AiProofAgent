# main.py
import sys
import argparse
import os

def main():
    # 简单检查：如果有 --gui 参数，或者没有任何参数，就尝试启动 GUI
    # 否则进入 CLI 模式
    
    # 这里我们做一个简单的预判断，不使用 heavy argparse
    use_gui = "--gui" in sys.argv
    
    # 添加当前文件所在目录的父目录到 sys.path，确保能正确导入模块
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    sys.path.insert(0, parent_dir)
    
    if use_gui:
        print("[INFO] Launching GUI...")
        try:
            # 懒加载：只有需要 GUI 时才导入 tkinter 依赖
            from AiProofAgent.ui.gui_app import ProofreadGUI
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
        from AiProofAgent.cli.cli_handler import run_cli_task
        run_cli_task()

if __name__ == "__main__":
    main()