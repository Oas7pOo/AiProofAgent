import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AiProofAgent")
    parser.add_argument("--cli", action="store_true", help="运行命令行模式")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--in-pdf", help="输入 PDF 路径")
    parser.add_argument("--in-json", help="输入一校状态 JSON 路径")
    parser.add_argument("--out-json", help="输出状态 JSON 路径")
    parser.add_argument("--run-proof2", action="store_true", help="执行二校")
    parser.add_argument("--export-md", help="导出 Markdown 路径")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.cli:
        from cli.cli_handler import run_cli_task
        from utils.logger import setup_root_logger

        setup_root_logger()
        run_cli_task(args)
        return

    from ui.gui_app import ProofreadGUI

    app = ProofreadGUI(config_path=args.config)
    app.mainloop()


if __name__ == "__main__":
    main()
