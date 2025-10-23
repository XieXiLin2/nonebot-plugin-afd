from pydantic import BaseModel


class GroupAfdConfig(BaseModel):
    enable_audit: bool = True
    enable_auto_reject: bool = False
    level_required: bool = False
    level_required_value: int = 0
