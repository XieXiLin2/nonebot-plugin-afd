from pathlib import Path

from nonebot import get_plugin_config
import nonebot_plugin_localstore as store
from pydantic import BaseModel, Field


class Config(BaseModel):
    """配置文件"""

    afd_token_dict: dict[int, list[str]] = Field(default_factory=dict)


plugin_config = get_plugin_config(Config)

config_file: Path = store.get_plugin_config_file("group_config.json")
user_relation_file: Path = store.get_plugin_data_file("user_relation.json")
