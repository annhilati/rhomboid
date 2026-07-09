from __future__ import annotations
from typing import Any, TYPE_CHECKING, Literal
import re, io

import discord
import discord.app_commands as app_commands

import rhombus
from rhombus.core import BeetFile

from ._rhombus_sandbox import compile_density, CompilationSandboxError

if TYPE_CHECKING:
    from main import RhombusClient


MESSAGE_CACHE: dict[int, discord.Message] = {}
"""Here we cache the bot's replies to messages of users, that issued something, so we can
allow the Bot correcting itself when the user corrects his message."""



#======// Discord Interface //===================================================================//

async def process_compile_request(message: str, reply_func):
    """Parsen der Discord Nachricht und Aufruf der Sandbox."""
    match = re.search(r'compile\s+`?([a-zA-Z0-9_]+)`?', message, re.IGNORECASE)
    compilation_target_name = match.group(1) if match else None

    if not (code_blocks := re.findall(r'```(?:python|py)\n(.*?)\n```', message, re.IGNORECASE | re.DOTALL)):
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

    async def handle_compile_requests(message: discord.Message):
        if message.author.bot:
            return
        
        # Reagiere, wenn der Bot gepingt wurde ODER die Nachricht bereits kompiliert wurde
        if client.user in message.mentions or message.id in MESSAGE_CACHE:

            if "```py" not in message.content.lower():
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
                msg = f"## Compilation failed: (`{e.__class__.__name__}`)\n```python\n{error_trace}\n```\n-# You can edit [the message]({message.jump_url}) to fix the error and re-run the compilation."
                await response(msg)
                
            except Exception as e:
                raise e

    @client.tree.context_menu(name="Compile Density")
    async def compile_context_menu(interaction: discord.Interaction, message: discord.Message):
        if not message.content or "```" not in message.content:
            await interaction.response.send_message("Diese Nachricht enthält keinen Code-Block.", ephemeral=True)
            return
            
        await interaction.response.defer(thinking=True)
        
        async def response(text: str, files: list[discord.File]=None):
            kwargs = {"content": text}
            if files is not None:
                kwargs["attachments"] = files
            else:
                kwargs["attachments"] = []
            await interaction.edit_original_response(**kwargs)
            
            try:
                MESSAGE_CACHE[message.id] = await interaction.original_response()
            except discord.NotFound:
                pass
            
        try:
            await process_compile_request(message.content, response)
        except CompilationSandboxError as e:
            error_trace = str(e)
            if len(error_trace) > 1800:
                error_trace = error_trace[-1800:]
            msg = f"## Compilation failed: (`{e.__class__.__name__}`)\n```python\n{error_trace}\n```\n-# You can edit [the message]({message.jump_url}) to fix the error and re-run the compilation."
            await response(msg)
            
        except Exception as e:
            raise e

    @client.event
    async def on_message(message: discord.Message):
        await handle_compile_requests(message)

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        await handle_compile_requests(after)
