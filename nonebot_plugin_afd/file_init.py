from .config import config_file, user_relation_file

if not config_file.exists():
    _ = config_file.write_text("{}", encoding="utf-8")

if not user_relation_file.exists():
    _ = user_relation_file.write_text("{}", encoding="utf-8")
