from __future__ import annotations
from typing import TYPE_CHECKING
import re, io, os, json

import discord
import discord.app_commands as app_commands

from .sandbox.runner import compile_density, CompilationSandboxError

if TYPE_CHECKING:
    from main import RhombusClient


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
    """Parse the Discord message and invoke the sandbox."""
    if not (code_blocks := re.findall(r'```(?:python|py)\n(.*?)\n```', code_text, re.IGNORECASE | re.DOTALL)):
        raise ValueError("No Python code blocks (```py or ```python) found.")

    # Pass the blocks individually to the compiler for better error logging
    compiled_files = compile_density(code_blocks, compilation_target_name)
        
    files_to_send: list[discord.File] = []
    for filename, content_str in compiled_files:
        files_to_send.append(discord.File(fp=io.BytesIO(content_str.encode('utf-8')), filename=filename))
        
    if not files_to_send:
        raise ValueError("The `compile()` method did not return any files.")

    await reply_func("", files=files_to_send)


def setup(client: RhombusClient):

    async def handle_potential_compilation_request_message(message: discord.Message):
        if message.author.bot:
            return
        
        is_cached = str(message.id) in MESSAGE_CACHE
        
        # React if the bot was pinged OR the message was already compiled
        if client.user in message.mentions or is_cached:

            target_msg = message
            command_text = message.content
            
            cached_target_name = None
            if is_cached:
                cached_target_name = MESSAGE_CACHE[str(message.id)].get("target_name")
            
            if "```py" not in command_text.lower():
                # Check if it is a reply to another message
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
                msg = f"## Compilation failed\n```python\n{error_trace}\n```\n-# Edit [the message]({target_msg.jump_url}) to fix the error and re-run the compilation."
                await response(msg)
                
            except Exception as e:
                raise e

    @client.tree.context_menu(name="Compile Density")
    async def compile_context_menu(interaction: discord.Interaction, message: discord.Message):
        if not message.content or "```" not in message.content:
            await interaction.response.send_message("This message does not contain a code block.", ephemeral=True)
            return
            
        # We always answer publicly. Since we use edit_original_response,
        # this is also allowed for User Apps! (403 Forbidden only occurred with message.reply).
        await interaction.response.defer(ephemeral=False, thinking=True)
        
        async def response(text: str, files: list[discord.File]=None):
            if files:
                await interaction.edit_original_response(content=text, attachments=files)
            else:
                await interaction.edit_original_response(content=text)
                
            try:
                # Fetch the sent message to store it in the cache
                reply = await interaction.original_response()
                MESSAGE_CACHE[str(message.id)] = {
                    "reply_id": reply.id,
                    "target_name": None
                }
                save_cache()
            except Exception:
                pass
            
        try:
            await process_compile_request(message.content, None, response)
        except (CompilationSandboxError, ValueError) as e:
            error_trace = str(e)
            if len(error_trace) > 1700:
                error_trace = "..." + error_trace[-1697:]
            msg = f"## Compilation failed\n```python\n{error_trace}\n```\n-# Edit [the message]({message.jump_url}) to fix the error and re-run the compilation."
            await response(msg)
            
        except Exception as e:
            raise e

    @client.event
    async def on_message(message: discord.Message):
        await handle_potential_compilation_request_message(message)

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        await handle_potential_compilation_request_message(after)
        
    @client.event
    async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
        # Wenn die Nachricht nicht im internen Cache war, wird on_message_edit nicht aufgerufen.
        # on_raw_message_edit fängt diese Fälle (z.B. nach einem Neustart) ab!
        if payload.cached_message is not None:
            return  # Wird bereits von on_message_edit behandelt
            
        # Wir reagieren nur, wenn die Nachricht in unserem eigenen Cache ist (also bearbeitet werden soll)
        # oder wenn es potenziell ein Code-Block ist. 
        if str(payload.message_id) in MESSAGE_CACHE or (payload.data and 'content' in payload.data and '```' in payload.data['content']):
            try:
                channel = client.get_channel(payload.channel_id) or await client.fetch_channel(payload.channel_id)
                if channel:
                    message = await channel.fetch_message(payload.message_id)
                    await handle_potential_compilation_request_message(message)
            except discord.NotFound:
                pass
            except Exception as e:
                import sys, traceback
                print(f"Fehler beim Fetchen der Raw-Message {payload.message_id}:", file=sys.stderr)
                traceback.print_exc()
