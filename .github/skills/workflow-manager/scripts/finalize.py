import json
import subprocess
import sys
import argparse
import os

# Import the configuration
try:
    from workflow_config import TRANSITIONS
    from utils import load_config
except ImportError:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from workflow_config import TRANSITIONS
    from utils import load_config

CONFIG = load_config()

def run_command(command, env=None):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, env=env)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e.stderr}")
        return None

def post_comment(issue_number, comment_file, repo=CONFIG["repo"]):
    print(f"Posting comment to issue #{issue_number}...")
    try:
        with open(comment_file, "r", encoding="utf-8") as f:
            comment_body = f.read()
    except Exception as e:
        print(f"❌ Error reading comment file: {e}")
        return False

    result = run_command([
        "gh", "issue", "comment", str(issue_number),
        "--repo", repo,
        "--body", comment_body
    ])
    return result is not None

def add_memory(text_file, project, role, namespace):
    print(f"Syncing to Myosotis (Namespace: {namespace})...")
    try:
        with open(text_file, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        print(f"❌ Error reading memory file: {e}")
        return False

    # Construct PYTHONPATH to find the myosotis package
    root_dir = os.getcwd()
    myosotis_dir = os.path.join(root_dir, "flask_blogs", "myosotis")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = myosotis_dir + os.pathsep + env.get("PYTHONPATH", "")

    # Call Myosotis CLI
    result = run_command([
        sys.executable, "-m", "myosotis.cli.main", "add",
        text,
        "--project", project,
        "--role", role,
        "--namespace", namespace
    ], env=env)
    
    if result:
        print(f"✅ Myosotis Sync: {result}")
        return True
    return False

def transition_workflow(issue_number, outcome, repo=CONFIG["repo"]):
    print(f"Updating GitHub Project status (Outcome: {outcome})...")
    
    # 1. Get current status
    issue_json = run_command([
        "gh", "issue", "view", str(issue_number),
        "--repo", repo,
        "--json", "projectItems"
    ])
    
    if not issue_json:
        return False
    
    data = json.loads(issue_json)
    project_items = data.get("projectItems", [])
    if not project_items:
        return False
    
    item = project_items[0]
    current_status = item.get("status", {}).get("name")
    
    if not current_status:
        field_values = item.get("fieldValues", {}).get("nodes", [])
        status_node = next((node for node in field_values if node.get("field", {}).get("name") == "Status"), None)
        if status_node:
            current_status = status_node.get("name")

    if not current_status:
        return False

    # 2. Determine target status
    status_transitions = TRANSITIONS.get(current_status)
    if not status_transitions:
        print(f"❌ Error: No transitions defined for '{current_status}'.")
        return False
    
    target_status = status_transitions.get(outcome)
    if not target_status:
        print(f"❌ Error: No target for outcome '{outcome}' from '{current_status}'.")
        return False

    # 3. Update status (import logic from transition.py or reimplement)
    # Reimplementing simplified version here
    item_id = item.get("id")
    project_id = item.get("project", {}).get("id")
    project_number = item.get("project", {}).get("number")
    
    # Find field and option IDs
    fields_json = run_command([
        "gh", "project", "field-list", str(project_number),
        "--owner", repo.split("/")[0],
        "--format", "json"
    ])
    
    if not fields_json:
        return False
    
    fields_data = json.loads(fields_json)
    status_field = next((f for f in fields_data.get("fields", []) if f.get("name") == "Status"), None)
    if not status_field:
        return False
    
    field_id = status_field.get("id")
    option = next((o for o in status_field.get("options", []) if o.get("name").lower() == target_status.lower()), None)
    if not option:
        return False
    
    option_id = option.get("id")
    
    # Apply update
    update_result = run_command([
        "gh", "project", "item-edit",
        "--id", item_id,
        "--project-id", project_id,
        "--field-id", field_id,
        "--single-select-option-id", option_id
    ])
    
    if update_result:
        print(f"✅ Project Status: Advanced from '{current_status}' to '{target_status}'.")
        return True
    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Finalize an agent mission (GitHub + Myosotis + Project Status).")
    parser.add_argument("issue_number", type=int, help="The issue number.")
    parser.add_argument("outcome", type=str, help="Mission outcome (success, failure, revision_requested, etc.).")
    parser.add_argument("--comment-file", type=str, help="File with GitHub comment body.")
    parser.add_argument("--memory-file", type=str, help="File with Myosotis memory text.")
    parser.add_argument("--memory-project", type=str, default=CONFIG["myosotis_project"], help="Myosotis project.")
    parser.add_argument("--memory-role", type=str, help="Myosotis role (e.g., product_owner).")
    parser.add_argument("--memory-namespace", type=str, help="Myosotis namespace (e.g., requirements).")
    parser.add_argument("--repo", type=str, default=CONFIG["repo"], help="The repository.")
    
    args = parser.parse_args()
    
    print(f"--- 🏁 Mission Finalization (Issue #{args.issue_number}) ---")
    
    success = True
    
    # 1. Post GitHub Comment
    if args.comment_file:
        if not post_comment(args.issue_number, args.comment_file, args.repo):
            success = False

    # 2. Sync to Myosotis
    if args.memory_file and args.memory_role and args.memory_namespace:
        if not add_memory(args.memory_file, args.memory_project, args.memory_role, args.memory_namespace):
            success = False
    elif args.memory_file:
        print("⚠️ Warning: Memory file provided but role/namespace missing. Skipping Myosotis sync.")

    # 3. Transition Project Status
    if not transition_workflow(args.issue_number, args.outcome, args.repo):
        success = False

    if success:
        print("🎉 Mission Finalized Successfully.")
        sys.exit(0)
    else:
        print("❌ Mission Finalization encountered errors.")
        sys.exit(1)
