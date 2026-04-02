import argparse
from utils.config import ConfigManager
from utils.logger import setup_root_logger
from ui.gui_app import ProofreadGUI
from cli.cli_handler import run_cli_task

def main():
    parser = argparse.ArgumentParser(description="AiProofAgent")
    parser.add_argument("--gui", action="store_true", help="Launch GUI")
    parser.add_argument("--cli", action="store_true", help="Launch CLI")
    parser.add_argument("--config", default="config.yaml", help="Config path")
    args = parser.parse_args()

    setup_root_logger()
    cfg = ConfigManager(args.config)

    if args.cli:
        run_cli_task(config_path=args.config)
    else:
        app = ProofreadGUI(config=cfg.data)
        app.mainloop()

if __name__ == "__main__":
    main()

