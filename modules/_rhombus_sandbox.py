from __future__ import annotations
from typing import Literal
import os, sys, ast, linecache, traceback, time, queue as q, multiprocessing


class CompilationSandboxError(Exception):
    """Wird geworfen, wenn der Sandbox-Worker einen Fehler meldet."""
    pass


#======// Core Sandbox & Compilation //============================================================//

def _compile_worker(code_blocks: list[str], compilation_target_name: str | None, result_queue: multiprocessing.Queue) -> None:
    """
    WICHTIG: Dieser Worker MUSS auf Windows eine Top-Level Funktion sein (darf nicht in 
    compile_density verschachtelt sein), da multiprocessing.Process sonst einen Pickle-Error wirft!
    """
    sys.dont_write_bytecode = True  # Verhindert .pyc Schreibversuche, die den Audit Hook triggern
    
    # SECURITY: Entferne ALLE sensiblen Umgebungsvariablen aus dem Worker-Prozess!
    # (Sonst könnte der User einfach os.environ['DISCORD_TOKEN'] auslesen)
    for key in list(os.environ.keys()):
        if any(secret in key.upper() for secret in ('TOKEN', 'KEY', 'SECRET', 'PASS', 'AUTH')):
            del os.environ[key]
    
    print("[Worker] Started.", flush=True)
    def audit_hook(event, args):
        if event in ('os.system', 'os.exec', 'subprocess.Popen', 'socket.connect', 'socket.bind', 'urllib.Request'):
            print(f"[Worker] AUDIT BLOCKED: {event}", file=sys.stderr, flush=True)
            raise RuntimeError(f"Sandbox security violation: {event} is disabled.")
        if event == 'open':
            path = str(args[0])
            mode = str(args[1])
            
            # Schreibzugriff immer blockieren
            if 'w' in mode or 'a' in mode or '+' in mode:
                print(f"[Worker] AUDIT BLOCKED File Write: {path} (mode {mode})", file=sys.stderr, flush=True)
                raise RuntimeError("Sandbox security violation: File writing is disabled.")
                
            # Lesezugriff auf sensible Dateien blockieren (.env, id_rsa, etc.)
            path_lower = path.lower()
            if '.env' in path_lower or '.ssh' in path_lower or 'token' in path_lower or 'credentials' in path_lower:
                print(f"[Worker] AUDIT BLOCKED File Read: {path}", file=sys.stderr, flush=True)
                raise RuntimeError("Sandbox security violation: Access to sensitive files is denied.")
    
    sys.addaudithook(audit_hook)

    try:
        print("[Worker] Importing rhombus...", flush=True)
        import rhombus
        namespace = {
            "rhombus": rhombus,
            **{name: getattr(rhombus, name) for name in dir(rhombus) if not name.startswith('_')}
        }
        print("[Worker] Imported rhombus.", flush=True)
        
        print("[Worker] Executing code...", flush=True)
        
        for i, block in enumerate(code_blocks):
            block_name = f"<Code Block {i+1}>"
            # Registriere den Code im linecache, damit der Traceback die echten Zeilen anzeigen kann
            linecache.cache[block_name] = (len(block), None, [line + '\n' for line in block.splitlines()], block_name)
            
            if i == len(code_blocks) - 1 and compilation_target_name is None:
                tree = ast.parse(block)
                if not tree.body:
                    raise ValueError(f"Der Code-Block {i+1} ist leer.")
                
                last_node = tree.body[-1]
                if isinstance(last_node, ast.Expr):
                    tree.body.pop()
                    exec(compile(tree, filename=block_name, mode="exec"), namespace)
                    target_value = eval(compile(ast.Expression(last_node.value), filename=block_name, mode="eval"), namespace)
                    compilation_target_name = "<unbound expression>"
                    target_var = rhombus.Density(target_value)
                else:
                    raise ValueError("Es wurde kein 'compile' angegeben und der Code endet nicht mit einer freien Expression.")
            else:
                exec(compile(block, filename=block_name, mode="exec"), namespace)

        if compilation_target_name is not None and compilation_target_name != "<unbound expression>":
            if compilation_target_name not in namespace:
                raise ValueError(f"Variable `{compilation_target_name}` is not defined.")
            target_var = rhombus.Density(namespace[compilation_target_name])
            
        print(f"[Worker] Compiling `{compilation_target_name}`...", flush=True)
        files = target_var.compile()
        print("[Worker] Compiled.", flush=True)
        
        # Wir müssen die Dateien hier im Worker encoden, da BeetFile Objekte evtl. 
        # nicht sicher durch die Multiprocessing-Queue gepickled werden können.
        files_data: list[tuple[str, str]] = []

        for identifier, beet_file in files:
            content_str = beet_file.encoder(beet_file.data)
            filename = identifier.split(":")[0] + "/" + "/".join(beet_file.scope) + "/" + identifier.split(":")[-1] + beet_file.extension
            files_data.append((filename, content_str))
            
        print("[Worker] Putting results in queue...", flush=True)
        result_queue.put({"success": files_data})
        print("[Worker] Done.", flush=True)
        
    except Exception as e:
        tb_exc = traceback.TracebackException.from_exception(e)
        
        # Filtere Traceback: Behalte nur Code-Blöcke (alles andere ist interner Rhombus-Code)
        filtered_stack = traceback.StackSummary()
        has_code_block = False
        for frame in tb_exc.stack:
            if frame.filename.startswith("<Code Block"):
                filtered_stack.append(frame)
                has_code_block = True
                
        if has_code_block:
            tb_exc.stack = filtered_stack
            
        error_trace = "".join(tb_exc.format())
        print(f"[Worker] ERROR: {type(e).__name__}", file=sys.stderr, flush=True)
        result_queue.put({"error": error_trace})

def compile_density(code_blocks: list[str], compilation_target_name: str | None = None) -> list[tuple[str, str]]:
    """
    Zentrales Interface für die Sandbox.
    Nimmt den User-Code und den Ziel-Variablennamen, führt ihn sicher in einem Subprozess aus
    und gibt eine Liste von (Dateiname, Datei_Inhalt_String) zurück.
    """
    queue = multiprocessing.Queue()
    
    # target darf kein Lambda sein, sonst crasht multiprocessing auf Windows beim Start!
    process = multiprocessing.Process(target=_compile_worker, args=(code_blocks, compilation_target_name, queue))
    process.start()

    start_time = time.time()
    timeout = 30.0
    result_data: dict[Literal["success"], list[tuple[str, str]]] | dict[Literal["error"], str] = None
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            print("[Main] Worker timed out!", flush=True)
            process.terminate()
            process.join()
            raise CompilationSandboxError("TimeoutError: Compilation took too long (infinite loop?).")
            
        try:
            # Blockiert bis zu 0.5s und wartet auf Daten
            result_data = queue.get(timeout=0.5)
            break
        except q.Empty:
            if not process.is_alive():
                # Prozess ist tot, versuche ein letztes Mal Daten zu lesen
                try:
                    result_data = queue.get_nowait()
                    break
                except q.Empty:
                    print("[Main] Worker crashed unexpectedly.", flush=True)
                    raise CompilationSandboxError("RuntimeError: Worker process crashed unexpectedly.")

    if result_data and "error" in result_data:
        raise CompilationSandboxError(result_data["error"])
        
    if result_data and "success" in result_data:
        return result_data["success"]
        
    raise CompilationSandboxError("Unknown error occurred during compilation.")
