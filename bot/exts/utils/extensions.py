import functools
import typing as t
from enum import Enum

from bot import exts
from bot.bot import Bot
from bot.constants import Emojis
from bot.converters import Extension
from bot.utils.embeds import create_embed
from bot.utils.extensions import EXTENSIONS
from bot.utils.pagination import LinePaginator
from disnake.ext import commands
from disnake.ext.commands import Context, group
from loguru import logger

UNLOAD_BLACKLIST = {
    f"{exts.__name__}.utils.extensions",
}
BASE_PATH_LEN = len(exts.__name__.split("."))


class Action(Enum):
    """Represents an action to perform on an extension."""

    # Need to be partial otherwise they are considered to be function definitions.
    LOAD = functools.partial(Bot.load_extension)
    UNLOAD = functools.partial(Bot.unload_extension)
    RELOAD = functools.partial(Bot.reload_extension)


class Extensions(commands.Cog):
    """Extension management commands."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @group(
        name="extensions",
        aliases=("ext", "exts", "c", "cog", "cogs"),
        invoke_without_command=True,
    )
    async def extensions_group(self, ctx: Context) -> None:
        """Load, unload, reload, and list loaded extensions."""
        await ctx.send_help(ctx.command)

    @extensions_group.command(name="load", aliases=("l",))
    async def load_command(self, ctx: Context, *extensions: Extension) -> None:
        r"""
        Load extensions given their fully qualified or unqualified names.

        If '\*' or '\*\*' is given as the name, all unloaded extensions will be loaded.
        """  # noqa: W605
        if not extensions:
            await ctx.send_help(ctx.command)
            return

        if "*" in extensions or "**" in extensions:
            extensions = set(EXTENSIONS) - set(self.bot.extensions.keys())

        msg, did_error = self.batch_manage(Action.LOAD, *extensions)  # type: ignore
        embed = create_embed("error" if did_error else "confirmation", msg)
        await ctx.send(embed=embed)

    @extensions_group.command(name="unload", aliases=("ul",))
    async def unload_command(self, ctx: Context, *extensions: Extension) -> None:
        r"""
        Unload currently loaded extensions given their fully qualified or unqualified names.

        If '\*' or '\*\*' is given as the name, all loaded extensions will be unloaded.
        """  # noqa: W605
        if not extensions:
            await ctx.send_help(ctx.command)
            return

        blacklisted = "\n".join(UNLOAD_BLACKLIST & set(extensions))

        if blacklisted:
            msg = (
                f"The following extension(s) may not be unloaded:```\n{blacklisted}```"
            )
            did_error = True
        else:
            if "*" in extensions or "**" in extensions:
                extensions = set(self.bot.extensions.keys()) - UNLOAD_BLACKLIST

            msg, did_error = self.batch_manage(Action.UNLOAD, *extensions)

        embed = create_embed("error" if did_error else "confirmation", msg)
        await ctx.send(embed=embed)

    @extensions_group.command(name="reload", aliases=("r",), root_aliases=("reload",))
    async def reload_command(self, ctx: Context, *extensions: Extension) -> None:
        r"""
        Reload extensions given their fully qualified or unqualified names.

        If an extension fails to be reloaded, it will be rolled-back to the prior working state.

        If '\*' is given as the name, all currently loaded extensions will be reloaded.
        If '\*\*' is given as the name, all extensions, including unloaded ones, will be reloaded.
        """  # noqa: W605
        if not extensions:
            await ctx.send_help(ctx.command)
            return

        if "**" in extensions:
            extensions = EXTENSIONS
        elif "*" in extensions:
            extensions = set(self.bot.extensions.keys()) | set(extensions)
            extensions.remove("*")

        msg, did_error = self.batch_manage(Action.RELOAD, *extensions)
        embed = create_embed("error" if did_error else "confirmation", msg)
        await ctx.send(embed=embed)

    @extensions_group.command(name="list", aliases=("all",))
    async def list_command(self, ctx: Context) -> None:
        """
        Get a list of all extensions, including their loaded status.

        Grey indicates that the extension is unloaded.
        Green indicates that the extension is currently loaded.
        """
        embed = create_embed("info", title=f"Extensions ({len(EXTENSIONS)})")

        lines = []
        categories = self.group_extension_statuses()
        for category, extensions in sorted(categories.items()):
            # Treat each category as a single line by concatenating everything.
            # This ensures the paginator will not cut off a page in the middle of a category.
            category = category.replace("_", " ").title()
            extensions = "\n".join(sorted(extensions))
            lines.append(f"**{category}**\n{extensions}\n")

        logger.debug(
            f"{ctx.author} requested a list of all cogs. Returning a paginated list."
        )
        await LinePaginator.paginate(lines, ctx, embed, empty=False)

    def group_extension_statuses(self) -> t.Mapping[str, str]:
        """Return a mapping of extension names and statuses to their categories."""
        categories = {}

        for ext in EXTENSIONS:
            if ext in self.bot.extensions:
                status = Emojis.status_online
            else:
                status = Emojis.status_offline

            path = ext.split(".")
            if len(path) > BASE_PATH_LEN + 1:
                category = " - ".join(path[BASE_PATH_LEN:-1])
            else:
                category = "uncategorised"

            categories.setdefault(category, []).append(f"{status}  {path[-1]}")

        return categories

    def batch_manage(self, action: Action, *extensions: str) -> tuple[str, bool]:
        """
        Apply an action to multiple extensions and return a message with the results.

        If only one extension is given, it is deferred to `manage()`.
        """
        if len(extensions) == 1:
            msg, error_msg = self.manage(action, extensions[0])
            return (msg, bool(error_msg))

        verb = action.name.lower()
        failures = {}

        for extension in extensions:
            _, error = self.manage(action, extension)
            if error:
                failures[extension] = error

        msg = f"{len(extensions) - len(failures)} / {len(extensions)} extensions {verb}ed."
        status = bool(failures)

        if failures:
            failures = "\n".join(f"{ext}\n    {err}" for ext, err in failures.items())
            msg += f"\n\n**Failures:**```\n{failures}```"

        logger.debug(f"Batch {verb}ed extensions.")
        return msg, status

    def manage(self, action: Action, ext: str) -> t.Tuple[str, t.Optional[str]]:
        """Apply an action to an extension and return the status message and any error message."""
        verb = action.name.lower()
        error_msg = None

        try:
            action.value(self.bot, ext)
        except (commands.ExtensionAlreadyLoaded, commands.ExtensionNotLoaded):
            if action is Action.RELOAD:
                # When reloading, just load the extension if it was not loaded.
                return self.manage(Action.LOAD, ext)

            msg = f"Extension `{ext}` is already {verb}ed."
            logger.debug(msg[4:])
        except Exception as e:
            if hasattr(e, "original"):
                e = e.original

            logger.exception(f"Extension '{ext}' failed to {verb}.")

            error_msg = f"{e.__class__.__name__}: {e}"
            msg = f"Failed to {verb} extension `{ext}`:\n```\n{error_msg}```"
        else:
            msg = f"Extension successfully {verb}ed: `{ext}`."
            logger.debug(msg[10:])

        return msg, error_msg

    # This cannot be static (must have a __func__ attribute).
    async def cog_check(self, ctx: Context) -> bool:
        """Only allow the bot owner invoke the commands in this cog."""
        return await self.bot.is_owner(ctx.author)

    # This cannot be static (must have a __func__ attribute).
    async def cog_command_error(self, ctx: Context, error: Exception) -> None:
        """Handle BadArgument errors locally to prevent the help command from showing."""
        if isinstance(error, commands.BadArgument):
            embed = create_embed("error", str(error))
            await ctx.send(embed=embed)
            error.handled = True


def setup(bot: Bot) -> None:
    """Load the Extensions cog."""
    bot.add_cog(Extensions(bot))
