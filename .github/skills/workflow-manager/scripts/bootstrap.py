import json
import subprocess
import sys
import argparse
import os

# Import the configuration
try:
    from workflow_config import GATES
    from utils import load_config
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from workflow_config import GATES
    from utils import load_config

CONFIG = load_config()

def run_command(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr}")
        return None

def bootstrap_mission(issue_number, persona_name, repo=CONFIG["repo"]):
    """
    Consolidates gate check and context retrieval for agent missions.
    """
    print(f"--- 🚀 Mission Bootstrap for {persona_name} (Issue #{issue_number}) ---")
    
    # 1. Gate Check
    print(f"Checking gate status...")
    issue_json = run_command([
        "gh", "issue", "view", str(issue_number),
        "--repo", repo,
        "--json", "title,body,comments,projectItems"
    ])
    
    if not issue_json:
        print(f"❌ Error: Could not fetch issue #{issue_number} from {repo}.")
        return False
    
    data = json.loads(issue_json)
    project_items = data.get("projectItems", [])
    
    if not project_items:
        print(f"❌ Error: Issue #{issue_number} is not assigned to any project.")
        return False
    
    item = project_items[0]
    current_status = item.get("status", {}).get("name")
    
    if not current_status:
        # Fallback to fieldValues if needed
        field_values = item.get("fieldValues", {}).get("nodes", [])
        status_node = next((node for node in field_values if node.get("field", {}).get("name") == "Status"), None)
        if status_node:
            current_status = status_node.get("name")
            
    if not current_status:
        print("❌ Error: Could not determine current status.")
        return False
        
    allowed_statuses = GATES.get(persona_name, [])
    if current_status not in allowed_statuses:
        print(f"❌ Gate Failed: Persona '{persona_name}' is NOT authorized for '{current_status}'.")
        print(f"Allowed statuses: {', '.join(allowed_statuses)}")
        return False
        
    print(f"✅ Gate Passed: '{current_status}' is active.")
    
    # 2. Context Retrieval
    print(f"Retrieving context...")
    
    context = []
    context.append(f"MISSION CONTEXT FOR {persona_name.upper()}")
    context.append(f"ISSUE: #{issue_number} | STATUS: {current_status}")
    context.append(f"TITLE: {data.get('title')}")
    context.append(f"BODY:\n{data.get('body')}")
    
    comments = data.get("comments", [])
    if comments:
        context.append("\n--- COMMENTS ---")
        for i, comment in enumerate(comments, 1):
            context.append(f"COMMENT {i} (by {comment.get('author', {}).get('login')}):")
            context.append(comment.get("body"))
            context.append("-" * 20)
            
    print("\n" + "="*50)
    print("\n".join(context))
    print("="*50 + "\n")
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap an agent mission (Gate Check + Context Fetch).")
    parser.add_argument("issue_number", type=int, help="The issue number.")
    parser.add_argument("persona_name", type=str, help="The agent persona (e.g., Sherlock).")
    parser.add_argument("--repo", type=str, default=CONFIG["repo"], help="The repository (owner/repo).")
    
    args = parser.parse_args()
    
    if bootstrap_mission(args.issue_number, args.persona_name, args.repo):
        sys.exit(0)
    else:
        sys.exit(1)
