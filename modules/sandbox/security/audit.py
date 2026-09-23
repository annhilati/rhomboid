import sys
import os

def setup_audit_hook(work_dir: str):
    def audit_hook(event, args):
        # Block dangerous modules/functions (ctypes must be handled OS-side to not break Windows imports)
        if event in ('os.system', 'os.exec', 'subprocess.Popen', 'socket.connect', 'socket.bind', 'urllib.Request'):
            raise RuntimeError(f'Sandbox security violation: {event} is disabled.')
            
        # Block write outside work_dir
        if event == 'open':
            path = os.path.abspath(str(args[0]))
            mode = str(args[1]) if len(args) > 1 else 'r'
            if 'w' in mode or 'a' in mode or '+' in mode:
                if not path.startswith(os.path.abspath(work_dir)):
                    raise RuntimeError(f'Sandbox security violation: Write outside work dir: {path}')
    
    sys.addaudithook(audit_hook)