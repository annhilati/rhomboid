import sys
import os

def setup_audit_hook(work_dir: str):
    def audit_hook(event, args):
        # Block dangerous modules/functions (ctypes must be handled OS-side to not break Windows imports)
        if event in ('os.system', 'os.exec', 'socket.bind'):
            raise RuntimeError(f'Sandbox security violation: {event} is disabled.')
            
        if event == 'urllib.Request':
            url = str(args[0])
            if not url.startswith('https://raw.githubusercontent.com/misode/mcmeta/'):
                raise RuntimeError(f'Sandbox security violation: urllib.Request to {url} is disabled.')
            
        if event == 'subprocess.Popen':
            exe = str(args[0]) if args[0] else (str(args[1][0]) if len(args) > 1 and args[1] else '')
            if 'fc-list' not in exe:
                raise RuntimeError(f'Sandbox security violation: subprocess.Popen is disabled.')
            
        # Block write outside work_dir
        if event == 'open':
            path = os.path.normcase(os.path.realpath(str(args[0])))
            mode = str(args[1]) if len(args) > 1 else 'r'
            if 'w' in mode or 'a' in mode or '+' in mode:
                work_dir_prefix = os.path.normcase(os.path.realpath(work_dir))
                if not work_dir_prefix.endswith(os.sep):
                    work_dir_prefix += os.sep
                if not path.startswith(work_dir_prefix):
                    raise RuntimeError(f'Sandbox security violation: Write outside work dir: {str(args[0])}\nResolved path: {path}\nWork dir: {work_dir_prefix}')
    
    sys.addaudithook(audit_hook)