from dataclasses import dataclass

@dataclass
class TermEntry:
    term: str
    translation: str
    note: str = ""