from __future__ import annotations
from typing import TYPE_CHECKING
import traceback, sys

import discord
import discord.app_commands as app_commands

if TYPE_CHECKING:
    from main import RhombusClient


async def send_error_message(ctx: discord.Interaction | discord.Message | discord.Webhook, error: Exception):
    """Helper method to format and send errors back as a Discord message."""

    msg = ""

    embed = discord.Embed(
        title="Unhandled Error",
        description=f"# {error.__class__.__name__}\n{error.args[0]}",
        color=discord.Color.red()
    )

    try:
        if isinstance(ctx, discord.Message):
            await ctx.reply(embed=embed, mention_author=False, silent=True)
        elif isinstance(ctx, discord.Webhook):
            await ctx.send(embed=embed, ephermal=True)
        elif isinstance(ctx, discord.Interaction):
            if ctx.response.is_done():
                await ctx.followup.send(embed=embed, ephermal=True)
            else:
                await ctx.response.send_message(embed=embed, ephermal=True)

    except Exception as e:
        print(f"Could not send error message to Discord: {e}", file=sys.stderr)

def setup(client: RhombusClient):
    @client.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        original_error = getattr(error, "original", error)
        await send_error_message(interaction, original_error)

    @client.event
    async def on_error(event_method: str, *args, **kwargs):
        error_type, error, tb = sys.exc_info()
        if error is None:
            return

        target = None
        if event_method == "on_message" and len(args) > 0 and isinstance(args[0], discord.Message):
            target = args[0]
        elif event_method == "on_message_edit" and len(args) > 1 and isinstance(args[1], discord.Message):
            target = args[1]
        
        if target:
            await send_error_message(target, error)
        else:
            print(f"Unhandled error in event {event_method}:", file=sys.stderr)
            traceback.print_exc()
