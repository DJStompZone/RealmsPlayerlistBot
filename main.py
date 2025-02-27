import asyncio
import contextlib
import logging
import os
from collections import defaultdict

import aiohttp
import aioredis
import nextcord
import tomli
from nextcord.ext import commands
from tortoise import Tortoise
from tortoise.exceptions import ConfigurationError
from tortoise.exceptions import DoesNotExist
from websockets.exceptions import ConnectionClosedOK
from xbox.webapi.api.client import XboxLiveClient
from xbox.webapi.authentication.manager import AuthenticationManager
from xbox.webapi.authentication.models import OAuth2TokenResponse

import common.utils as utils
import keep_alive
from common.custom_providers import ClubProvider
from common.custom_providers import ProfileProvider
from common.help_cmd import PaginatedHelpCommand
from common.models import GuildConfig


# load the config file into environment variables
# this allows an easy way to access these variables from any file
# we allow the user to set a configuration location via an already-set
# env var if they wish, but it'll default to config.toml in the running
# directory
CONFIG_LOCATION = os.environ.get("CONFIG_LOCATION", "config.toml")
with open(CONFIG_LOCATION, "rb") as f:
    toml_dict = tomli.load(f)
    for key, value in toml_dict.items():
        os.environ[key] = str(value)


logger = logging.getLogger("nextcord")
logger.setLevel(logging.INFO)
handler = logging.FileHandler(
    filename=os.environ["LOG_FILE_PATH"], encoding="utf-8", mode="a"
)
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
logger.addHandler(handler)

DEV_GUILD_ID = int(os.environ["DEV_GUILD_ID"])


async def _get_prefixes(bot: utils.RealmBotBase, msg: nextcord.Message):
    if not msg.guild:
        return set()

    if prefixes := bot.cached_prefixes[msg.guild.id]:
        return prefixes

    guild_config = await GuildConfig.get(guild_id=msg.guild.id)
    prefixes = bot.cached_prefixes[msg.guild.id] = guild_config.prefixes
    return prefixes


async def realms_playerlist_prefixes(bot: utils.RealmBotBase, msg: nextcord.Message):
    mention_prefixes = {f"{bot.user.mention} ", f"<@!{bot.user.id}> "}

    try:
        custom_prefixes = await _get_prefixes(bot, msg)
    except DoesNotExist:
        # guild hasnt been added yet
        custom_prefixes = set()
    except AttributeError:
        # prefix handling runs before command checks, so there's a chance there's no guild
        custom_prefixes = {"!?"}
    except ConfigurationError:  # prefix handling also runs before on_ready sometimes
        custom_prefixes = set()
    except KeyError:  # rare possibility, but you know
        custom_prefixes = set()
    except asyncio.TimeoutError:  # happens right before reconnects
        custom_prefixes = set()

    return mention_prefixes.union(custom_prefixes)


def global_checks(ctx: commands.Context[utils.RealmBotBase]):
    if not ctx.bot.is_ready():
        return False

    if ctx.bot.init_load:
        return False

    if not ctx.guild:
        return False

    if ctx.author.id == ctx.bot.owner.id:
        return True

    return not (
        ctx.guild.id == DEV_GUILD_ID
        and ctx.command.qualified_name not in ("help", "ping")
    )


async def on_init_load():
    await Tortoise.init(
        db_url=os.environ.get("DB_URL"), modules={"models": ["common.models"]}
    )
    bot.redis = aioredis.from_url(os.environ.get("REDIS_URL"), decode_responses=True)

    await bot.wait_until_ready()

    bot.session = aiohttp.ClientSession()
    auth_mgr = AuthenticationManager(
        bot.session, os.environ["XBOX_CLIENT_ID"], os.environ["XBOX_CLIENT_SECRET"], ""
    )
    auth_mgr.oauth = OAuth2TokenResponse.parse_file(os.environ["XAPI_TOKENS_LOCATION"])
    await auth_mgr.refresh_tokens()
    xbl_client = XboxLiveClient(auth_mgr)
    bot.profile = ProfileProvider(xbl_client)
    bot.club = ClubProvider(xbl_client)

    bot.load_extension("onami")

    cogs_list = utils.get_all_extensions(os.environ["DIRECTORY_OF_BOT"])
    for cog in cogs_list:
        if cog != "cogs.owner_cmds":
            with contextlib.suppress(commands.NoEntryPointError):
                bot.load_extension(cog)
    application = await bot.application_info()
    bot.owner = application.owner


class RealmsPlayerlistBot(utils.RealmBotBase):
    def __init__(
        self,
        command_prefix,
        help_command=PaginatedHelpCommand(),
        description=None,
        **options,
    ):
        super().__init__(
            command_prefix,
            help_command=help_command,
            description=description,
            **options,
        )
        self._checks.append(global_checks)

    async def on_ready(self):
        while not hasattr(self, "owner"):
            await asyncio.sleep(0.1)

        utcnow = nextcord.utils.utcnow()
        time_format = nextcord.utils.format_dt(utcnow)

        connect_msg = (
            f"Logged in at {time_format}!"
            if self.init_load == True
            else f"Reconnected at {time_format}!"
        )

        await self.owner.send(connect_msg)

        self.init_load = False

        activity = nextcord.Activity(
            name="over some Realms", type=nextcord.ActivityType.watching
        )

        try:
            await self.change_presence(activity=activity)
        except ConnectionClosedOK:
            await utils.msg_to_owner(self, "Reconnecting...")

    async def on_disconnect(self):
        # basically, this needs to be done as otherwise, when the bot reconnects,
        # redis may complain that a connection was closed by a peer
        # this isnt a great solution, but it should work
        with contextlib.suppress(Exception):
            await self.redis.connection_pool.disconnect(inuse_connections=True)

    async def on_resumed(self):
        activity = nextcord.Activity(
            name="over some Realms", type=nextcord.ActivityType.watching
        )
        await self.change_presence(activity=activity)

    async def on_error(self, event, *args, **kwargs):
        try:
            raise
        except BaseException as e:
            await utils.error_handle(self, e)

    async def get_context(self, message, *, cls=utils.RealmContext):
        """
        A simple extension of get_content. If it doesn't manage to get a command, it changes the string used
        to get the command from - to _ and retries. Convenient for the end user.

        This allows uses the bot's custom context by default.
        """

        ctx = await super().get_context(message, cls=cls)
        if ctx.command is None and ctx.invoked_with:
            ctx.command = self.all_commands.get(ctx.invoked_with.replace("-", "_"))

        return ctx

    async def close(self) -> None:
        await bot.session.close()
        return await super().close()


intents = nextcord.Intents(
    guilds=True, emojis_and_stickers=True, messages=True, reactions=True
)
mentions = nextcord.AllowedMentions.all()

bot = RealmsPlayerlistBot(
    command_prefix=realms_playerlist_prefixes,
    allowed_mentions=mentions,
    intents=intents,
)

bot.cached_prefixes = defaultdict(set)
bot.init_load = True
bot.color = nextcord.Color(int(os.environ["BOT_COLOR"]))  # 8ac249, aka 9093705


bot.load_extension("cogs.owner_cmds")
bot.loop.create_task(on_init_load())
# keep_alive.keep_alive()
bot.run(os.environ["MAIN_TOKEN"])
