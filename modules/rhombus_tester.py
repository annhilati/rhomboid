from __future__ import annotations
from typing import Any, TYPE_CHECKING, Literal
import re, io, asyncio, traceback, time, queue as q, sys, multiprocessing

import discord
import discord.app_commands as app_commands

import rhombus
from rhombus.core import BeetFile

if TYPE_CHECKING:
    from main import RhombusClient


MESSAGE_CACHE: dict[int, discord.Message] = {}
"Key is id of original message, value is bot reply message"


class CompilationSandboxError(Exception):
    """Wird geworfen, wenn der Sandbox-Worker einen Fehler meldet."""
    pass


#======// Core Sandbox & Compilation //============================================================//

def _compile_worker(code: str, compilation_target_name: str | None, result_queue: multiprocessing.Queue):
    """
    WICHTIG: Dieser Worker MUSS auf Windows eine Top-Level Funktion sein (darf nicht in 
    compile_density verschachtelt sein), da multiprocessing.Process sonst einen Pickle-Error wirft!
    """
    import os
    import sys
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
        import ast
        tree = ast.parse(code)
        
        if compilation_target_name is None:
            if not tree.body:
                raise ValueError("Der Code-Block ist leer.")
            
            last_node = tree.body[-1]
            if isinstance(last_node, ast.Expr):
                tree.body.pop()
                exec(compile(tree, filename="<ast>", mode="exec"), namespace)
                target_value = eval(compile(ast.Expression(last_node.value), filename="<ast>", mode="eval"), namespace)
                compilation_target_name = "<unbound expression>"
                target_var = rhombus.Density(target_value)
            else:
                raise ValueError("Es wurde kein 'compile' angegeben und der Code endet nicht mit einer freien Expression.")
        else:
            exec(code, namespace)
            if compilation_target_name not in namespace:
                raise ValueError(f"Variable `{compilation_target_name}` is not defined.")
            target_var = rhombus.Density(namespace[compilation_target_name])
            
        print(f"[Worker] Compiling `{compilation_target_name}`...", flush=True)
        files = target_var.compile()
        print("[Worker] Compiled.", flush=True)
        
        # Wir müssen die Dateien hier im Worker encoden, da BeetFile Objekte evtl. 
        # nicht sicher durch die Multiprocessing-Queue gepickled werden können.
        files_data: list[tuple[str, str]] = []
        include_registries = True if len(set(identifier for identifier, _ in files)) != len(files) else False

        for identifier, beet_file in files:
            content_str = beet_file.encoder(beet_file.data)
            filename = ("_".join(beet_file.scope) + "__" if include_registries else "") + identifier.replace(':', '_').replace('/', '_') + '.json'
            files_data.append((filename, content_str))
            
        print("[Worker] Putting results in queue...", flush=True)
        result_queue.put({"success": files_data})
        print("[Worker] Done.", flush=True)
        
    except Exception as e:
        import traceback
        error_trace = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        print(f"[Worker] ERROR: {type(e).__name__}", file=sys.stderr, flush=True)
        result_queue.put({"error": error_trace})

def compile_density(code: str, compilation_target_name: str | None = None) -> list[tuple[str, str]]:
    """
    Zentrales Interface für die Sandbox.
    Nimmt den User-Code und den Ziel-Variablennamen, führt ihn sicher in einem Subprozess aus
    und gibt eine Liste von (Dateiname, Datei_Inhalt_String) zurück.
    """
    queue = multiprocessing.Queue()
    
    # target darf kein Lambda sein, sonst crasht multiprocessing auf Windows beim Start!
    process = multiprocessing.Process(target=_compile_worker, args=(code, compilation_target_name, queue))
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


#======// Discord Interface //===================================================================//

async def process_compile_request(message: str, reply_func):
    """Parsen der Discord Nachricht und Aufruf der Sandbox."""
    match = re.search(r'compile\s+`?([a-zA-Z0-9_]+)`?', message, re.IGNORECASE)
    compilation_target_name = match.group(1) if match else None

    if not (code_blocks := re.findall(r'```(?:python|py)?\n(.*?)\n```', message, re.DOTALL)):
        raise ValueError("No Python code blocks found.")

    code = "\n".join(code_blocks)
        
    # Rufe nun das neue saubere Interface auf
    compiled_files = compile_density(code, compilation_target_name)
        
    files_to_send: list[discord.File] = []
    for filename, content_str in compiled_files:
        files_to_send.append(discord.File(fp=io.BytesIO(content_str.encode('utf-8')), filename=filename))
        
    if not files_to_send:
        raise ValueError("Die `compile()` Methode hat keine Dateien zurückgegeben.")

    await reply_func("", files=files_to_send)


def setup(client: RhombusClient):

    async def handle_compile_requests(message: discord.Message):
        if message.author.bot:
            return
        
        if client.user in message.mentions:

            if "```" not in message.content:
                return
            
            async def response(text: str, files: list[discord.File]=None):
                if (existing_reply := MESSAGE_CACHE.get(message.id)):
                    await existing_reply.edit(content=text, attachments=files if files else [])
                    return
                
                if files:
                    reply = await message.reply(content=text, files=files, mention_author=False, silent=True)
                else:
                    reply = await message.reply(content=text, mention_author=False, silent=True)

                MESSAGE_CACHE[message.id] = reply
            
            try:
                async with message.channel.typing():
                    await process_compile_request(message.content, response)

            except CompilationSandboxError as e:
                error_trace = str(e)
                if len(error_trace) > 1800:
                    error_trace = error_trace[-1800:]
                msg = f"## Compilation failed: (`{e.__class__.__name__}`)\n```python\n{error_trace}\n```\n-# You can edit {message.jump_url} to fix the error and re-run the compilation."
                await response(msg)
                
            except Exception as e:
                raise e

    @client.event
    async def on_message(message: discord.Message):
        await handle_compile_requests(message)

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        await handle_compile_requests(after)
