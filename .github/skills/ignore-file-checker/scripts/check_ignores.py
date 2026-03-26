import subprocess
import os
import sys

def run_command(command, cwd=None):
    try:
        result = subprocess.run(command, capture_output=True, text=True, cwd=cwd, shell=True)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1

def check_ignores(root_dir="."):
    print(f"--- Ignore File Audit for {os.path.abspath(root_dir)} ---")
    
    # 1. Tracked files that are ignored
    stdout, stderr, code = run_command("git ls-files -i -c --exclude-standard", cwd=root_dir)
    if stdout:
        print("\n[!] Tracked files that match ignore patterns (should probably be removed from Git):")
        for line in stdout.splitlines():
            print(f"  - {line}")
    else:
        print("\n[✓] No tracked files match ignore patterns.")

    # 2. Untracked files that are not ignored
    stdout, stderr, code = run_command("git ls-files -o --exclude-standard", cwd=root_dir)
    if stdout:
        print("\n[!] Untracked files that are NOT ignored (should probably be added to ignore files):")
        for line in stdout.splitlines():
            print(f"  - {line}")
    else:
        print("\n[✓] All untracked files are correctly ignored.")

    # 3. Find ignore files and check for non-recursive patterns
    ignore_files = []
    for r, d, f in os.walk(root_dir):
        if ".git" in d: d.remove(".git")
        for file in f:
            if file in [".gitignore", ".geminiignore"]:
                ignore_files.append(os.path.join(r, file))

    if ignore_files:
        print("\n--- Auditing Ignore File Patterns ---")
        common_dirs = ["env", "venv", ".venv", "node_modules", "__pycache__", ".pytest_cache"]
        for ignore_file in ignore_files:
            print(f"\nChecking: {ignore_file}")
            with open(ignore_file, "r") as f:
                content = f.read()
                for d in common_dirs:
                    if d in content and f"**/{d}" not in content and f"/{d}" not in content:
                        print(f"  [!] Pattern '{d}' might be non-recursive. Consider using '**/{d}/'.")
    else:
        print("\n[!] No .gitignore or .geminiignore files found.")

    # 4. Check for submodules
    stdout, stderr, code = run_command("git submodule status", cwd=root_dir)
    if stdout:
        print("\n--- Submodule Audit ---")
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                submodule_path = parts[1]
                print(f"\nSubmodule: {submodule_path}")
                check_ignores(os.path.join(root_dir, submodule_path))

if __name__ == "__main__":
    check_ignores()
