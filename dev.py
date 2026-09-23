import os
import sys
import time
import subprocess

def get_latest_mtime():
    """Finds the newest timestamp of all Python files in the directory (except dev.py)."""
    mtime = 0
    for root, _, files in os.walk('.'):
        # Ignore caches and git
        if '.git' in root or '__pycache__' in root or '.venv' in root:
            continue
        for file in files:
            if file.endswith('.py') and file != 'dev.py':
                file_path = os.path.join(root, file)
                mtime = max(mtime, os.path.getmtime(file_path))
    return mtime

if __name__ == '__main__':
    print("Starting Development Server with hot-reloading...")
    last_mtime = get_latest_mtime()
    
    # Start the actual bot
    process = subprocess.Popen([sys.executable, "main.py"])

    try:
        while True:
            time.sleep(1.0)
            current_mtime = get_latest_mtime()
            
            if current_mtime > last_mtime:
                print("\n[Dev] File change detected! Restarting bot...")
                last_mtime = current_mtime
                
                # Terminate the old process cleanly
                process.terminate()
                process.wait()
                
                # Start the new process
                process = subprocess.Popen([sys.executable, "main.py"])
                
    except KeyboardInterrupt:
        print("\n[Dev] Terminating Development Server...")
        process.terminate()
