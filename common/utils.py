#!/usr/bin/env python3.8
import collections
import logging
import traceback
import typing
from pathlib import Path

import aiohttp
import aioredis
import nextcord
from nextcord.ext import commands

from .models import GuildConfig


def proper_permissions():
    async def predicate(ctx: commands.Context):
        # checks if author has admin or manage guild perms or is the owner
        permissions = ctx.channel.permissions_for(ctx.author)
        return permissions.manage_guild

    return commands.check(predicate)


async def deprecated_cmd(ctx: commands.Context):
    deprecated_embed = nextcord.Embed(
        colour=nextcord.Colour.darker_grey(),
        description="This feature is deprecated, "
        + "and will be removed by the end of this year."
        + "\nDM Astrea if that is an issue.",
    )

    await ctx.reply(embed=deprecated_embed)


async def error_handle(bot, error, ctx=None):
    # handles errors and sends them to owner
    if isinstance(error, aiohttp.ServerDisconnectedError):
        to_send = "Disconnected from server!"
        split = True
    else:
        error_str = error_format(error)
        logging.getLogger("discord").error(error_str)

        chunks = line_split(error_str)
        for i in range(len(chunks)):
            chunks[i][0] = f"```py\n{chunks[i][0]}"
            chunks[i][len(chunks[i]) - 1] += "\n```"

        final_chunks = ["\n".join(chunk) for chunk in chunks]
        if ctx and hasattr(ctx, "message") and hasattr(ctx.message, "jump_url"):
            final_chunks.insert(0, f"Error on: {ctx.message.jump_url}")

        to_send = final_chunks
        split = False

    await msg_to_owner(bot, to_send, split)

    if ctx:
        error_embed = nextcord.Embed(
            colour=nextcord.Colour.red(),
            description=(
                "An internal error has occured. The bot owner has been notified.\n"
            )
            + f"Error (for bot owner purposes): {error}",
        )
        if isinstance(ctx, commands.Context):
            await ctx.reply(embed=error_embed)
        elif isinstance(ctx, nextcord.Interaction):
            await ctx.send(embed=error_embed)


async def msg_to_owner(bot, content, split=True):
    # sends a message to the owner
    owner = bot.owner
    string = str(content)

    str_chunks = string_split(string) if split else content
    for chunk in str_chunks:
        await owner.send(f"{chunk}")


def line_split(content: str, split_by=20):
    content_split = content.splitlines()
    return [
        content_split[x : x + split_by] for x in range(0, len(content_split), split_by)
    ]


def embed_check(embed: nextcord.Embed) -> bool:
    """Checks if an embed is valid, as per Discord's guidelines.
    See https://discord.com/developers/docs/resources/channel#embed-limits for details."""
    if len(embed) > 6000:
        return False

    if embed.title and len(embed.title) > 256:
        return False
    if embed.description and len(embed.description) > 4096:
        return False
    if embed.author and embed.author.name and len(embed.author.name) > 256:
        return False
    if embed.footer and embed.footer.text and len(embed.footer.text) > 2048:
        return False
    if embed.fields:
        if len(embed.fields) > 25:
            return False
        for field in embed.fields:
            if field.name and len(field.name) > 1024:
                return False
            if field.value and len(field.value) > 2048:
                return False

    return True


def deny_mentions(user):
    # generates an AllowedMentions object that only pings the user specified
    return nextcord.AllowedMentions(everyone=False, users=[user], roles=False)


def error_format(error):
    # simple function that formats an exception
    return "".join(
        traceback.format_exception(
            etype=type(error), value=error, tb=error.__traceback__
        )
    )


def string_split(string):
    # simple function that splits a string into 1950-character parts
    return [string[i : i + 1950] for i in range(0, len(string), 1950)]


def file_to_ext(str_path, base_path):
    # changes a file to an import-like string
    str_path = str_path.replace(base_path, "")
    str_path = str_path.replace("/", ".")
    return str_path.replace(".py", "")


def get_all_extensions(str_path, folder="cogs"):
    # gets all extensions in a folder
    ext_files = collections.deque()
    loc_split = str_path.split("cogs")
    base_path = loc_split[0]

    if base_path == str_path:
        base_path = base_path.replace("main.py", "")
    base_path = base_path.replace("\\", "/")

    if base_path[-1] != "/":
        base_path += "/"

    pathlist = Path(f"{base_path}/{folder}").glob("**/*.py")
    for path in pathlist:
        str_path = str(path.as_posix())
        str_path = file_to_ext(str_path, base_path)

        if str_path != "cogs.db_handler":
            ext_files.append(str_path)

    return ext_files


def toggle_friendly_str(bool_to_convert):
    return "on" if bool_to_convert == True else "off"


def yesno_friendly_str(bool_to_convert):
    return "yes" if bool_to_convert == True else "no"


class CustomCheckFailure(commands.CheckFailure):
    # custom classs for custom prerequisite failures outside of normal command checks
    pass


class RealmContext(commands.Context):
    guild: nextcord.Guild
    guild_config: typing.Optional[GuildConfig]
    bot: "RealmBotBase"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.guild_config = None

    async def fetch_config(self) -> GuildConfig:
        """
        Gets the configuration for the context's guild.

        Returns:
            GuildConfig: The guild config.
        """
        if self.guild_config:
            return self.guild_config

        config = await GuildConfig.get(guild_id=self.guild.id)
        self.guild_config = config
        return config

    async def reply(self, content: typing.Optional[str] = None, **kwargs):
        # by default, replying will fail if the message no longer exists
        # id rather the message still continue to send, personally
        ref = nextcord.MessageReference.from_message(
            self.message, fail_if_not_exists=False
        )
        return await self.channel.send(content, reference=ref, **kwargs)


if typing.TYPE_CHECKING:
    from .custom_providers import ProfileProvider, ClubProvider

    class RealmBotBase(commands.Bot):
        init_load: bool
        color: nextcord.Color
        session: aiohttp.ClientSession
        profile: ProfileProvider
        club: ClubProvider
        owner: nextcord.User
        redis: aioredis.Redis
        cached_prefixes: typing.DefaultDict[int, typing.Set[str]]

        async def get_context(self, message, *, cls=RealmContext) -> RealmContext:
            ...

else:

    class RealmBotBase(commands.Bot):
        pass
