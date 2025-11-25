from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class ModificationBlueprint:
    plan_id: str
    target_file: str
    confidence: str
    action_type: str
    location_hint: dict
    reasoning: str
    parent_container_path: Optional[str] = None

    def dict(self):
        return asdict(self)
