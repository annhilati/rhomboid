import discord
from discord import app_commands
import os
import importlib.metadata
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

class RhombusClient(discord.Client):
    def __init__(self):
        super().__init__(
            intents=intents, 
            allowed_mentions=discord.AllowedMentions(replied_user=False)
        )
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # Load our modules (without Cogs)
        from modules import error_handler, rhombus_tester
        error_handler.setup(self)
        rhombus_tester.setup(self)

        await self.tree.sync()

# Create the Bot instance
client = RhombusClient()

@client.event
async def on_ready():
    print(f'Logged in as {client.user.name} (ID: {client.user.id})')
    print('------')
    try:
        rhombus_version = importlib.metadata.version("rhombus")
        activity = discord.Activity(type=discord.ActivityType.playing, name=f"Running Rhombus v{rhombus_version}")
        await client.change_presence(activity=activity)
        print(f"Status set to: Rhombus v{rhombus_version}")
    except Exception as e:
        print(f"Could not set Rhombus version in status: {e}")

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if token:
        client.run(token)
    else:
        print("Error: DISCORD_TOKEN not found in environment.")
