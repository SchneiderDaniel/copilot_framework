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
        return None

def get_mission_status(issue_number, repo=CONFIG["repo"]):
    """
    Checks the current status of an issue and identifies the authorized agent.
    """
    issue_json = run_command([
        "gh", "issue", "view", str(issue_number),
        "--repo", repo,
        "--json", "title,projectItems"
    ])
    
    if not issue_json:
        print(f"❌ Error: Could not find issue #{issue_number}.")
        return

    data = json.loads(issue_json)
    project_items = data.get("projectItems", [])
    
    if not project_items:
        # Cross-repo project discovery attempt
        print("🔍 Searching for cross-repo project association...")
        # Try to find projects owned by the user/org that contain this issue
        user_projects = run_command(["gh", "project", "list", "--owner", repo.split('/')[0], "--format", "json"])
        if user_projects:
            projects = json.loads(user_projects)
            for p in projects:
                p_number = p.get("number")
                p_owner = repo.split('/')[0]
                # Check if this issue is in this project
                items = run_command(["gh", "project", "item-list", str(p_number), "--owner", p_owner, "--format", "json"])
                if items:
                    item_data = json.loads(items)
                    # For ProjectV2, items can be issues or PRs. Look for a match.
                    match = next((i for i in item_data if i.get("content", {}).get("number") == issue_number), None)
                    if match:
                        project_items = [match]
                        break

    if not project_items:
        print(f"📍 Issue #{issue_number}: '{data.get('title')}'")
        print("⚠️ Status: NOT IN PROJECT. (Please add it to the project first.)")
        return

    item = project_items[0]
    current_status = item.get("status", {}).get("name")
    
    if not current_status:
        # Fallback to fieldValues
        field_values = item.get("fieldValues", {}).get("nodes", [])
        status_node = next((node for node in field_values if node.get("field", {}).get("name") == "Status"), None)
        if status_node:
            current_status = status_node.get("name")

    print(f"📍 Issue #{issue_number}: '{data.get('title')}'")
    print(f"⚙️ Current Status: '{current_status}'")
    
    # Identify authorized personas
    authorized_personas = [p for p, statuses in GATES.items() if current_status in statuses]
    
    if not authorized_personas:
        print("🛑 No agent is currently authorized for this status.")
    else:
        print(f"👤 Authorized Agents: {', '.join(authorized_personas)}")
        print("\n--- Next Step ---")
        primary_agent = authorized_personas[0]
        # Special case for Implementation where Mycroft might group first
        if "Implementation" in current_status and "Mycroft" in authorized_personas:
             print(f"👉 Recommended: Run Mycroft first for grouping, then Watson.")
        
        print(f"Run the following to start the mission:")
        print(f"  gemini run {primary_agent.lower()} {issue_number}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check mission status and identify the next agent.")
    parser.add_argument("issue_number", type=int, help="The issue number.")
    parser.add_argument("--repo", type=str, default=CONFIG["repo"], help="The repository.")
    parser.add_argument("--status", type=str, help="Manual override for the issue status.")
    
    args = parser.parse_args()
    
    if args.status:
        # Mock the project items for manual override
        print(f"📍 Issue #{args.issue_number} (Manual Override)")
        print(f"⚙️ Current Status: '{args.status}'")
        authorized_personas = [p for p, statuses in GATES.items() if args.status in statuses]
        if not authorized_personas:
            print("🛑 No agent is currently authorized for this status.")
        else:
            print(f"👤 Authorized Agents: {', '.join(authorized_personas)}")
            print("\n--- Next Step ---")
            primary_agent = authorized_personas[0]
            print(f"Run the following to start the mission:")
            print(f"  gemini run {primary_agent.lower()} {args.issue_number}")
    else:
        get_mission_status(args.issue_number, args.repo)
