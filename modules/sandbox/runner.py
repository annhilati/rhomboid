import multiprocessing
import time
import queue as q
from .worker import _compile_worker
from .policy.limits import TIMEOUT_SECONDS
from .security.ipc import decode_payload

class CompilationSandboxError(Exception):
    pass

def compile_density(code_blocks: list[str], compilation_target_name: str | None = None) -> list[tuple[str, str]]:
    queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_compile_worker, args=(code_blocks, compilation_target_name, queue))
    process.start()

    start_time = time.time()
    result_data = None
    
    while True:
        if time.time() - start_time > TIMEOUT_SECONDS:
            process.terminate()
            process.join()
            raise CompilationSandboxError('TimeoutError: Compilation took too long.')
            
        try:
            raw_payload = queue.get(timeout=0.5)
            result_data = decode_payload(raw_payload)
            break
        except q.Empty:
            if not process.is_alive():
                try:
                    raw_payload = queue.get_nowait()
                    result_data = decode_payload(raw_payload)
                    break
                except q.Empty:
                    raise CompilationSandboxError('RuntimeError: Worker process crashed unexpectedly.')

    if not result_data['success']:
        raise CompilationSandboxError(result_data['data'])
        
    return result_data['data']