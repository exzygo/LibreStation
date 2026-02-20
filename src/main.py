import discord
import yt_dlp
import asyncio
import os
from discord.ext import commands
from dotenv import load_dotenv
import re

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="libre!", intents=intents, help_command=None)

yt_dl_opts = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": False
}
ytdl = yt_dlp.YoutubeDL(yt_dl_opts)

ffmpeg_opts = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}

queues = {}
paused_timestamps = {}
current_sources = {}

def status_embed(title: str, description: str, color: discord.Color):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    embed.set_footer(text="LibreStation • Streaming Engine")
    return embed


def get_spotify_title(spotify_url: str):
    try:
        info = ytdl.extract_info(spotify_url, download=False, process=False)
        if info and "title" in info:
            return info["title"]
    except Exception:
        pass
    match = re.search(r"track/([a-zA-Z0-9]+)", spotify_url)
    if match:
        return f"spotify track {match.group(1)}"
    return "spotify track"


def get_source(url: str):
    if "open.spotify.com" in url:
        title = get_spotify_title(url)
        url = f"ytsearch:{title}"

    try:
        info = ytdl.extract_info(url, download=False)
        if "entries" in info:
            info = info["entries"][0]
        return info["url"], info.get("title", "Unknown title")
    except Exception as e:
        print(f"[ ERROR ] yt_dlp failed: {e}")
        return None, None


async def animate_extraction(ctx, msg):
    frames = ["○","●"]
    i = 0
    while True:
        try:
            frame = frames[i % len(frames)]
            await msg.edit(content=f"[ FFMPEG ] **Extracting and Downloading URL** (  {frame}  )")
            await asyncio.sleep(0.25)
            i += 1
        except (discord.NotFound, asyncio.CancelledError):
            break


@bot.event
async def on_ready():
    print(f"[ LOG ] BOT CONNECTED AS: {bot.user}")


async def next(ctx):
    vc = ctx.voice_client
    guild_id = ctx.guild.id

    if guild_id in queues and queues[guild_id]:
        song = queues[guild_id].pop(0)

        status_msg = await ctx.send(
            embed=status_embed(
                "↺ Preparing playback",
                "Extracting audio source and initializing stream...",
                discord.Color.gold()
            )
        )

        source_url, title = await asyncio.to_thread(get_source, song["url"])

        if not source_url:
            await status_msg.edit(
                embed=status_embed(
                    "✖ Failed",
                    "Could not load this track. Skipping...",
                    discord.Color.red()
                )
            )
            return await next(ctx)

        current_sources[guild_id] = source_url
        await asyncio.sleep(1)

        await status_msg.edit(
            embed=status_embed(
                "▶ Now Playing",
                f"**{title}**",
                discord.Color.blurple()
            )
        )

        vc.play(
            discord.FFmpegPCMAudio(source_url, **ffmpeg_opts),
            after=lambda e: asyncio.run_coroutine_threadsafe(next(ctx), bot.loop)
        )

    else:
        await ctx.send(
            embed=status_embed(
                "⏹ Queue finished",
                "No more tracks in queue.",
                discord.Color.dark_grey()
            )
        )
        current_sources.pop(guild_id, None)


@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="LibreStation — Command Help",
        description="List of available commands for the LibreStation bot.\nUse `libre!<command>` to execute.",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="▶  Music Playback",
        value=(
            "**add <url>** — Adds a song to the queue and starts playing.\n"
            "**play** — Resumes the current playback.\n"
            "**stop** — Pauses the current song.\n"
            "**skip** — Skips to the next song.\n"
            "**queue** — Displays the current playback queue.\n"
            "**exit** — Disconnects the bot from the voice channel."
        ),
        inline=False
    )

    embed.add_field(
        name="▶ Information",
        value=(
            "**help** — Shows this help message.\n"
            "**about** — Displays information about the bot."
        ),
        inline=False
    )

    embed.set_footer(
        text=(
            "LibreStation © 2025 — Free software under the GNU General Public License v2 (GPLv2)\n"
            "You may redistribute and/or modify this program under the terms of the GPLv2."
        )
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

    await ctx.send(embed=embed)


@bot.command(name="about")
async def about(ctx):
    embed = discord.Embed(
        title="About LibreStation",
        description=(
            "**LibreStation** is a minimalist and open-source music bot developed in Python "
            "using `discord.py` and `yt_dlp`, licesend under the **GNU GPLv2** and with support "
	        "for Youtube and Spotify music links.\n\n"
            "⏺  **Default prefix:** `libre!`\n"
            "⏺  **License:** [GNU GPL v2](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)\n"
            "⏺  **Source code:** publicly available at https://github.com/grassleaff/LibreStation"
        ),
        color=discord.Color.green()
    )

    embed.set_footer(
        text=(
            "LibreStation © 2025 — Distributed under the GNU GPLv2.\n"
            "No warranties; see the full license text for details."
        )
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)

    await ctx.send(embed=embed)


@bot.command()
async def exit(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Bye bye")
    else:
        await ctx.send("Im not on a voice channel, vro")


@bot.command()
async def add(ctx, url: str):
    if not ctx.author.voice:
        await ctx.send(
            embed=status_embed(
                "✖ Error",
                "You must be connected to a voice channel.",
                discord.Color.red()
            )
        )
        return

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect(self_deaf=True)

    status_msg = await ctx.send(
        embed=status_embed(
            "↺ Processing track",
            "Resolving source and preparing audio...",
            discord.Color.gold()
        )
    )

    source_url, title = await asyncio.to_thread(get_source, url)

    if not source_url:
        await status_msg.edit(
            embed=status_embed(
                "✖ Invalid link",
                "Unsupported or invalid URL.",
                discord.Color.red()
            )
        )
        return

    await status_msg.edit(
        embed=status_embed(
            "✔ Added to queue",
            f"**{title}**",
            discord.Color.green()
        )
    )

    if ctx.guild.id not in queues:
        queues[ctx.guild.id] = []

    queues[ctx.guild.id].append({"url": url, "title": title})

    vc = ctx.voice_client
    if not vc.is_playing() and not vc.is_paused():
        await next(ctx)


@bot.command()
async def stop(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await ctx.send("[  ❚❚  ] Paused")
    else:
        await ctx.send("[  *  ] No music on queue")


@bot.command()
async def play(ctx):
    vc = ctx.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await ctx.send("[  ▶  ] Playing")
    elif not vc:
        await ctx.send("Im not in a voice channel. Lemme join u! :D")
    else:
        await ctx.send("[  *  ] No music on queue")


@bot.command()
async def skip(ctx):
    vc = ctx.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await ctx.send("[  ►►  ] Skipped ")
    else:
        await ctx.send("[  *  ] No music on queue")


@bot.command()
async def queue(ctx):
    guild_id = ctx.guild.id

    if guild_id not in queues or len(queues[guild_id]) == 0:
        embed = discord.Embed(
            title="⊹˚♬₊⋆ - Queue",
            description="No music in queue.",
            color=discord.Color.dark_grey()
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(
        title="𝄞 - Music Queue",
        color=discord.Color.blurple()
    )

    # Now Playing
    vc = ctx.voice_client
    if vc and vc.is_playing():
        embed.add_field(
            name="▶ Now Playing",
            value="Streaming from queue",
            inline=False
        )
    else:
        embed.add_field(
            name="▶ Now Playing",
            value="Nothing playing",
            inline=False
        )

    # Queue list (limit to 10 items)
    max_items = 10
    queue_slice = queues[guild_id][:max_items]

    queue_text = ""
    for i, song in enumerate(queue_slice, start=1):
        queue_text += f"`{i}.` **{song['title']}**\n"

    if len(queues[guild_id]) > max_items:
        queue_text += f"\n`+ {len(queues[guild_id]) - max_items} more tracks...`"

    embed.add_field(
        name="⌲ Up Next",
        value=queue_text,
        inline=False
    )

    embed.set_footer(
        text=f"Total tracks in queue: {len(queues[guild_id])}"
    )

    embed.set_thumbnail(url=bot.user.display_avatar.url)

    await ctx.send(embed=embed)


bot.run(os.getenv("BOT_TOKEN"))
