import os
import sys
import time
import subprocess

def get_latest_mtime():
    """Findet den neuesten Zeitstempel aller Python-Dateien im Verzeichnis (außer dev.py)."""
    mtime = 0
    for root, _, files in os.walk('.'):
        # Ignoriere Caches und Git
        if '.git' in root or '__pycache__' in root or '.venv' in root:
            continue
        for file in files:
            if file.endswith('.py') and file != 'dev.py':
                file_path = os.path.join(root, file)
                mtime = max(mtime, os.path.getmtime(file_path))
    return mtime

if __name__ == '__main__':
    print("Starte Development Server mit Hot-Reloading...")
    last_mtime = get_latest_mtime()
    
    # Starte den echten Bot
    process = subprocess.Popen([sys.executable, "main.py"])

    try:
        while True:
            time.sleep(1.0)
            current_mtime = get_latest_mtime()
            
            if current_mtime > last_mtime:
                print("\n[Dev] Datei-Änderung erkannt! Starte Bot neu...")
                last_mtime = current_mtime
                
                # Alten Prozess sauber beenden
                process.terminate()
                process.wait()
                
                # Neuen Prozess starten
                process = subprocess.Popen([sys.executable, "main.py"])
                
    except KeyboardInterrupt:
        print("\n[Dev] Beende Development Server...")
        process.terminate()
