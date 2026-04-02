from dataclasses import dataclass, field
from typing import List
from models.document import TranslationBlock

@dataclass
class ProjectInfo:
    archive_name: str = ""
    job_count: int = 0
    blocks: List[TranslationBlock] = field(default_factory=list)