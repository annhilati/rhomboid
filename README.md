# Rhomboid

A Discord bot to compile density functions written in Rhombus - The Python-embedded Domain-specific Language for Minecraft Terrain Generation - inside of Discord.

Invite it to a Discord server or add it to your personal apps [here](https://discord.com/oauth2/authorize?client_id=1523973266006347897).

## Usage

### Compile Density Functions

1. Send a message containing Python code blocks that has an unbound expression of type `Density` at the bottom.
2. Issue the compilation:
   - The message itself contains a ping to the bot
   - Reply to the message with a ping to the bot
   - Use the context menu: Right click the message and choose `Compile Density` of the app's commands

- Editing the message with the code blocks re-issues compilation
- Reacting to a message of the bot with the waste bin emoji will remove the message if you were the trigger for the message.