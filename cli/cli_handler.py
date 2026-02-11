# cli/cli_handler.py
import argparse
import sys
import os
from tools.proofread_service import ProofreadApp
from ai.alignment_service import AlignmentService
from utils.config_loader import load_config # 引用刚才拆出来的

def parse_args():
    """定义命令行参数"""
    parser = argparse.ArgumentParser(description="AI Proofread Tool (CLI)")
    parser.add_argument("--archive", help="Project archive name (Required)")
    parser.add_argument("--in-csv", help="Input CSV path")
    parser.add_argument("--in-json", help="Input Source JSON path")
    parser.add_argument("--in-pdf", help="Input PDF path (OCR mode)")
    parser.add_argument("--out-json", help="Output Project JSON path")
    parser.add_argument("--terms", help="Terms CSV/JSON path")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--run-ai", action="store_true", help="Run AI alignment immediately")
    return parser.parse_args()

def run_cli_task():
    """命令行模式的主入口"""
    args = parse_args()

    # 1. 基础校验
    if not args.archive or not args.out_json:
        print("[ERROR] CLI mode requires --archive and --out-json")
        return # 退出函数而不是 sys.exit，更优雅

    # 2. 加载配置
    config = load_config(args.config)
    
    # 3. 初始化 App
    app = ProofreadApp(archive_name=args.archive, config=config, job_count=1)

    # 4. 路由分发
    if os.path.exists(args.out_json):
        print(f"[INFO] Loading archive: {args.out_json}")
        app.load_project_json(args.out_json)
    elif args.in_csv:
        print(f"[INFO] Importing CSV: {args.in_csv}")
        app.import_from_csv(args.in_csv)
    elif args.in_json: 
        print(f"[INFO] Importing JSON: {args.in_json}")
        app.import_from_json(args.in_json) 
    elif args.in_pdf:
        print(f"[INFO] Importing PDF: {args.in_pdf}")
        app.import_from_pdf(args.in_pdf)
    else:
        print(f"[ERROR] No valid input source found!")
        return

    # 5. 加载术语
    if args.terms:
        app.load_terms(args.terms)

    # 6. 运行 AI
    if args.run_ai:
        if not config:
            print("[ERROR] AI requires config.yaml")
            return
        
        try:
            print("Initializing AI service...")
            ai_service = AlignmentService(config)
            max_workers = config.get('ai_max_workers')
            app.run_alignment_batch_threaded(ai_service, args.out_json, max_workers)
        except Exception as e:
            print(f"[FATAL] AI Error: {e}")

    # 7. 保存
    out_dir = os.path.dirname(args.out_json)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)
    app.export_project_json(args.out_json)
    print(f"[SUCCESS] Saved to: {args.out_json}")