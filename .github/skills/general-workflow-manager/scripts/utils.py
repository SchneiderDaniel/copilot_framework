import json
import os

def load_config():
    """
    Loads project configuration from .github/context/project_config.json.
    """
    root_dir = os.getcwd()
    config_path = os.path.join(root_dir, ".github", "context", "project_config.json")
    
    # Default values
    default_config = {
        "repo": "SchneiderDaniel/copilot_framework",
        "myosotis_project": "copilot_framework",
        "github_project_number": 2
    }
    
    if not os.path.exists(config_path):
        return default_config
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Warning: Could not load project_config.json: {e}")
        return default_config
