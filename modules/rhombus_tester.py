from __future__ import annotations
from typing import Any, TYPE_CHECKING, Literal
import re, io

import discord
import discord.app_commands as app_commands

import rhombus
from rhombus.core import BeetFile

from .sandbox.runner import compile_density, CompilationSandboxError

if TYPE_CHECKING:
    from main import RhombusClient


import os, json

CACHE_FILE = "message_cache.json"

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f: 
                return json.load(f)
        except Exception:
            pass
    return {}

MESSAGE_CACHE = load_cache()

def save_cache():
    # Behalte maximal die letzten 1000 Einträge, damit die Datei nicht unendlich wächst
    if len(MESSAGE_CACHE) > 1000:
        for k in list(MESSAGE_CACHE.keys())[:-1000]:
            del MESSAGE_CACHE[k]
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(MESSAGE_CACHE, f)

"""Here we cache the bot's replies to messages of users (stored in a JSON file), so we can
allow the Bot correcting itself when the user corrects his message, even after restarts."""



#======// Discord Interface //===================================================================//

async def process_compile_request(code_text: str, compilation_target_name: str | None, reply_func):
    """Parsen der Discord Nachricht und Aufruf der Sandbox."""
    if not (code_blocks := re.findall(r'```(?:python|py)\n(.*?)\n```', code_text, re.IGNORECASE | re.DOTALL)):
        raise ValueError("Es wurden keine Python Code-Blöcke (```py oder ```python) gefunden.")

    # Übergebe die Blöcke einzeln an den Compiler für besseres Error-Logging
    compiled_files = compile_density(code_blocks, compilation_target_name)
        
    files_to_send: list[discord.File] = []
    for filename, content_str in compiled_files:
        files_to_send.append(discord.File(fp=io.BytesIO(content_str.encode('utf-8')), filename=filename))
        
    if not files_to_send:
        raise ValueError("Die `compile()` Methode hat keine Dateien zurückgegeben.")

    await reply_func("", files=files_to_send)


def setup(client: RhombusClient):

    async def handle_potential_compilation_request_message(message: discord.Message):
        if message.author.bot:
            return
        
        is_cached = str(message.id) in MESSAGE_CACHE
        
        # Reagiere, wenn der Bot gepingt wurde ODER die Nachricht bereits kompiliert wurde
        if client.user in message.mentions or is_cached:

            target_msg = message
            command_text = message.content
            
            cached_target_name = None
            if is_cached:
                cached_target_name = MESSAGE_CACHE[str(message.id)].get("target_name")
            
            if "```py" not in command_text.lower():
                # Prüfe, ob es eine Antwort auf eine andere Nachricht ist
                if message.reference and message.reference.message_id:
                    try:
                        ref_msg = message.reference.resolved
                        if not isinstance(ref_msg, discord.Message):
                            ref_msg = await message.channel.fetch_message(message.reference.message_id)
                        
                        if "```py" in ref_msg.content.lower():
                            target_msg = ref_msg
                        else:
                            return
                    except Exception:
                        return
                else:
                    return
            
            match = re.search(r'compile\s+`?([a-zA-Z0-9_]+)`?', command_text, re.IGNORECASE)
            compilation_target_name = match.group(1) if match else cached_target_name

            async def response(text: str, files: list[discord.File]=None):
                reply_info = MESSAGE_CACHE.get(str(target_msg.id))
                if reply_info:
                    try:
                        existing_reply = await target_msg.channel.fetch_message(reply_info["reply_id"])
                        await existing_reply.edit(content=text, attachments=files if files else [])
                        return
                    except discord.NotFound:
                        pass
                
                if files:
                    reply = await target_msg.reply(content=text, files=files, mention_author=False, silent=True)
                else:
                    reply = await target_msg.reply(content=text, mention_author=False, silent=True)

                MESSAGE_CACHE[str(target_msg.id)] = {
                    "reply_id": reply.id,
                    "target_name": compilation_target_name
                }
                save_cache()
            
            try:
                async with target_msg.channel.typing():
                    await process_compile_request(target_msg.content, compilation_target_name, response)

            except CompilationSandboxError as e:
                error_trace = str(e)
                if len(error_trace) > 1700:
                    error_trace = "..." + error_trace[-1697:]
                msg = f"## Compilation failed: (`{e.__class__.__name__}`)\n```python\n{error_trace}\n```\n-# You can edit [the message]({target_msg.jump_url}) to fix the error and re-run the compilation."
                await response(msg)
                
            except Exception as e:
                raise e

    @client.tree.context_menu(name="Compile Density")
    async def compile_context_menu(interaction: discord.Interaction, message: discord.Message):
        if not message.content or "```" not in message.content:
            await interaction.response.send_message("Diese Nachricht enthält keinen Code-Block.", ephemeral=True)
            return
            
        # Wir deferren ephemeral, damit der Nutzer sieht, dass etwas passiert, 
        # die echte Antwort aber als normale Nachricht kommt (die bearbeitbar bleibt)
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        async def response(text: str, files: list[discord.File]=None):
            # Wir nutzen exakt dieselbe Logik wie beim Ping, um eine normale Nachricht zu senden!
            reply_info = MESSAGE_CACHE.get(str(message.id))
            if reply_info:
                try:
                    existing_reply = await message.channel.fetch_message(reply_info["reply_id"])
                    await existing_reply.edit(content=text, attachments=files if files else [])
                    return
                except discord.NotFound:
                    pass
            
            if files:
                reply = await message.reply(content=text, files=files, mention_author=False, silent=True)
            else:
                reply = await message.reply(content=text, mention_author=False, silent=True)

            MESSAGE_CACHE[str(message.id)] = {
                "reply_id": reply.id,
                "target_name": None
            }
            save_cache()
            
            # Schließe die ursprüngliche Interaktion ab
            try:
                await interaction.edit_original_response(content="✅ Kompilierung ausgeführt!")
            except discord.NotFound:
                pass
            
        try:
            await process_compile_request(message.content, None, response)
        except CompilationSandboxError as e:
            error_trace = str(e)
            if len(error_trace) > 1700:
                error_trace = "..." + error_trace[-1697:]
            msg = f"## Compilation failed: (`{e.__class__.__name__}`)\n```python\n{error_trace}\n```\n-# You can edit [the message]({message.jump_url}) to fix the error and re-run the compilation."
            await response(msg)
            
        except Exception as e:
            raise e

    @client.event
    async def on_message(message: discord.Message):
        await handle_potential_compilation_request_message(message)

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        await handle_potential_compilation_request_message(after)
