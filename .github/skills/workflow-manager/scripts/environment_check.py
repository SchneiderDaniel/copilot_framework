import subprocess
import sys
import os

def check_command(command, args=None):
    if args is None:
        args = ["--version"]
    try:
        result = subprocess.run([command] + args, capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip().split('\n')[0]
            return True, version
        return False, "Command failed"
    except FileNotFoundError:
        return False, "Not found"

def check_gh_auth():
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if "Logged in to github.com" in result.stdout or "Logged in to github.com" in result.stderr:
            return True, "Authenticated"
        return False, "Not logged in"
    except Exception as e:
        return False, str(e)

def run_checks():
    print("--- 🔍 Environment Health Check ---")
    
    checks = {
        "GitHub CLI (gh)": ("gh", ["--version"]),
        "Python": (sys.executable, ["--version"]),
        "Pytest": ("pytest", ["--version"]),
        "Pybabel": ("pybabel", ["--version"]),
    }
    
    all_passed = True
    
    for label, (cmd, args) in checks.items():
        passed, info = check_command(cmd, args)
        status = "✅" if passed else "❌"
        print(f"{status} {label}: {info}")
        if not passed:
            all_passed = False
            
    # Check GH Auth
    passed, info = check_gh_auth()
    status = "✅" if passed else "❌"
    print(f"{status} GitHub Auth: {info}")
    if not passed:
        all_passed = False
        
    # Check Myosotis
    root_dir = os.getcwd()
    myosotis_dir = os.path.join(root_dir, "flask_blogs", "myosotis")
    if os.path.exists(myosotis_dir):
        print(f"✅ Myosotis Package: Found at {myosotis_dir}")
    else:
        print(f"❌ Myosotis Package: NOT FOUND at {myosotis_dir}")
        all_passed = False
        
    print("-" * 35)
    if all_passed:
        print("🎉 All systems go! Ready for missions.")
    else:
        print("⚠️ Some checks failed. Agents may encounter issues.")
        
    return all_passed

if __name__ == "__main__":
    if run_checks():
        sys.exit(0)
    else:
        sys.exit(1)
