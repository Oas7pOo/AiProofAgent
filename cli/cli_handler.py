from pathlib import Path

from core.format_converter import FormatConverter
from workflows.proofread1_flow import Proofread1Workflow
from workflows.proofread2_flow import Proofread2Workflow


def run_cli_task(args) -> None:
    errors = []

    if args.in_pdf:
        source_path = Path(args.in_pdf)
        output_path = Path(args.out_json) if args.out_json else (
            source_path.with_name(f"{source_path.stem}_state.json")
        )

        workflow = Proofread1Workflow(args.config)
        worker = workflow.execute_async(
            file_path=str(source_path),
            out_path=str(output_path),
            is_pdf=True,
            error_callback=errors.append,
        )
        worker.join()

        if errors:
            raise errors[0]

    if args.in_json and args.run_proof2:
        source_path = Path(args.in_json)
        output_path = Path(args.out_json) if args.out_json else (
            source_path.with_name(f"{source_path.stem}_proof2.json")
        )

        workflow = Proofread2Workflow(args.config)
        workflow.init_session(
            archive_path=str(output_path),
            stage1_path=str(source_path),
        )
        worker = workflow.run_bulk_async(error_callback=errors.append)
        worker.join()

        if errors:
            raise errors[0]

    if args.export_md and args.in_json:
        blocks, _, _ = FormatConverter.load_from_json(args.in_json)
        FormatConverter.export_to_markdown(blocks, args.export_md)
