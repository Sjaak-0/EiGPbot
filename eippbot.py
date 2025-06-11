import discord
import os
import json
import asyncio
from discord.ext import commands
from flask import Flask
from threading import Thread
import random
import time
import aiohttp
import urllib.parse

with open('token.txt', 'r') as file:
    TOKEN = file.read().strip()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = commands.Bot(command_prefix="$", intents=intents)

app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

server_config = {}

def load_config():
    global server_config
    if not os.path.exists('config.json'):
        with open('config.json', 'w') as file:
            json.dump({}, file)  
    with open('config.json', 'r') as file:
        try:
            server_config = json.load(file)  
        except json.JSONDecodeError:
            print("Config file is empty or invalid. Initializing with default values.")
            server_config = {}

def save_config():
    print(f"Saving config.")
    with open('config.json', 'w') as file:
        json.dump(server_config, file, indent=4)

@client.event
async def on_ready():
    load_config()
    await client.add_cog(SoupSweeper(client)) 
    print(f'Logged in as {client.user}')

    channel = client.get_channel(1358470170191986842)
    if channel:
        await channel.send(f'EippBot is now online! Or am I?')
    else:
        print("❗ Could not find the channel with ID 1358470170191986842.")

@client.command()
@commands.is_owner() 
async def shutdown(ctx):
    channel = client.get_channel(1358470170191986842)
    if channel:
        await channel.send("EippBot shutting down...")
    await client.close()

@client.command(name='permission')
async def permission(ctx):
    bot_member = ctx.guild.me 
    permissions = bot_member.guild_permissions

    perms_list = [f"✅ {name.replace('_', ' ').title()}" if value else f"❌ {name.replace('_', ' ').title()}"
                  for name, value in permissions]

    perms_chunks = [perms_list[i:i + 10] for i in range(0, len(perms_list), 10)] 
    embed = discord.Embed(title=f"Permissions for {bot_member.display_name} in **{ctx.guild.name}**", color=0x7289DA)

    for i, chunk in enumerate(perms_chunks):
        embed.add_field(name=f"Permissions Part {i + 1}", value="\n".join(chunk), inline=False)

    await ctx.send(embed=embed)

@client.command(name="test", help="Test command.")
async def test(ctx):
    await ctx.send("Test deez nuts lmao.")

@client.command(name="setcategory", help="Set the confessional category. (Admin only)")
@commands.has_permissions(administrator=True)
async def setcategory(ctx, category_id: int):
    server_id = str(ctx.guild.id)
    if server_id not in server_config:
        server_config[server_id] = {}
        server_config[server_id]['server_name'] = ctx.guild.name
    server_config[server_id]['category_id'] = category_id
    save_config()
    await ctx.send(f"Confessional category set to {category_id}.")

@client.command(name="setrole", help="Set a specific role. (Admin only)")
@commands.has_permissions(administrator=True)
async def setrole(ctx, role_name: str, role_id: int):
    allowed_roles = ["host", "player", "spectator", "eliminated", "bot"]
    
    role_name = role_name.lower()
    
    if role_name not in allowed_roles:
        await ctx.send(f"Invalid role name. Only the following roles are allowed: {', '.join(allowed_roles)}")
        return
    
    server_id = str(ctx.guild.id)
    config_key = role_name + "_role"
    
    if server_id not in server_config:
        server_config[server_id] = {}
        server_config[server_id]['server_name'] = ctx.guild.name
    
    server_config[server_id][config_key] = role_id
    save_config()
    await ctx.send(f"{role_name.capitalize()} role set to {role_id}.")

@client.command(name="confessional", help="Creates a confessional channel for a specified user.")
@commands.has_guild_permissions(administrator=True)
async def confessional(ctx, user: discord.Member):
    server_id = str(ctx.guild.id)
    if server_id not in server_config:
        await ctx.send("Server configuration is missing. Please set the necessary roles and category first.")
        return

    required_settings = ['host_role', 'category_id', 'bot_role', 'player_role', 'spectator_role']
    missing_config = [key for key in required_settings if key not in server_config[server_id]]
    if missing_config:
        await ctx.send(f"Missing configuration for: {', '.join(missing_config)}.")
        return

    host_role_id = server_config[server_id]["host_role"]
    category_id = server_config[server_id]["category_id"]
    bot_role_id = server_config[server_id]["bot_role"]
    player_role_id = server_config[server_id]["player_role"]
    spectator_role_id = server_config[server_id]["spectator_role"]
    
    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)
    if host_role not in ctx.author.roles:
        await ctx.send("You do not have permission to use this command.")
        return

    try:
        category = discord.utils.get(ctx.guild.categories, id=category_id)
        existing_channel = discord.utils.get(category.channels, name=user.name)

        if existing_channel:
            await ctx.send(f"{user.mention} already has a confessional channel: {existing_channel.mention}.")
            return

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            host_role: discord.PermissionOverwrite.from_pair(discord.Permissions.all(), discord.Permissions.none()),
            discord.utils.get(ctx.guild.roles, id=bot_role_id): discord.PermissionOverwrite.from_pair(discord.Permissions.all(), discord.Permissions.none()),
            discord.utils.get(ctx.guild.roles, id=spectator_role_id): discord.PermissionOverwrite(read_messages=False, send_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True),
            discord.utils.get(ctx.guild.roles, id=player_role_id): discord.PermissionOverwrite(read_messages=False, send_messages=False),
        }

        channel = await category.create_text_channel(name=user.name, overwrites=overwrites)
        await ctx.send(f"Confessional channel created for {user.mention}.")

        role_to_add = ctx.guild.get_role(player_role_id)
        try:
            await user.add_roles(role_to_add)
            await ctx.send(f"Player role has been added to {user.mention}.")
        except discord.Forbidden:
            await ctx.send("I do not have permission to assign that role. Perhaps check that the Bot role is higher than the other roles?")
        except Exception as e:
            await ctx.send(f"Failed to add role: {e}")


    except discord.Forbidden:
        await ctx.send("I do not have permission to create channels.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

with open('config.json', 'r') as f:
    config = json.load(f)

cooldowns = {}

@client.command(name="roll", help="Rolls a random number between 1 and the specified number.")
@commands.has_guild_permissions(send_messages=True)
async def roll(ctx, number: int):
    try:
        guild_id = str(ctx.guild.id)
        server_config = config.get(guild_id)

        if not server_config:
            await ctx.send("Server configuration not found.")
            return

        host_role_id = server_config.get("host_role")

        if number <= 0:
            await ctx.send("Please provide a positive integer.")
            return

        host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)
        if host_role in ctx.author.roles:
            roll_result = random.randint(1, number)

            embed = discord.Embed(
                title="🎲 Roll Result 🎲",
                description=f"You rolled a **{roll_result}** (1-{number}).",
                color=0xf5a9b8  
            )
            await ctx.send(embed=embed)
        else:
            user_id = ctx.author.id
            current_time = time.time()

            if user_id in cooldowns and current_time - cooldowns[user_id] < 300:
                remaining_time = int(300 - (current_time - cooldowns[user_id]))
                await ctx.send(f"Please wait {remaining_time} seconds before using this command again.")
                return

            cooldowns[user_id] = current_time

            roll_result = random.randint(1, number)

            embed = discord.Embed(
                title="🎲 Roll Result 🎲",
                description=f"You rolled a **{roll_result}** (1-{number}).",
                color=0xf5a9b8  
            )
            await ctx.send(embed=embed)

    except ValueError:
        await ctx.send("Please provide a valid integer.")
    except commands.MissingRequiredArgument:
        await ctx.send("Please specify a number to roll.")

@client.command(name="multihit", help="Simulates multiple hit moves with accuracy and optional flinch chance.")
@commands.has_guild_permissions(send_messages=True)
async def multihit(ctx, hits: int, accuracy: int, flinch_chance: int = 0):
    if hits <= 0 or hits > 10:
        await ctx.send("Please enter a number of hits between 1 and 10.")
        return
    if accuracy <= 0 or accuracy > 100:
        await ctx.send("Please enter an accuracy between 1 and 100.")
        return
    if flinch_chance < 0 or flinch_chance > 100:
        await ctx.send("Please enter a flinch chance between 0 and 100.")
        return

    guild_id = str(ctx.guild.id)
    server_config = config.get(guild_id)

    if not server_config:
        await ctx.send("Server configuration not found.")
        return

    host_role_id = server_config.get("host_role")
    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)

    is_host = host_role in ctx.author.roles
    user_id = ctx.author.id
    current_time = time.time()

    if not is_host:
        if user_id in cooldowns and current_time - cooldowns[user_id] < 300:
            remaining = int(300 - (current_time - cooldowns[user_id]))
            await ctx.send(f"Please wait {remaining} seconds before using this command again.")
            return
        cooldowns[user_id] = current_time

    results = []
    flinch_occurred = False
    successful_hits = 0

    for i in range(hits):
        hit_roll = random.randint(1, 100)
        if hit_roll > accuracy:
            results.append(f"Roll {i + 1}: **{hit_roll}** (Missed)")
            break

        hit_result = f"Roll {i + 1}: **{hit_roll}**"
        if flinch_chance > 0 and not flinch_occurred:
            flinch_roll = random.randint(1, 100)
            hit_result += f" (Flinch Roll: {flinch_roll})"
            if flinch_roll <= flinch_chance:
                results.append(hit_result)
                results.append("**Flinch!** No further flinch rolls.")
                flinch_occurred = True
            else:
                results.append(hit_result)
        else:
            results.append(hit_result)

        successful_hits += 1

    embed = discord.Embed(
        title="🎯 Multihit Simulation 🎯",
        description="\n".join(results),
        color=0xf5a9b8
    )
    embed.add_field(name="Summary", value=f"Total successful hits: **{successful_hits}**")

    if flinch_occurred:
        embed.add_field(name="Effect", value="The opponent flinched and couldn't move!")

    await ctx.send(embed=embed)

@client.command(name="makeserver", help="Deletes all channels and makes a template eipp server.")
@commands.has_permissions(administrator=True)
async def makeserver(ctx):
    if ctx.author.id != ctx.guild.owner_id:
        await ctx.send("You must be the server owner to use this command.")
        return

    warning_msg = await ctx.send(
        "⚠️ **This will delete all current channels in the server.**\n"
        "Do you wish to proceed? Type `Yes` or `No`."
    )

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["yes", "no"]

    try:
        response = await client.wait_for("message", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        await ctx.send("⏳ Confirmation timed out. Operation cancelled.")
        return

    if response.content.lower() != "yes":
        await ctx.send("❌ Operation cancelled.")
        return

    server = ctx.guild

    try:
        for channel in server.channels:
            await channel.delete()
        for category in server.categories:
            await category.delete()

        roles = {
            "Host": discord.Permissions(administrator=True),
            "Player": discord.Permissions(),
            "Spectator": discord.Permissions(),
            "Eliminated": discord.Permissions(),
            "Bot": discord.Permissions()
        }

        role_ids = {}
        for role_name, perms in roles.items():
            role = await server.create_role(name=role_name, permissions=perms)
            role_ids[role_name.lower()] = role.id

        categories = {
            "Announcements": [
                ("announcements", {
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["host"]: discord.PermissionOverwrite(send_messages=True)
                }),
                ("eipp-rules", {
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["host"]: discord.PermissionOverwrite(send_messages=True)
                }),
                ("bans", {
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["host"]: discord.PermissionOverwrite(send_messages=True)
                }),
                ("twist-info", {
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["host"]: discord.PermissionOverwrite(send_messages=True)
                }),
            ],
            "Text Channels": [
                ("general", {
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    role_ids["player"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["spectator"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["eliminated"]: discord.PermissionOverwrite(read_messages=True, send_messages=False)
                }),
                ("rule-discussion", {
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    role_ids["player"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["spectator"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["eliminated"]: discord.PermissionOverwrite(read_messages=True, send_messages=False)
                }),
            ],
            "Game Chat": [
                ("player-chat", {
                    role_ids["player"]: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    role_ids["spectator"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["eliminated"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False)
                }),
                ("spectator-chat", {
                    role_ids["spectator"]: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    role_ids["player"]: discord.PermissionOverwrite(read_messages=False),
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False)
                }),
                ("graveyard", {
                    role_ids["spectator"]: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    role_ids["eliminated"]: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    role_ids["player"]: discord.PermissionOverwrite(read_messages=False),
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False)
                }),
            ],
            "The Game": [
                ("season-1", {
                    role_ids["host"]: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    role_ids["player"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["spectator"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    role_ids["eliminated"]: discord.PermissionOverwrite(read_messages=True, send_messages=False),
                    server.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False)
                }),
            ],
            "Hosts": [
                ("host-chat", {
                    role_ids["host"]: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    server.default_role: discord.PermissionOverwrite(read_messages=False)
                }),
                ("logs", {
                    role_ids["host"]: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                    server.default_role: discord.PermissionOverwrite(read_messages=False)
                }),
            ],
            "Confessionals": []
        }

        category_ids = {}
        general_channel = None

        for category_name, channels in categories.items():
            category = await server.create_category(category_name)
            category_ids[category_name.lower().replace(" ", "_")] = category.id

            for channel_name, overwrites in channels:
                channel_overwrites = {}

                for role_id, perms in overwrites.items():
                    if role_id == server.default_role:
                        channel_overwrites[server.default_role] = perms
                    else:
                        role = server.get_role(role_id)
                        if role:
                            channel_overwrites[role] = perms

                channel = await category.create_text_channel(channel_name, overwrites=channel_overwrites)

                if channel_name == "general":
                    general_channel = channel

        if general_channel:
            await server.edit(system_channel=general_channel)

        server_config[str(server.id)] = {
            "server_name": server.name,
            "host_role": role_ids["host"],
            "player_role": role_ids["player"],
            "spectator_role": role_ids["spectator"],
            "eliminated_role": role_ids["eliminated"],
            "bot_role": role_ids["bot"],
            "category_id": category_ids.get("confessionals", None)
        }
        save_config()

    except discord.Forbidden:
        await ctx.send("I lack the permissions to create roles or channels.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@client.command(name="opentospecs", help="Opens the current channel to spectators.")
async def opentospecs(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config or 'category_id' not in server_config[server_id]:
        await ctx.send("Category ID is not set for this server. Please configure it first.")
        return

    category_id = server_config[server_id]['category_id']

    if ctx.channel.category_id != category_id:
        await ctx.send("This command can only be used in channels under the specified category.")
        return

    spectator_role_id = server_config[server_id].get('spectator_role')
    if not spectator_role_id:
        await ctx.send("Spectator role is not set for this server. Please configure it first.")
        return

    spectator_role = discord.utils.get(ctx.guild.roles, id=spectator_role_id)
    if not spectator_role:
        await ctx.send("The spectator role is missing or invalid.")
        return

    try:
        await ctx.channel.set_permissions(spectator_role, read_messages=True)
        await ctx.send(f"Spectators can now view this channel: {ctx.channel.mention}")
    except discord.Forbidden:
        await ctx.send("I lack the permissions to modify channel settings.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@client.command(name="uploademotes", help="Upload emotes by attaching images.")
@commands.has_permissions(administrator=True)
async def uploademotes(ctx):
    if not ctx.message.attachments:
        await ctx.send("Please attach images to upload as emotes.")
        return

    for attachment in ctx.message.attachments:
        if not attachment.filename.lower().endswith(('png', 'jpg', 'jpeg', 'gif')):
            await ctx.send(f"{attachment.filename} is not a supported image file.")
            continue

        emote_name = attachment.filename.split('.')[0][:32].replace(" ", "_")

        try:
            img_data = await attachment.read()
            emote = await ctx.guild.create_custom_emoji(name=emote_name, image=img_data)
            await ctx.send(f"Uploaded emote: {emote_name} ({emote})")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to upload `{emote_name}`: {str(e)}")

    await ctx.send("Finished uploading emotes.")

@client.command(name="close", help="Removes all game related roles to close off a season.")
@commands.has_permissions(administrator=True)
async def close(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config:
        await ctx.send("Server configuration not found. Please run the setup commands first.")
        return

    role_keys = ["player_role", "eliminated_role", "spectator_role"]
    roles_to_remove = [
        discord.utils.get(ctx.guild.roles, id=server_config[server_id].get(key))
        for key in role_keys
    ]

    if not all(roles_to_remove):
        missing_roles = [
            key for key, role in zip(role_keys, roles_to_remove) if role is None
        ]
        await ctx.send(
            f"One or more roles are missing in the server configuration: {', '.join(missing_roles)}."
        )
        return
    await ctx.send("Removing Player, Spectator and Eliminated roles from all server members. This may take a moment.")

    removed_count = 0

    try:
        for member in ctx.guild.members:
            roles_to_remove_from_member = [
                role for role in roles_to_remove if role in member.roles
            ]
            if roles_to_remove_from_member:
                await member.remove_roles(*roles_to_remove_from_member)
                removed_count += len(roles_to_remove_from_member)

        await ctx.send(
            f"Game over! A total of {removed_count} roles have been removed from members."
        )

    except discord.Forbidden:
        await ctx.send("I lack the permissions to modify roles for some members.")
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}")

@client.command(name="deleteconfessionals", help="Deletes all confessional channels in the category. Requires host role. Prompts for confirmation.")
async def deleteconfessionals(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config:
        await ctx.send("Server configuration not found.")
        return

    if 'host_role' not in server_config[server_id] or 'category_id' not in server_config[server_id]:
        await ctx.send("Host role or category ID not set for this server. Please configure them first.")
        return

    host_role_id = server_config[server_id]['host_role']
    category_id = server_config[server_id]['category_id']

    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)
    if host_role not in ctx.author.roles:
        await ctx.send("You do not have permission to use this command. Host role required.")
        return

    await ctx.send("Are you sure you want to delete all confessionals? Type 'Yes' to confirm.")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'yes'

    try:
        msg = await client.wait_for('message', check=check, timeout=30)  

    except asyncio.TimeoutError:
        await ctx.send("Deletion cancelled: Confirmation timeout.")
        return

    if msg.content.lower() == 'yes':
        await ctx.send("Deleting confessionals...")
        category = discord.utils.get(ctx.guild.categories, id=category_id)

        if category is None:
            await ctx.send("Confessionals category not found.")
            return

        try:
            for channel in category.channels:
                await channel.delete()
            await ctx.send("All confessionals have been deleted.")

        except discord.Forbidden:
            await ctx.send("I do not have permission to delete channels in this category.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
    else:
        await ctx.send("Deletion cancelled.")

@client.command(name="playerlist", help="Lists all players with the player role, randomized, and mentions them. Host role required.")
async def playerlist(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config:
        await ctx.send("Server configuration not found.")
        return

    if 'host_role' not in server_config[server_id] or 'player_role' not in server_config[server_id]:
        await ctx.send("Host role or player role not set for this server. Please configure them first.")
        return

    host_role_id = server_config[server_id]['host_role']
    player_role_id = server_config[server_id]['player_role']

    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)
    if host_role not in ctx.author.roles:
        await ctx.send("You do not have permission to use this command. Host role required.")
        return

    player_role = discord.utils.get(ctx.guild.roles, id=player_role_id)
    if player_role is None:
        await ctx.send("Player role not found.")
        return

    players = [member for member in ctx.guild.members if player_role in member.roles]

    if not players:
        await ctx.send("No players with the player role found. I guess no one is fighting a gorilla then.")
        return

    random.shuffle(players)

    message = "Here's some of the 100 people I nominate to fight 1 gorilla:\n"
    message += "\n".join([member.mention for member in players])

    await ctx.send(message)

@client.command(name="updateplayerlist", help="Updates the last posted player list by the bot.")
async def updateplayerlist(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config:
        await ctx.send("Server configuration not found.")
        return

    if 'host_role' not in server_config[server_id] or 'player_role' not in server_config[server_id]:
        await ctx.send("Host role or player role not set for this server. Please configure them first.")
        return

    host_role_id = server_config[server_id]['host_role']
    player_role_id = server_config[server_id]['player_role']

    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)
    if host_role not in ctx.author.roles:
        await ctx.send("You do not have permission to use this command. Host role required.")
        return

    player_role = discord.utils.get(ctx.guild.roles, id=player_role_id)
    if player_role is None:
        await ctx.send("Player role not found.")
        return

    players = [member for member in ctx.guild.members if player_role in member.roles]

    if not players:
        await ctx.send("No players with the player role found.")
        return

    random.shuffle(players)

    updated_message = "Players:\n"
    updated_message += "\n".join([member.mention for member in players])

    async for message in ctx.channel.history(limit=100):
        if message.author == client.user and message.content.startswith("Players:"):
            await message.edit(content=updated_message)
            await ctx.send("Player list has been updated.", delete_after=10)
            return

    await ctx.send("No previous player list message found to update.")

@client.command(name="addspecs", help="Adds the spectator role to all members without the player role. Host role required.")
async def addspecs(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config:
        await ctx.send("Server configuration not found.")
        return

    if 'host_role' not in server_config[server_id] or 'player_role' not in server_config[server_id] or 'spectator_role' not in server_config[server_id]:
        await ctx.send("Host role, player role, or spectator role not set for this server. Please configure them first.")
        return

    host_role_id = server_config[server_id]['host_role']
    player_role_id = server_config[server_id]['player_role']
    spectator_role_id = server_config[server_id]['spectator_role']

    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)
    if host_role not in ctx.author.roles:
        await ctx.send("You do not have permission to use this command. Host role required.")
        return

    player_role = discord.utils.get(ctx.guild.roles, id=player_role_id)
    spectator_role = discord.utils.get(ctx.guild.roles, id=spectator_role_id)

    if player_role is None or spectator_role is None:
        await ctx.send("Player role or spectator role not found.")
        return

    members_to_update = []
    for member in ctx.guild.members:
        if player_role not in member.roles and host_role not in member.roles:
            members_to_update.append(member)

    if not members_to_update:
        await ctx.send("No eligible members found to receive the spectator role.")
        return

    await ctx.send(f"Adding spectator role to {len(members_to_update)} members. This may take a moment...")

    try:
        for member in members_to_update:
            await member.add_roles(spectator_role)
        await ctx.send("Spectator role added to all eligible members.")
    except discord.Forbidden:
        await ctx.send("I do not have permission to add roles to members. Check if the Bot role is higher than Player and Spectator roles.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


@client.command(name="soup")
async def soup(ctx):
    await ctx.send("Soup time!")
    return

@client.command(name="edward")
async def edward(ctx):
    await ctx.send("https://cdn.discordapp.com/emojis/1334416241317646438.webp?size=128")
    return

@client.command(name="earthquake")
async def earthquake(ctx):
    await ctx.send("KO! Saberslasher11 eliminated with Blaziken.")
    return

@client.command(name="IPAddress", help="Generates a fake IP address for a mentioned user.")
async def ip_address(ctx, member: discord.Member):
    num1 = random.randint(0, 255)
    num2 = random.randint(0, 255)
    num3 = random.randint(0, 255)
    num4 = random.randint(0, 255)
    ipaddress = f"{member.display_name}'s IP Address is: {num1}.{num2}.{num3}.{num4}"
    await ctx.send(ipaddress)

@client.command(name="addrole", help="Creates a new role with the specified name and hex color. (Admin only)")
@commands.has_permissions(administrator=True)
async def addrole(ctx, role_name: str, hex_color: str):
    """Creates a role with the specified name and hex color (Admin only)."""

    
    if not hex_color.startswith("#") or len(hex_color) != 7:
        await ctx.send("Invalid hex color format. Use the format `#RRGGBB`.")
        return
    
    try:
        color = discord.Color(int(hex_color[1:], 16))  
        role = await ctx.guild.create_role(name=role_name, color=color)
        await ctx.send(f"Role `{role.name}` created successfully with color `{hex_color}`!")
    except discord.Forbidden:
        await ctx.send("I lack the required permissions to create roles.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

@addrole.error
async def addrole_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You need to be an administrator to use this command.")

@client.command(name="deleteallemotes", help="Deletes all custom emotes in the server. Host-only command.")
async def deleteallemotes(ctx):
    guild_id = str(ctx.guild.id)
    server_config = config.get(guild_id)

    if not server_config:
        await ctx.send("Server configuration not found.")
        return

    host_role_id = server_config.get("host_role")
    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)

    if host_role not in ctx.author.roles:
        await ctx.send("Only hosts can use this command.")
        return

    if not ctx.guild.emojis:
        await ctx.send("This server has no custom emotes.")
        return

    await ctx.send("⚠️ Are you sure you want to delete **ALL custom emotes**? Type `Yes` to confirm.")

    def check(m):
        return m.author == ctx.author and m.content.strip().lower() == "yes"

    try:
        confirmation = await client.wait_for("message", check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("Timed out. Emote deletion cancelled.")
        return

    deleted = 0
    for emoji in ctx.guild.emojis:
        try:
            await emoji.delete()
            deleted += 1
        except discord.Forbidden:
            await ctx.send(f"❌ Could not delete emote `{emoji.name}` due to missing permissions.")
        except discord.HTTPException:
            await ctx.send(f"⚠️ Failed to delete `{emoji.name}`. Skipping.")

    await ctx.send(f"✅ Deleted {deleted} emotes.")

@client.command(name="groupconfessional", help="Creates a confessional channel for multiple users with a custom name.")
@commands.has_guild_permissions(administrator=True)
async def groupconfessional(ctx, channel_name: str, *users: discord.Member):
    server_id = str(ctx.guild.id)
    if server_id not in server_config:
        await ctx.send("Server configuration is missing. Please set the necessary roles and category first.")
        return

    required_settings = ['host_role', 'category_id', 'bot_role', 'player_role', 'spectator_role']
    missing_config = [key for key in required_settings if key not in server_config[server_id]]
    if missing_config:
        await ctx.send(f"Missing configuration for: {', '.join(missing_config)}.")
        return

    host_role_id = server_config[server_id]["host_role"]
    category_id = server_config[server_id]["category_id"]
    bot_role_id = server_config[server_id]["bot_role"]
    player_role_id = server_config[server_id]["player_role"]
    spectator_role_id = server_config[server_id]["spectator_role"]

    host_role = discord.utils.get(ctx.guild.roles, id=host_role_id)
    if host_role not in ctx.author.roles:
        await ctx.send("You do not have permission to use this command.")
        return

    try:
        category = discord.utils.get(ctx.guild.categories, id=category_id)
        existing_channel = discord.utils.get(category.channels, name=channel_name)

        if existing_channel:
            await ctx.send(f"A channel named '{channel_name}' already exists: {existing_channel.mention}.")
            return

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            host_role: discord.PermissionOverwrite.from_pair(discord.Permissions.all(), discord.Permissions.none()),
            discord.utils.get(ctx.guild.roles, id=bot_role_id): discord.PermissionOverwrite.from_pair(discord.Permissions.all(), discord.Permissions.none()),
            discord.utils.get(ctx.guild.roles, id=spectator_role_id): discord.PermissionOverwrite(read_messages=False, send_messages=False),
            discord.utils.get(ctx.guild.roles, id=player_role_id): discord.PermissionOverwrite(read_messages=False, send_messages=False),
        }

        for user in users:
            overwrites[user] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        channel = await category.create_text_channel(name=channel_name, overwrites=overwrites)
        await ctx.send(f"Confessional channel '{channel_name}' created for {', '.join(user.mention for user in users)}.")

        role_to_add = ctx.guild.get_role(player_role_id)
        if role_to_add:
            for user in users:
                await user.add_roles(role_to_add)
            await ctx.send(f"Player role has been added to {', '.join(user.mention for user in users)}.")

    except discord.Forbidden:
        await ctx.send("I do not have permission to create channels.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")

BOWL = "\U0001f963"  # 🥣
SIZE = 9
SHARD = -1
SHARD_LIMIT = 4

class SoupSweeper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="soupsweeper", help="Starts a game of SoupSweeper! You can specify how many soup bowls (5–10).")
    async def execute(self, ctx, num_soups: int = 10):
        if num_soups < 5 or num_soups > 10:
            await ctx.send(f"❌ Invalid number of soup bowls. Please choose a number between **5** and **10**.")
            return

        field = [[0] * SIZE for _ in range(SIZE)]
        final_field = ""

        self.set_shards(field, num_soups)
        start_row, start_col = self.determine_start_coords(field)

        for row in range(SIZE):
            for col in range(SIZE):
                emote = self.translate_to_emote(field[row][col])
                final_field += emote if (row, col) == (start_row, start_col) else f"||{emote}||"
            final_field += "\n"

        embed = discord.Embed(
            title="🥣 SoupSweeper",
            description=final_field,
            color=0xf5a9b8  
        )
        embed.set_footer(text=f"Try not to uncover a soup bowl! ({num_soups} bowls hidden)")

        await ctx.send(embed=embed)

    def set_shards(self, field, max_shards):
        shard_count = 0

        while shard_count < max_shards:
            row, col = random.randint(0, SIZE - 1), random.randint(0, SIZE - 1)
            if not self.can_be_placed(row, col, field):
                continue

            field[row][col] = SHARD
            shard_count += 1

            for dr in [-1, 0, 1]:
                for dc in [-1, 0, 1]:
                    nr, nc = row + dr, col + dc
                    if self.is_valid_pos(nr, nc) and field[nr][nc] != SHARD:
                        field[nr][nc] += 1

    def can_be_placed(self, row, col, field):
        if field[row][col] == SHARD:
            return False
        
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                nr, nc = row + dr, col + dc
                if self.is_valid_pos(nr, nc) and field[nr][nc] == SHARD_LIMIT:
                    return False
        
        return True

    def is_valid_pos(self, row, col):
        return 0 <= row < SIZE and 0 <= col < SIZE

    def determine_start_coords(self, field):
        while True:
            row, col = random.randint(0, SIZE - 1), random.randint(0, SIZE - 1)
            if field[row][col] == 0:
                return row, col

    def translate_to_emote(self, num):
        emotes = {
            SHARD: BOWL,
            0: "0️⃣",
            1: "1️⃣",
            2: "2️⃣",
            3: "3️⃣",
            4: "4️⃣",
            5: "5️⃣",
            6: "6️⃣",
            7: "7️⃣",
            8: "8️⃣"
        }
        return emotes.get(num, "⬜")

@client.command(name="lock", help="Adds a lock emote to the current channel name.")
async def lock_channel(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config or 'category_id' not in server_config[server_id]:
        await ctx.send("Category ID is not set for this server. Please configure it first.")
        return

    category_id = server_config[server_id]['category_id']

    if ctx.channel.category_id != category_id:
        await ctx.send("This command can only be used in channels under the specified category.")
        return

    try:
        if ctx.channel.name.endswith("🔒"):
            await ctx.send("This channel is already locked.")
        else:
            new_name = ctx.channel.name + "🔒"
            await ctx.channel.edit(name=new_name)
            await ctx.send(f"Channel locked: {ctx.channel.mention}")
    except discord.Forbidden:
        await ctx.send("I don't have permission to rename this channel.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


@client.command(name="unlock", help="Removes the lock emote from the current channel name.")
async def unlock_channel(ctx):
    server_id = str(ctx.guild.id)

    if server_id not in server_config or 'category_id' not in server_config[server_id]:
        await ctx.send("Category ID is not set for this server. Please configure it first.")
        return

    category_id = server_config[server_id]['category_id']

    if ctx.channel.category_id != category_id:
        await ctx.send("This command can only be used in channels under the specified category.")
        return

    try:
        if ctx.channel.name.endswith("🔒"):
            new_name = ctx.channel.name[:-1] 
            await ctx.channel.edit(name=new_name)
            await ctx.send(f"Channel unlocked: {ctx.channel.mention}")
        else:
            await ctx.send("This channel is not locked.")
    except discord.Forbidden:
        await ctx.send("I don't have permission to rename this channel.")
    except Exception as e:
        await ctx.send(f"An error occurred: {e}")


with open("commandlist.json", "r") as f:
    command_data = json.load(f)

def get_command_pages():
    halfway = len(command_data) // 2
    pages = [command_data[:halfway], command_data[halfway:]]
    return pages

@client.command(name="commandlist", help="Shows all available commands.")
async def commandlist(ctx):
    with open("commandlist.json", "r") as file:
        data = json.load(file)

    all_commands = data.get("commands", [])

    commands_per_page = 7
    paginated = [
        all_commands[i:i + commands_per_page]
        for i in range(0, len(all_commands), commands_per_page)
    ]

    if not paginated:
        return await ctx.send("❌ No commands found in the command list.")

    current_page = 0

    def generate_embed(page_index):
        embed = discord.Embed(
            title=f"🤖 Bot Commands — Page {page_index + 1}/{len(paginated)}",
            description="Here's a list of commands you can use:",
            color=0xf5a9b8
        )
        for cmd in paginated[page_index]:
            embed.add_field(name=f"`{cmd['name']}`", value=cmd['description'], inline=False)
        embed.set_footer(text=f"Page {page_index + 1}/{len(paginated)} — Use ⬅️ or ➡️ to navigate.")
        return embed

    message = await ctx.send(embed=generate_embed(current_page))
    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")

    def check(reaction, user):
        return (
            user == ctx.author and 
            str(reaction.emoji) in ["⬅️", "➡️"] and 
            reaction.message.id == message.id
        )

    while True:
        try:
            reaction, user = await client.wait_for("reaction_add", timeout=60.0, check=check)

            if str(reaction.emoji) == "➡️":
                current_page = (current_page + 1) % len(paginated)
            elif str(reaction.emoji) == "⬅️":
                current_page = (current_page - 1) % len(paginated)

            await message.edit(embed=generate_embed(current_page))
            await message.remove_reaction(reaction.emoji, user)

        except asyncio.TimeoutError:
            break

EIPPU_SECTIONS = {
    "sylvieon": "Sylvieon's Eippus 💖",
    "upcoming": "Upcoming Eippus! 💖",
    "ongoing": "Ongoing Eippus! 💖",
    "other": "Other Eippus! 💖"
}

OWNER_ID = 922921889347817483 

def load_shoutout_data():
    with open("shoutout.json", "r") as f:
        return json.load(f)

def save_shoutout_data(data):
    with open("shoutout.json", "w") as f:
        json.dump(data, f, indent=4)

async def is_owner(ctx):
    return ctx.author.id == OWNER_ID

@client.command(name="eippulist", help="View Sylvieon's and friends' Eippus.")
async def eippulist(ctx):
    data = load_shoutout_data()
    pages = []

    entries_per_page = 5

    for section, title in EIPPU_SECTIONS.items():
        section_entries = data.get(section, [])

        num_section_pages = max(1, (len(section_entries) + entries_per_page - 1) // entries_per_page)

        for page_index in range(num_section_pages):
            embed = discord.Embed(
                title=title.split(" 💖")[0] + (f" {page_index + 1}" if num_section_pages > 1 else ""),
                color=0xf5a9b8
            )

            if len(section_entries) == 0 and section in ["ongoing", "upcoming"]:
                msg = "Wow, there are no ongoing Eippus! Check back later." if section == "ongoing" \
                    else "No upcoming Eippus are listed yet! Stay tuned for announcements."
                embed.description = msg
            else:
                embed.description = {
                    "sylvieon": "Come check out my other Eipps!",
                    "upcoming": "Plenty of other cool Eippus coming soon! Be sure to join quick before they start!",
                    "ongoing": "These games are going on right now! Feel free to spectate.",
                    "other": "These may have concluded and are awaiting a new season. Stay tuned!"
                }[section]

                start = page_index * entries_per_page
                end = start + entries_per_page
                for e in section_entries[start:end]:
                    embed.add_field(name=f"`{e['name']}`", value=f"{e['description']} \n{e['link']}", inline=False)

            pages.append(embed)

    current_page = 0
    message = await ctx.send(embed=pages[current_page])

    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == message.id

    while True:
        try:
            reaction, user = await client.wait_for("reaction_add", timeout=120.0, check=check)

            if str(reaction.emoji) == "➡️" and current_page < len(pages) - 1:
                current_page += 1
                await message.edit(embed=pages[current_page])
            elif str(reaction.emoji) == "⬅️" and current_page > 0:
                current_page -= 1
                await message.edit(embed=pages[current_page])

            await message.remove_reaction(reaction, user)

        except asyncio.TimeoutError:
            break

@client.command(name="addeippu", help="Add a new Eippu to the list (owner only).")
async def addeippu(ctx, section: str, name: str, description: str, link: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized to use this command.")

    section = section.lower()
    if section not in EIPPU_SECTIONS:
        return await ctx.send(f"Invalid section. Choose from: {', '.join(EIPPU_SECTIONS)}")

    data = load_shoutout_data()
    data.setdefault(section, []).append({
        "name": name,
        "description": description,
        "link": link
    })
    save_shoutout_data(data)
    await ctx.send(f"✅ Added `{name}` to `{section}`.")


@client.command(name="updateeippu", help="Update an existing Eippu entry.")
async def updateeippu(ctx, section: str, name: str, new_description: str = None, new_link: str = None):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized.")

    section = section.lower()
    if section not in EIPPU_SECTIONS:
        return await ctx.send("Invalid section name.")

    data = load_shoutout_data()
    entry = next((e for e in data.get(section, []) if e["name"].lower() == name.lower()), None)

    if entry:
        if new_description:
            entry["description"] = new_description
        if new_link:
            entry["link"] = new_link
        save_shoutout_data(data)
        await ctx.send(f"✅ Updated `{name}` in `{section}`.")
    else:
        await ctx.send("❌ Entry not found.")


@client.command(name="moveeippu", help="Move an Eippu from one section to another.")
async def moveeippu(ctx, from_section: str, to_section: str, name: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized.")

    from_section, to_section = from_section.lower(), to_section.lower()
    if from_section not in EIPPU_SECTIONS or to_section not in EIPPU_SECTIONS:
        return await ctx.send("Invalid section name.")

    data = load_shoutout_data()
    entry = next((e for e in data.get(from_section, []) if e["name"].lower() == name.lower()), None)

    if entry:
        data[from_section].remove(entry)
        data.setdefault(to_section, []).append(entry)
        save_shoutout_data(data)
        await ctx.send(f"✅ Moved `{name}` from `{from_section}` to `{to_section}`.")
    else:
        await ctx.send("❌ Entry not found.")


@client.command(name="deleteeippu", help="Delete an Eippu from a section.")
async def deleteeippu(ctx, section: str, name: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized.")

    section = section.lower()
    if section not in EIPPU_SECTIONS:
        return await ctx.send("Invalid section name.")

    data = load_shoutout_data()
    before_count = len(data.get(section, []))
    data[section] = [e for e in data.get(section, []) if e["name"].lower() != name.lower()]
    after_count = len(data[section])

    if before_count != after_count:
        save_shoutout_data(data)
        await ctx.send(f"🗑️ Deleted `{name}` from `{section}`.")
    else:
        await ctx.send("❌ Entry not found.")

@client.command(name="renameeippu", help="Rename an existing Eippu (owner only).")
async def renameeippu(ctx, section: str, old_name: str, new_name: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized.")

    section = section.lower()
    if section not in EIPPU_SECTIONS:
        return await ctx.send("Invalid section name.")

    data = load_shoutout_data()
    entry = next((e for e in data.get(section, []) if e["name"].lower() == old_name.lower()), None)

    if entry:
        entry["name"] = new_name
        save_shoutout_data(data)
        await ctx.send(f"✏️ Renamed `{old_name}` to `{new_name}` in `{section}`.")
    else:
        await ctx.send("❌ Entry not found.")

@client.command(name="addeippbotcommand", help='Add a command to the command list (owner only).')
async def addeippbotcommand(ctx, name: str, description: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized to use this command.")

    with open("commandlist.json", "r") as f:
        data = json.load(f)

    if any(cmd["name"].lower() == name.lower() for cmd in data["commands"]):
        return await ctx.send("❌ A command with that name already exists.")

    data["commands"].append({
        "name": name,
        "description": description
    })

    with open("commandlist.json", "w") as f:
        json.dump(data, f, indent=2)

    await ctx.send(f"✅ Added command `{name}`.")

@client.command(name="updateeippbotcommand", help='Update an existing command\'s description (owner only).')
async def updateeippbotcommand(ctx, name: str, new_description: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized to use this command.")

    with open("commandlist.json", "r") as f:
        data = json.load(f)

    for cmd in data["commands"]:
        if cmd["name"].lower() == name.lower():
            cmd["description"] = new_description
            with open("commandlist.json", "w") as f:
                json.dump(data, f, indent=2)
            return await ctx.send(f"✅ Updated command `{name}`.")

    await ctx.send("❌ Command not found.")

@client.command(name="deleteeippbotcommand", help='Delete a command from the command list (owner only).')
async def deleteeippbotcommand(ctx, name: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized to use this command.")

    with open("commandlist.json", "r") as f:
        data = json.load(f)

    before = len(data["commands"])
    data["commands"] = [cmd for cmd in data["commands"] if cmd["name"].lower() != name.lower()]
    after = len(data["commands"])

    if before == after:
        return await ctx.send("❌ Command not found.")

    with open("commandlist.json", "w") as f:
        json.dump(data, f, indent=2)

    await ctx.send(f"🗑️ Deleted command `{name}`.")

@client.command(name="renameeippbotcommand", help="Rename an existing bot command (owner only).")
async def renameeippbotcommand(ctx, old_name: str, new_name: str):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized to use this command.")

    with open("commandlist.json", "r") as f:
        data = json.load(f)

    if any(cmd["name"].lower() == new_name.lower() for cmd in data["commands"]):
        return await ctx.send("❌ A command with the new name already exists.")

    for cmd in data["commands"]:
        if cmd["name"].lower() == old_name.lower():
            cmd["name"] = new_name
            with open("commandlist.json", "w") as f:
                json.dump(data, f, indent=2)
            return await ctx.send(f"✏️ Renamed command `{old_name}` to `{new_name}`.")

    await ctx.send("❌ Command not found.")

@client.command(name="talkhere")
async def talkhere(ctx, channel_id: int, *, message: str):

    if not await is_owner(ctx):
        return await ctx.send("You are not authorized to use this command.")
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete messages.")
        return
    except discord.HTTPException:
        await ctx.send("Failed to delete the message. Please try again.")
        return

    channel = client.get_channel(channel_id)
    if channel is None:
        await ctx.send("Could not find the specified channel. Make sure I'm in that channel.")
        return

    await channel.send(message)

async def get_random_pokemon_name():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://pokeapi.co/api/v2/pokemon?limit=1000") as resp:
            data = await resp.json()
            pokemon = random.choice(data["results"])
            return pokemon["name"].lower()

@client.command()
async def whosthatpokemon(ctx):
    pokemon_name = await get_random_pokemon_name()  
    display = [":black_large_square:" if c != ' ' else ' ' for c in pokemon_name]
    guessed_letters = set()
    lives = 7
    player = ctx.author

    def format_display():
        return ' '.join(display)

    def create_embed():
        embed = discord.Embed(
            title="Who's That Pokémon?",
            description=f"{format_display()}",
            color=discord.Color.gold()
        )
        embed.add_field(name="Lives", value=f"{lives} ❤️", inline=False)
        embed.add_field(name="Guessed Letters", value=", ".join(sorted(guessed_letters)) or "None", inline=False)
        embed.set_author(name=f"{player.name}'s game", icon_url=player.display_avatar.url)
        return embed

    def check(m):
        return m.author == player and m.channel == ctx.channel

    game_msg = await ctx.send(embed=create_embed())

    while lives > 0:
        try:
            guess_msg = await client.wait_for('message', check=check, timeout=600.0)
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Time's up! The Pokémon was **{pokemon_name.title()}**.")
            return

        guess = guess_msg.content.lower().strip()

        if len(guess) == 1:
            if guess in guessed_letters:
                await ctx.send(f"You already guessed `{guess}`!")
                continue
            guessed_letters.add(guess)
            if guess in pokemon_name:
                for i, letter in enumerate(pokemon_name):
                    if letter == guess:
                        display[i] = letter
                if ''.join(display) == pokemon_name:
                    embed = discord.Embed(
                        title="🎉 You got it!",
                        description=f"It's **{pokemon_name.title()}**!",
                        color=discord.Color.green()
                    )
                    image_name = pokemon_name.lower().replace("♀", "-f").replace("♂", "-m").replace(".", "").replace(" ", "-")
                    embed.set_image(url=f"https://img.pokemondb.net/artwork/{urllib.parse.quote(image_name)}.jpg")
                    await game_msg.edit(embed=embed)
                    return
            else:
                lives -= 1
        elif guess == pokemon_name:
            embed = discord.Embed(
                title="🎉 You got it!",
                description=f"It's **{pokemon_name.title()}**!",
                color=discord.Color.green()
            )
            image_name = pokemon_name.lower().replace("♀", "-f").replace("♂", "-m").replace(".", "").replace(" ", "-")
            embed.set_image(url=f"https://img.pokemondb.net/artwork/{urllib.parse.quote(image_name)}.jpg")
            await game_msg.edit(embed=embed)
            return
        else:
            lives -= 1

        await game_msg.edit(embed=create_embed())

    embed = discord.Embed(
        title="💀 Game Over",
        description=f"The Pokémon was **{pokemon_name.title()}**.",
        color=discord.Color.red()
    )
    embed.set_image(url="https://cdn.discordapp.com/emojis/848239838377148456.webp?size=128")
    await game_msg.edit(embed=embed)

@client.command(name="metronome", help="Calls a random move Metronome can select.")
async def metronome(ctx):
    try:
        with open("metronome.txt", "r", encoding="utf-8") as file:
            moves = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        return await ctx.send("❌ `metronome.txt` not found.")

    if not moves:
        return await ctx.send("❌ No moves found in `metronome.txt`.")

    selected_move = random.choice(moves)
    await ctx.send(f"🎲 **The Pokémon waggles its finger... It uses `{selected_move}`!**")

@client.command()
async def voltorbflip(ctx):
    try:
        with open("gamecorner.json", "r") as file:
            players = json.load(file)
    except FileNotFoundError:
        players = []

    player = next((p for p in players if p["user_id"] == str(ctx.author.id)), None)
    if player is None:
        player = {"user_id": str(ctx.author.id), "username": ctx.author.name, "coins": 0, "level": 1}
        players.append(player)

    level = player["level"]
    if level < 1:
        level = 1
    elif level > 8:
        level = 8

    level_data = {
        1: [(3, 1, 6), (0, 3, 6), (5, 0, 6), (2, 2, 6), (4, 1, 6)],
        2: [(1, 3, 7), (6, 0, 7), (3, 2, 7), (0, 4, 7), (5, 1, 7)],
        3: [(2, 3, 8), (7, 0, 8), (4, 2, 8), (1, 4, 8), (6, 1, 8)],
        4: [(3, 3, 8), (0, 5, 8), (8, 0, 10), (5, 2, 10), (2, 4, 10)],
        5: [(7, 1, 10), (4, 3, 10), (1, 5, 10), (9, 0, 10), (6, 2, 10)],
        6: [(3, 4, 10), (0, 6, 10), (8, 1, 10), (5, 3, 10), (2, 5, 10)],
        7: [(7, 2, 10), (4, 4, 10), (1, 6, 13), (9, 1, 13), (6, 3, 10)],
        8: [(0, 7, 10), (8, 2, 10), (5, 4, 10), (2, 6, 10), (7, 3, 10)]
    }

    board_size = 5
    choice = random.choice(level_data[level])
    twos, threes, voltorbs = choice
    hidden_board = [[1 for _ in range(board_size)] for _ in range(board_size)]
    positions = [(r, c) for r in range(board_size) for c in range(board_size)]
    random.shuffle(positions)

    for _ in range(voltorbs):
        r, c = positions.pop()
        hidden_board[r][c] = 'V'
    for _ in range(threes):
        r, c = positions.pop()
        hidden_board[r][c] = 3
    for _ in range(twos):
        r, c = positions.pop()
        hidden_board[r][c] = 2

    revealed = [[False for _ in range(board_size)] for _ in range(board_size)]
    coins = 0
    first_guess = True

    def format_board():
        rows = []
        header = "    1  2  3  4  5"
        for r in range(board_size):
            row_str = chr(65 + r) + "  "
            for c in range(board_size):
                if revealed[r][c]:
                    val = hidden_board[r][c]
                    row_str += {
                        1: "1️⃣ ", 2: "2️⃣ ", 3: "3️⃣ ", 'V': "💣 "
                    }[val]
                else:
                    row_str += "⬛ "
            row_sum = sum(val if isinstance(val, int) else 0 for val in hidden_board[r])
            vol_count = sum(1 for val in hidden_board[r] if val == 'V')
            row_str += f"| {row_sum}  {'💣'*vol_count}"
            rows.append(row_str)

        col_sums = []
        col_vols = []
        for c in range(board_size):
            total = 0
            bombs = 0
            for r in range(board_size):
                val = hidden_board[r][c]
                if isinstance(val, int):
                    total += val
                elif val == 'V':
                    bombs += 1
            col_sums.append(f"{total:2}")
            col_vols.append(f"{bombs:2}")

        footer1 = "⬇  " + " ".join(col_sums)
        footer2 = "💣 " + " ".join(col_vols)

        return f"```\n{header}\n" + "\n".join(rows) + f"\n{footer1}\n{footer2}\nTotal coins: {coins}```"

    embed = discord.Embed(
        title=f"Voltorb Flip – Level {level}",
        description=format_board(),
        color=0xf5a9b8
    )
    embed.set_author(name=f"{ctx.author.name}'s game", icon_url=ctx.author.display_avatar.url)
    message = await ctx.send(embed=embed)

    total_specials = twos + threes
    revealed_specials = 0

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    while True:
        try:
            guess_msg = await client.wait_for('message', check=check, timeout=300.0)
        except asyncio.TimeoutError:
            embed.description += "\n⏰ Time's up!"
            await message.edit(embed=embed)
            return

        guess = guess_msg.content.upper().strip()
        if guess == "QUIT":
            embed.description = format_board() + f"\n❌ You quit the game. Coins earned: {coins}"
            await message.edit(embed=embed)

            player["coins"] += coins
            player["level"] = 1  
            with open("gamecorner.json", "w") as file:
                json.dump(players, file, indent=4)

            return

        if len(guess) == 2 and guess[0] in "ABCDE" and guess[1] in "12345":
            r = ord(guess[0]) - 65
            c = int(guess[1]) - 1
        else:
            await ctx.send("Invalid format. Use like 'A1', 'C3', etc.")
            continue

        if revealed[r][c]:
            await ctx.send("That tile is already revealed!")
            continue

        revealed[r][c] = True
        value = hidden_board[r][c]

        if value == 'V':
            embed.description = format_board() + "\n💥 You hit a Voltorb! Game over. You earned 0 coins."
            await message.edit(embed=embed)

            player["coins"] += coins
            player["level"] = 1 
            with open("gamecorner.json", "w") as file:
                json.dump(players, file, indent=4)

            return
        elif isinstance(value, int):
            if first_guess:
                coins = value
                first_guess = False
            else:
                coins *= value
            if value in [2, 3]:
                revealed_specials += 1
            if revealed_specials == total_specials:
                embed.description = format_board() + f"\n🎉 You win! Coins earned: {coins}"
                await message.edit(embed=embed)

                player["coins"] += coins
                if player["level"] < 8:
                    player["level"] += 1  
                with open("gamecorner.json", "w") as file:
                    json.dump(players, file, indent=4)

                return

        embed.description = format_board()
        await message.edit(embed=embed)
        await guess_msg.delete()

@client.command()
async def leaderboard(ctx):

    try:
        with open("gamecorner.json", "r") as file:
            players = json.load(file)
    except FileNotFoundError:
        await ctx.send("No players found.")
        return

    players.sort(key=lambda x: x["coins"], reverse=True)

    players_per_page = 10
    total_pages = (len(players) + players_per_page - 1) // players_per_page  
    current_page = 1

    def format_leaderboard(page):
        start_index = (page - 1) * players_per_page
        end_index = min(page * players_per_page, len(players))
        page_players = players[start_index:end_index]

        leaderboard = ""
        for i, player in enumerate(page_players, start=start_index + 1):
            leaderboard += f"{i}. {player['username']} - {player['coins']} coins\n"
        
        return leaderboard

    embed = discord.Embed(
        title="Leaderboard",
        description=format_leaderboard(current_page),
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Page {current_page}/{total_pages}")

    message = await ctx.send(embed=embed)

    await message.add_reaction("⬅️")
    await message.add_reaction("➡️")

    def check(reaction, user):
        return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

    while True:
        try:
            reaction, user = await client.wait_for('reaction_add', check=check, timeout=120.0)
        except asyncio.TimeoutError:
            await message.clear_reactions()
            return
        
        if str(reaction.emoji) == "➡️" and current_page < total_pages:
            current_page += 1
        elif str(reaction.emoji) == "⬅️" and current_page > 1:
            current_page -= 1

        embed.description = format_leaderboard(current_page)
        embed.set_footer(text=f"Page {current_page}/{total_pages}")
        await message.edit(embed=embed)

        await message.remove_reaction(reaction, user)

@client.command()
async def addcoins(ctx, member: discord.Member, amount: int):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized.")

    try:
        with open("gamecorner.json", "r") as file:
            players = json.load(file)
    except FileNotFoundError:
        players = []

    player = next((p for p in players if p["user_id"] == str(member.id)), None)
    if player is None:
        player = {"user_id": str(member.id), "username": member.name, "coins": 0, "level": 1}
        players.append(player)

    player["coins"] += amount
    await ctx.send(f"Added {amount} coins to {member.name}. They now have {player['coins']} coins.")

    with open("gamecorner.json", "w") as file:
        json.dump(players, file, indent=4)


@client.command()
async def removecoins(ctx, member: discord.Member, amount: int):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized.")

    try:
        with open("gamecorner.json", "r") as file:
            players = json.load(file)
    except FileNotFoundError:
        players = []

    player = next((p for p in players if p["user_id"] == str(member.id)), None)
    if player is None:
        return await ctx.send(f"{member.name} does not have any coins recorded.")

    player["coins"] = max(0, player["coins"] - amount)
    await ctx.send(f"Removed {amount} coins from {member.name}. They now have {player['coins']} coins.")

    with open("gamecorner.json", "w") as file:
        json.dump(players, file, indent=4)


@client.command()
async def setcoins(ctx, member: discord.Member, amount: int):
    if not await is_owner(ctx):
        return await ctx.send("You are not authorized.")

    if amount < 0:
        return await ctx.send("Coins amount cannot be negative.")

    try:
        with open("gamecorner.json", "r") as file:
            players = json.load(file)
    except FileNotFoundError:
        players = []

    player = next((p for p in players if p["user_id"] == str(member.id)), None)
    if player is None:
        player = {"user_id": str(member.id), "username": member.name, "coins": amount, "level": 1}
        players.append(player)
    else:
        player["coins"] = amount

    await ctx.send(f"Set {member.name}'s coins to {amount}.")

    with open("gamecorner.json", "w") as file:
        json.dump(players, file, indent=4)

client.run(TOKEN)
