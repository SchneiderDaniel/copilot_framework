import os
import sys
import argparse
import subprocess

# Import the configuration
try:
    from utils import load_config
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from utils import load_config

CONFIG = load_config()

def run_command(command, env=None):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, env=env)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e.stderr}")
        return None

def save_checkpoint(issue_number, persona, text):
    print(f"💾 Saving checkpoint for {persona} (Issue #{issue_number})...")
    
    root_dir = os.getcwd()
    myosotis_dir = os.path.join(root_dir, "flask_blogs", "myosotis")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = myosotis_dir + os.pathsep + env.get("PYTHONPATH", "")

    result = run_command([
        sys.executable, "-m", "myosotis.cli.main", "add",
        text,
        "--project", CONFIG["myosotis_project"],
        "--role", persona.lower(),
        "--namespace", "checkpoints"
    ], env=env)
    
    if result:
        print(f"✅ Checkpoint saved to Myosotis.")
        return True
    return False

def load_checkpoint(issue_number, persona):
    print(f"📂 Loading latest checkpoint for {persona} (Issue #{issue_number})...")
    
    root_dir = os.getcwd()
    myosotis_dir = os.path.join(root_dir, "flask_blogs", "myosotis")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = myosotis_dir + os.pathsep + env.get("PYTHONPATH", "")

    # Search for the latest checkpoint
    query = f"Latest checkpoint for issue {issue_number} role {persona}"
    result = run_command([
        sys.executable, "-m", "myosotis.cli.main", "search",
        query,
        "--project", CONFIG["myosotis_project"],
        "--role", persona.lower(),
        "--limit", "1"
    ], env=env)
    
    if result:
        print("\n--- LATEST CHECKPOINT ---")
        print(result)
        print("-" * 25 + "\n")
        return True
    else:
        print("ℹ️ No checkpoint found.")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save or load agent checkpoints for context compaction.")
    parser.add_argument("action", choices=["save", "load"], help="Action to perform.")
    parser.add_argument("issue_number", type=int, help="The issue number.")
    parser.add_argument("persona", type=str, help="The agent persona.")
    parser.add_argument("--text", type=str, help="Checkpoint content (only for 'save').")
    parser.add_argument("--file", type=str, help="File containing checkpoint content (only for 'save').")
    
    args = parser.parse_args()
    
    if args.action == "save":
        content = args.text
        if args.file:
            try:
                with open(args.file, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                print(f"❌ Error reading file: {e}")
                sys.exit(1)
        
        if not content:
            print("❌ Error: No content provided for checkpoint.")
            sys.exit(1)
            
        if save_checkpoint(args.issue_number, args.persona, content):
            sys.exit(0)
    else:
        if load_checkpoint(args.issue_number, args.persona):
            sys.exit(0)
    
    sys.exit(1)
