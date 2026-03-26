import subprocess
import time
import sys
import os
import requests
from signal import SIGTERM

def wait_for_app(url, timeout=30):
    start_time = time.time()
    # Print on a single line with carriage return to avoid flooding terminal
    while time.time() - start_time < timeout:
        try:
            sys.stdout.write(f"\rWaiting for app at {url}... {int(time.time() - start_time)}s".ljust(50))
            sys.stdout.flush()
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                print(f"\n✅ App is ready at {url}")
                return True
        except requests.exceptions.ConnectionError:
            pass
        except Exception as e:
            pass
        time.sleep(1)
    print("\n❌ Timed out waiting for app.")
    return False

def run_tests(app_dir, app_port, test_file):
    env = os.environ.copy()
    env["FLASK_APP"] = "run.py"
    env["PYTHONPATH"] = os.path.abspath(app_dir)
    
    # Logs are already excluded from git/AI
    log_path = os.path.abspath("flask_app.log")
    log_file = open(log_path, "w")
    
    try:
        app_process = subprocess.Popen(
            [sys.executable, "-m", "flask", "run", "--port", str(app_port), "--with-threads"],
            cwd=app_dir,
            env=env,
            stdout=log_file,
            stderr=log_file,
            text=True
        )
        
        url = f"http://127.0.0.1:{app_port}"
        
        if wait_for_app(url):
            print(f"🚀 Running tests in {test_file}...")
            # Capture output to avoid flooding terminal unless failure occurs
            test_process = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", test_file, f"--base-url={url}"],
                env=env,
                capture_output=True,
                text=True
            )
            
            if test_process.returncode != 0:
                print("\n❌ UI Tests failed!")
                print("--- Pytest Output (Truncated) ---")
                lines = (test_process.stdout + (test_process.stderr or "")).strip().splitlines()
                limit = 50
                if len(lines) > limit:
                    print("\n".join(lines[:limit]))
                    print(f"\n... ({len(lines) - limit} more lines truncated)")
                else:
                    print("\n".join(lines))
            else:
                print("\n✅ UI Tests passed successfully!")
            
            return test_process.returncode == 0
        else:
            print("\n--- App Logs (last 50 lines) ---")
            log_file.flush()
            with open(log_path, "r") as f:
                lines = f.readlines()
                limit = 50
                for line in lines[-limit:]:
                    print(line.strip())
            return False
    except Exception as e:
        print(f"\nFatal error: {e}")
        return False
    finally:
        if 'app_process' in locals():
            app_process.terminate()
            try:
                app_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app_process.kill()
        log_file.close()

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python run_ui_test.py <app_dir> <app_port> <test_file>")
        sys.exit(1)
    
    app_dir = sys.argv[1]
    app_port = int(sys.argv[2])
    test_file = sys.argv[3]
    
    success = run_tests(app_dir, app_port, test_file)
    sys.exit(0 if success else 1)
