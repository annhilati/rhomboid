import discord
from discord import app_commands
import os
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
        # Lade unsere Module (ohne Cogs)
        from modules import error_handler, rhombus_tester
        error_handler.setup(self)
        rhombus_tester.setup(self)

        await self.tree.sync()

# Erstelle die Bot-Instanz
client = RhombusClient()

@client.event
async def on_ready():
    print(f'Eingeloggt als {client.user.name} (ID: {client.user.id})')
    print('------')

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if token:
        client.run(token)
    else:
        print("Fehler: DISCORD_TOKEN nicht in der Umgebung gefunden.")
