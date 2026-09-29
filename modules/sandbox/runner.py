import multiprocessing
import time
import asyncio
import queue as q
from .worker import _persistent_worker_loop
from .policy.limits import TIMEOUT_SECONDS
from .security.ipc import decode_payload

class CompilationSandboxError(Exception):
    pass


class WorkerManager:
    def __init__(self):
        self.process = None
        self.task_queue = None
        self.result_queue = None

    def start(self):
        ctx = multiprocessing.get_context('spawn')
        self.task_queue = ctx.Queue()
        self.result_queue = ctx.Queue()
        self.process = ctx.Process(target=_persistent_worker_loop, args=(self.task_queue, self.result_queue))
        self.process.start()

    def restart(self):
        if self.process and self.process.is_alive():
            self.process.kill()
            self.process.join()
        self.start()

_manager = WorkerManager()

async def compile_density(code_blocks: list[str]) -> list[tuple[str, str]]:
    if _manager.process is None or not _manager.process.is_alive():
        _manager.restart()
        
    _manager.task_queue.put(code_blocks)
    start_time = time.time()
    result_data = None
    
    while True:
        if time.time() - start_time > TIMEOUT_SECONDS:
            _manager.restart()
            raise CompilationSandboxError('TimeoutError: Compilation took too long.')
            
        try:
            raw_payload = _manager.result_queue.get_nowait()
            result_data = decode_payload(raw_payload)
            break
        except q.Empty:
            if not _manager.process.is_alive():
                _manager.restart()
                raise CompilationSandboxError('RuntimeError: Worker process crashed unexpectedly.')
            await asyncio.sleep(0.1)

    if not result_data['success']:
        raise CompilationSandboxError(result_data['data'])
        
    return result_data['data']