import argparse
import os
from workflows.proofread1_flow import Proofread1Workflow
from workflows.proofread2_flow import Proofread2Workflow
from core.format_converter import FormatConverter
from utils.config import ConfigManager
import logging

logger = logging.getLogger("AiProofAgent.CLI")

def parse_args():
    p = argparse.ArgumentParser(description="AiProofAgent CLI")
    p.add_argument("--in-pdf", help="Input PDF path (OCR)")
    p.add_argument("--in-json", help="Input JSON state path (Resume/Stage2)")
    p.add_argument("--config", default="config.yaml", help="Config path")
    p.add_argument("--run-proof2", action="store_true", help="Perform second proofread")
    p.add_argument("--export-md", help="Export to Markdown path")
    return p.parse_args()

def run_cli_task(config_path="config.yaml"):
    args = parse_args()
    cfg = ConfigManager(config_path)

    logger.info("启动命令行模式 (简化版)...")
    if args.in_pdf:
        logger.info("执行一校任务...")
        out_path = args.in_pdf.replace('.pdf', '_state.json')
        Proofread1Workflow(config_path).execute_async(file_path=args.in_pdf, out_path=out_path, is_pdf=True)
        
    if args.in_json and args.run_proof2:
        logger.info("执行二校任务...")
        Proofread2Workflow(config_path).execute_async(file_path=args.in_json)

    if args.export_md and args.in_json:
        blocks, _, _ = FormatConverter.load_from_json(args.in_json)
        FormatConverter.export_to_markdown(blocks, args.export_md)
