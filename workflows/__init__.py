"""工作流模块"""

from .base_runner import BatchTaskRunner, WorkflowError
from .proofread1_flow import Proofread1Workflow
from .proofread2_flow import Proofread2Workflow

__all__ = [
    'BatchTaskRunner',
    'WorkflowError',
    'Proofread1Workflow',
    'Proofread2Workflow'
]