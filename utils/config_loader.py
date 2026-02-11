import os
import yaml

def load_config(config_path="config.yaml"):
    """
    只负责老实读取 config.yaml，绝不自作聪明添加默认值。
    """
    target_path = config_path
    
    # 兼容性查找
    if not os.path.exists(target_path):
        if os.path.exists(os.path.join("study_py", config_path)):
            target_path = os.path.join("study_py", config_path)
        else:
            # 如果文件不存在，就返回空，UI 上会显示为空，由用户自己填
            return {}

    try:
        with open(target_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"[WARN] Config load failed: {e}")
        return {}

def save_config(config_data, config_path="config.yaml"):
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)
    except Exception as e:
        print(f"[ERROR] Save config failed: {e}")
        raise e