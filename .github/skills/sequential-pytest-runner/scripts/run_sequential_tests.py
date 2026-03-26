import os
import sys
import subprocess
import argparse

# Correctly locate the .gemini/tmp directory relative to this script
PROGRESS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "tmp", "pytest_progress.txt"))

def get_test_nodes(test_dir):
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    
    # Run pytest --collect-only -q to get a list of tests
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q"]
    if test_dir and test_dir != ".":
        cmd.append(test_dir)
        
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode not in (0, 5):
        print(f"Failed to collect tests:\n{result.stderr or result.stdout}")
        sys.exit(1)
        
    nodes = []
    for line in result.stdout.splitlines():
        # A test node usually looks like 'tests/test_file.py::test_name'
        if "::" in line and not line.startswith("warnings") and not line.startswith("="):
            nodes.append(line.strip())
            
    return nodes

def load_passed_nodes():
    if not os.path.exists(PROGRESS_FILE):
        return set()
    with open(PROGRESS_FILE, "r") as f:
        return set(line.strip() for line in f if line.strip())

def save_passed_node(node):
    # Ensure the directory exists
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "a") as f:
        f.write(node + "\n")

def clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)

def run_full_suite(test_dir="."):
    print("\n🚀 Running full test suite for final validation...")
    clear_progress()
    
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    cmd = [sys.executable, "-m", "pytest"]
    if test_dir and test_dir != ".":
        cmd.append(test_dir)
    
    # We don't capture here because it's the final run and user might want to see it,
    # but we could if needed.
    result = subprocess.run(cmd, env=env)
    if result.returncode == 0:
        print("\n✅ Final full test run passed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Final full test run failed. Please investigate.")
        sys.exit(1)

def run_tests_sequentially(test_dir="."):
    collected_nodes = get_test_nodes(test_dir)
    if not collected_nodes:
        print("No tests found.")
        return
        
    passed_nodes = load_passed_nodes()
    pending_nodes = [node for node in collected_nodes if node not in passed_nodes]
    
    if not pending_nodes:
        print("\n🎉 All tests have already passed sequentially at least once!")
        run_full_suite(test_dir)
            
    total = len(collected_nodes)
    passed_count = len(passed_nodes)
    remaining = len(pending_nodes)
    
    print(f"Total tests: {total}")
    print(f"Already passed: {passed_count}")
    print(f"Remaining: {remaining}")
    print("Running remaining tests sequentially (silent mode)...\n")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    
    for i, node in enumerate(pending_nodes, 1):
        current_idx = i + passed_count
        # Use carriage return to update the same line, reducing terminal scroll load
        sys.stdout.write(f"\r[{current_idx}/{total}] Testing: {node[:60]}...".ljust(80))
        sys.stdout.flush()
        
        # Run the single test with captured output to avoid flooding the terminal
        cmd = [sys.executable, "-m", "pytest", "-q", node]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"\n\n❌ Test failed: {node}")
            print("="*40)
            
            # Limit output to avoid crashing the terminal
            lines = (result.stdout + (result.stderr or "")).strip().splitlines()
            limit = 50
            if len(lines) > limit:
                print("\n".join(lines[:limit]))
                print(f"\n... ({len(lines) - limit} more lines truncated)")
            else:
                print("\n".join(lines))
                
            print("="*40)
            print("Stopping sequential execution. Fix this test and run the script again to resume.")
            sys.exit(1)
            
        save_passed_node(node)
            
    print("\n\n✅ All tests passed sequentially!")
    run_full_suite(test_dir)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run pytest tests sequentially and stop on failure, with resume support.")
    parser.add_argument("test_dir", nargs="?", default=".", help="Directory or file to run tests from.")
    args = parser.parse_args()
    
    run_tests_sequentially(args.test_dir)
