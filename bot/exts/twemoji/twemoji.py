import re
from typing import Literal, Optional

import disnake
from bot.bot import Bot
from bot.utils.embeds import create_embed
from disnake.ext import commands
from disnake.interactions import ApplicationCommandInteraction
from emoji import UNICODE_EMOJI_ENGLISH, is_emoji

BASE_URLS = {
    "png": "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/",
    "svg": "https://raw.githubusercontent.com/twitter/twemoji/master/assets/svg/",
}
CODE = re.compile(r"[a-f1-9][a-f0-9]{3,5}$")


class Twemoji(commands.Cog):
    """Utilities for working with Twemojis."""

    def __init__(self, bot: Bot):
        self.bot = bot

    @staticmethod
    def get_url(codepoint: str, format: Literal["png", "svg"]) -> str:
        """Returns a source file URL for the specified Twemoji, in the corresponding format."""
        return f"{BASE_URLS[format]}{codepoint}.{format}"

    @staticmethod
    def alias_to_name(alias: str) -> str:
        """
        Transform a unicode alias to an emoji name.

        Example usages:
        >>> alias_to_name(":falling_leaf:")
        "Falling leaf"
        >>> alias_to_name(":family_man_girl_boy:")
        "Family man girl boy"
        """
        name = alias[1:-1].replace("_", " ")
        return name.capitalize()

    @staticmethod
    def build_embed(codepoint: str) -> disnake.Embed:
        """Returns the main embed for the `twemoji` commmand."""
        emoji = "".join(Twemoji.emoji(e) for e in codepoint.split("-"))

        embed = create_embed(
            title=Twemoji.alias_to_name(UNICODE_EMOJI_ENGLISH[emoji]),
            description=f"{codepoint.replace('-', ' ')}\n[Download svg]({Twemoji.get_url(codepoint, 'svg')})",
            thumbnail_url=Twemoji.get_url(codepoint, "png"),
        )
        return embed

    @staticmethod
    def emoji(codepoint: str) -> str:
        """
        Returns the emoji corresponding to a given `codepoint`, or `""` if no emoji was found.

        The return value is an emoji character, such as "🍂". The `codepoint`
        argument can be of any format, since it will be trimmed automatically.
        """
        if code := Twemoji.trim_code(codepoint):
            return chr(int(code, 16))
        return ""

    @staticmethod
    def codepoint(emoji: str) -> str:
        """
        Returns the codepoint, in a trimmed format, of a single emoji.

        `emoji` should be an emoji character, such as "🐍" and "🥰", and
        not a codepoint like "1f1f8". When working with combined emojis,
        such as "🇸🇪" and "👨‍👩‍👦", send the component emojis through the method
        one at a time.
        """
        return hex(ord(emoji))[2:]

    @staticmethod
    def trim_code(codepoint: Optional[str]) -> Optional[str]:
        """
        Returns the meaningful information from the given `codepoint`.

        If no codepoint is found, `None` is returned.

        Example usages:
        >>> trim_code("U+1f1f8")
        "1f1f8"
        >>> trim_code("\u0001f1f8")
        "1f1f8"
        >>> trim_code("1f466")
        "1f466"
        """
        if not codepoint:
            return None
        if code := CODE.search(codepoint):
            return code.group()

    @staticmethod
    def codepoint_from_input(raw_emoji: str) -> str:
        """
        Returns the codepoint corresponding to the passed tuple, separated by "-".

        The return format matches the format used in URLs for Twemoji source files.

        Example usages:
        >>> codepoint_from_input(("🐍",))
        "1f40d"
        >>> codepoint_from_input(("1f1f8", "1f1ea"))
        "1f1f8-1f1ea"
        >>> codepoint_from_input(("👨‍👧‍👦",))
        "1f468-200d-1f467-200d-1f466"
        """
        emoji_list: list[str] = [emoji.lower() for emoji in raw_emoji.split()]
        if is_emoji(emoji_list[0]):
            emojis = (Twemoji.codepoint(emoji) for emoji in emoji_list[0])
            return "-".join(emojis)

        emoji = "".join(Twemoji.emoji(Twemoji.trim_code(code)) for code in emoji_list)  # type: ignore
        if is_emoji(emoji):
            return "-".join(Twemoji.codepoint(e) for e in emoji)

        raise ValueError("No codepoint could be obtained from the given input")

    @commands.slash_command()
    async def twemoji(
        self, inter: ApplicationCommandInteraction, raw_emoji: str
    ) -> None:
        """Sends a preview of a given Twemoji, specified by codepoint or emoji."""
        if len(raw_emoji) == 0:
            return
        try:
            codepoint = self.codepoint_from_input(raw_emoji)
        except ValueError:
            raise commands.BadArgument(
                "please include a valid emoji or emoji codepoint."
            )

        await inter.response.send_message(embed=self.build_embed(codepoint))


def setup(bot: Bot) -> None:
    """Load the Twemoji cog."""
    bot.add_cog(Twemoji(bot))
