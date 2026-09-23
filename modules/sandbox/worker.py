import sys
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

def _compile_worker(code_blocks: list[str], target_name: str | None, queue: multiprocessing.Queue):
    sys.dont_write_bytecode = True
    clean_environment()
    apply_resource_limits(limits.MAX_RAM_MB, limits.MAX_CPU_TIME, limits.MAX_FILES_OPEN)
    
    with tempfile.TemporaryDirectory(prefix=filesystem_policy.WORK_DIR_PREFIX) as work_dir:
        setup_audit_hook(work_dir)
        
        try:
            result = execute_rhombus_code(code_blocks, target_name)
            queue.put(encode_payload(True, result))
        except Exception as e:
            tb_exc = traceback.TracebackException.from_exception(e)
            filtered_stack = traceback.StackSummary()
            has_code_block = False
            for frame in tb_exc.stack:
                if frame.filename.startswith('<Code Block'):
                    filtered_stack.append(frame)
                    has_code_block = True
            if has_code_block:
                tb_exc.stack = filtered_stack
            queue.put(encode_payload(False, ''.join(tb_exc.format())))