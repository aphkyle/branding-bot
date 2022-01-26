import io
import os
from urllib.parse import urlparse
from xml.etree.ElementTree import ParseError

import aiohttp
import cairosvg
import disnake
from bot.constants import OUTPUT_IMAGE_FORMATS
from disnake.ext import commands
from PIL import Image, UnidentifiedImageError

from bot.utils.executor import in_executor


async def download_bytes(url: str) -> io.BytesIO:
    """Downloads bytes from a given `url` and return it."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return io.BytesIO(await resp.read())

                raise commands.BadArgument(f"The given [URL]({url}) can't be accessed.")
        except (aiohttp.InvalidURL, aiohttp.ClientConnectionError):
            raise commands.BadArgument("The given URL is invalid.")


async def download_image(url: str) -> Image.Image:
    """Downloads image from a url and returns a it."""
    try:
        return Image.open(await download_bytes(url))
    except UnidentifiedImageError:
        raise commands.BadArgument(f"The given [URL]({url}) leads to an invalid image.")


async def image_to_file(
    image: Image.Image, filename: str = "image", format: str = "PNG"
) -> disnake.File:
    """
    Converts a Pillow Image object to a Disnake File object.

    Do not include any extension in the `filename` argument. For example, pass
    "image" instead of "image.png". The extension is appended
    automatically based on the format.
    """
    format = format.upper()
    if format not in OUTPUT_IMAGE_FORMATS:
        raise ValueError(
            f"'{format}' is not one of the supported formats ({', '.join(OUTPUT_IMAGE_FORMATS)})."
        )

    def _convert(image):
        if format in ["JPEG", "PDF"]:
            image = image.convert("RGB")  # Removes transparancy

        with io.BytesIO() as image_binary:
            image.save(image_binary, format)
            image_binary.seek(0)
            return disnake.File(
                fp=image_binary,
                filename=f"{filename}.{format.lower()}",
            )

    return await in_executor(_convert, image)


async def bytes_to_file(byte_stream: bytes, filename: str = None) -> disnake.File:
    """Converts a bytes-like object to a Disnake File object."""
    image = Image.open(io.BytesIO(byte_stream))
    if filename:
        return await image_to_file(image, filename)
    return await image_to_file(image)


def filename_from_url(url: str) -> str:
    """
    Get the filename of a file, from a url

    Returns the first string in the filename. For example, "image" instead of
    "image.png", or "files" instead of "files.archive.zip".
    """
    path = urlparse(url).path
    filename = os.path.basename(path)
    return filename.split(".")[0]


def image_to_mask(image: Image.Image) -> Image.Image:
    data: list[int] = []
    for item in image.convert("RGBA").getdata():
        data.append(0 if item[3] == 0 else 256)

    mask = Image.new("L", image.size)
    mask.putdata(data)
    return mask


def add_background(image: Image.Image, color: str | int):
    canvas = Image.new("RGBA", image.size, color=color)
    return Image.composite(image, canvas, image_to_mask(image))


def rasterize_svg(bytestream: bytes, scale: int = 1) -> Image.Image:
    try:
        output = cairosvg.svg2png(bytestring=bytestream, scale=scale)
    except ParseError:
        raise commands.BadArgument("The provided URL returns to an invalid SVG.")
    if not output:
        raise commands.BadArgument("No image was found.")

    return Image.open(io.BytesIO(output))
