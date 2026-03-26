import json
import subprocess
import sys
import os

# Helper to run shell commands
def run_command(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e.stderr}")
        return None

def update_status(issue_number, target_status, repo="SchneiderDaniel/flask_blogs"):
    print(f"Updating issue #{issue_number} status to '{target_status}' in repository {repo}...")
    
    # 1. Get issue project details
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
        print(f"❌ Error: Issue #{issue_number} is not associated with any project.")
        return False
    
    item = project_items[0]
    item_id = item.get("id")
    project_id = item.get("project", {}).get("id")
    project_number = item.get("project", {}).get("number")
    
    # 2. Find field and option IDs
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
        print("❌ Error: Could not find 'Status' field in project.")
        return False
    
    field_id = status_field.get("id")
    option = next((o for o in status_field.get("options", []) if o.get("name").lower() == target_status.lower()), None)
    if not option:
        print(f"❌ Error: Option '{target_status}' not found in Status field.")
        print(f"Available options: {', '.join([o['name'] for o in status_field.get('options', [])])}")
        return False
    
    option_id = option.get("id")
    
    # 3. Apply update
    update_result = run_command([
        "gh", "project", "item-edit",
        "--id", item_id,
        "--project-id", project_id,
        "--field-id", field_id,
        "--single-select-option-id", option_id
    ])
    
    if update_result:
        print(f"✅ Successfully updated issue #{issue_number} status to '{target_status}'.")
        return True
    return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python update_issue_status.py <issue_number> <target_status> [repo]")
        sys.exit(1)
    
    issue_num = sys.argv[1]
    status = sys.argv[2]
    repository = sys.argv[3] if len(sys.argv) > 3 else "SchneiderDaniel/flask_blogs"
    
    if update_status(issue_num, status, repository):
        sys.exit(0)
    else:
        sys.exit(1)
