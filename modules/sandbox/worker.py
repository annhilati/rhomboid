import sys
import os
import traceback
import tempfile
import multiprocessing
from .security.environment import clean_environment
from .security.audit import setup_audit_hook
from .security.resources import apply_resource_limits
from .security.ipc import encode_payload
from .compilation import execute_rhombus_code
from .policy import limits
from .policy import filesystem_policy

def _persistent_worker_loop(task_queue: multiprocessing.Queue, result_queue: multiprocessing.Queue):
    sys.dont_write_bytecode = True
    clean_environment()
    # Wir setzen MAX_CPU_TIME extrem hoch, da der Worker wiederverwendet wird. Timeout wird vom Runner erzwungen.
    apply_resource_limits(limits.MAX_RAM_MB, 999999, limits.MAX_FILES_OPEN)
    
    with tempfile.TemporaryDirectory(prefix=filesystem_policy.WORK_DIR_PREFIX) as work_dir:
        # Weichen matplotlib in unser Sandbox-Verzeichnis um, damit der Font-Cache geschrieben werden darf
        os.environ['MPLCONFIGDIR'] = work_dir
        setup_audit_hook(work_dir)
        
        while True:
            try:
                code_blocks = task_queue.get()
                if code_blocks is None:
                    break
            except Exception:
                break
                
            try:
                result = execute_rhombus_code(code_blocks)
                result_queue.put(encode_payload(True, result))
            except Exception as e:
                tb_exc = traceback.TracebackException.from_exception(e)
                
                # Anonymize all paths in the traceback to protect privacy
                cwd_path = os.path.abspath(os.getcwd())
                home_path = os.path.abspath(os.path.expanduser('~'))
                for frame in tb_exc.stack:
                    if frame.filename and frame.filename != '<Code Blocks>':
                        fpath = os.path.abspath(frame.filename)
                        if fpath.startswith(cwd_path):
                            frame.filename = fpath.replace(cwd_path, '.', 1)
                        elif fpath.startswith(home_path):
                            frame.filename = fpath.replace(home_path, '~', 1)
                            
                filtered_stack = traceback.StackSummary()
                has_code_block = False
                for frame in tb_exc.stack:
                    if frame.filename == '<Code Blocks>':
                        frame.lineno -= 2
                        if hasattr(frame, 'end_lineno') and frame.end_lineno is not None:
                            frame.end_lineno -= 2
                            
                        if frame.name == 'rhombus_code':
                            frame.name = '<module>'
                            filtered_stack.append(frame)
                            has_code_block = True
                        elif frame.name in ('if_branch', 'else_branch', 'with_block'):
                            if filtered_stack:
                                filtered_stack[-1].lineno = frame.lineno
                                filtered_stack[-1]._line = frame._line
                                if hasattr(frame, 'end_lineno'):
                                    filtered_stack[-1].end_lineno = frame.end_lineno
                                    filtered_stack[-1].colno = getattr(frame, 'colno', None)
                                    filtered_stack[-1].end_colno = getattr(frame, 'end_colno', None)
                        else:
                            filtered_stack.append(frame)
                            has_code_block = True
                if has_code_block:
                    tb_exc.stack = filtered_stack
                result_queue.put(encode_payload(False, ''.join(tb_exc.format())))