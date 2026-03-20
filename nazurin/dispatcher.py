import asyncio
from typing import ClassVar
from urllib.parse import urljoin

from aiogram import Bot, Dispatcher, F
from aiogram.enums import UpdateType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, Message, Update
from aiogram.types.reaction_type_emoji import ReactionTypeEmoji
from aiogram.utils.chat_action import ChatActionMiddleware
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from nazurin import config
from nazurin.config import FeedbackType
from nazurin.utils import logger
from nazurin.utils.exceptions import AlreadyExistsError
from nazurin.utils.filters import URLFilter

from .bot import NazurinBot
from .commands import CommandsManager
from .middleware import AuthMiddleware, LoggingMiddleware
from .server import NazurinServer


class NazurinDispatcher(Dispatcher):
    allowed_updates: ClassVar[list[UpdateType]] = [UpdateType.MESSAGE]

    def __init__(self, bot: NazurinBot):
        super().__init__()
        self.bot: NazurinBot = bot

        self.update.outer_middleware(AuthMiddleware())
        self.message.middleware(LoggingMiddleware())
        self.message.middleware(ChatActionMiddleware())

        self.server = NazurinServer(bot)

        self.startup.register(self.on_startup)
        self.shutdown.register(self.on_shutdown)

        self.commands = CommandsManager()

    def init(self):
        self.bot.init()
        self.message.register(
            self.update_collection,
            F.entities | F.caption_entities,
            URLFilter(),
        )

    def message_handler(
        self,
        *custom_filters,
        args="",
        description="",
        help_text="",
        **kwargs,
    ):
        """
        Register message handler with commands and description.
        For more information see aiogram documentation.

        Parameters
        ----------
            args: Arguments string
            description: Description
            help_text: Help text
        """

        self.commands.register(
            *custom_filters,
            args=args,
            description=description,
            help_text=help_text,
        )
        return self.message(
            *custom_filters,
            **kwargs,
        )

    async def on_startup(self, *_args):
        if config.ENV == "production":
            await self.bot.set_webhook(
                urljoin(config.WEBHOOK_URL, config.WEBHOOK_PATH),
                secret_token=config.WEBHOOK_SECRET,
                allowed_updates=self.allowed_updates,
                drop_pending_updates=True,
            )
        logger.info(
            "Command auto sync on startup: enabled={}",
            config.AUTO_SET_COMMANDS,
        )
        if config.AUTO_SET_COMMANDS:
            await self.set_commands_safe()
        await self.bot.on_startup()

    async def on_shutdown(self, *_args):
        logger.info(
            "Command auto cleanup on shutdown: enabled={}",
            config.AUTO_DELETE_COMMANDS_ON_SHUTDOWN,
        )
        if config.AUTO_DELETE_COMMANDS_ON_SHUTDOWN:
            await self.clear_commands_safe()
        await self.bot.on_shutdown()

    def managed_commands(self) -> list[BotCommand]:
        commands = {}
        for command in self.commands.list():
            commands[command.command] = command
        return list(commands.values())

    async def set_commands_safe(self):
        managed_commands = self.managed_commands()
        if not managed_commands:
            logger.info("Skipped auto setting bot commands: no managed commands found")
            return
        try:
            existing_commands = await self.bot.get_my_commands()
            merged_commands = {
                command.command: command for command in existing_commands
            }
            for command in managed_commands:
                merged_commands[command.command] = command
            await self.bot.set_my_commands(list(merged_commands.values()))
            logger.info(
                "Auto set bot commands done: managed={}, existing={}, merged={}",
                len(managed_commands),
                len(existing_commands),
                len(merged_commands),
            )
        except TelegramAPIError as error:
            logger.warning("Failed to auto set bot commands: {}", error)
        except Exception as error:
            logger.exception(
                "Unexpected error when auto setting bot commands: {}",
                error,
            )

    async def clear_commands_safe(self):
        managed_names = {command.command for command in self.managed_commands()}
        if not managed_names:
            logger.info("Skipped auto clearing bot commands: no managed commands found")
            return
        try:
            existing_commands = await self.bot.get_my_commands()
            remaining_commands = [
                command
                for command in existing_commands
                if command.command not in managed_names
            ]
            if remaining_commands:
                await self.bot.set_my_commands(remaining_commands)
            else:
                await self.bot.delete_my_commands()
            logger.info(
                "Auto clear bot commands done: managed={}, existing={}, remaining={}",
                len(managed_names),
                len(existing_commands),
                len(remaining_commands),
            )
        except TelegramAPIError as error:
            logger.warning("Failed to auto clear bot commands: {}", error)
        except Exception as error:
            logger.exception(
                "Unexpected error when auto clearing bot commands: {}",
                error,
            )

    async def feed_update(self, bot: Bot, update: Update, **kwargs):
        with logger.contextualize(request=f"update:{update.update_id}"):
            return await super().feed_update(bot, update, **kwargs)

    def start(self):
        logger.info("Starting...")
        self.init()
        if config.ENV == "production":
            logger.info("Set webhook")
            handler = SimpleRequestHandler(
                self, self.bot, secret_token=config.WEBHOOK_SECRET
            )
            handler.register(self.server, config.WEBHOOK_PATH)
            setup_application(self.server, self, bot=self.bot)
            # Tell aiohttp to use main thread event loop instead of creating a new one
            # otherwise bot commands will run in a different loop
            # from main thread functions and classes like Mongo and Mega.api_upload,
            # resulting in RuntimeError: Task attached to different loop
            web.run_app(
                self.server,
                host=config.HOST,
                port=config.PORT,
                loop=asyncio.get_event_loop(),
                access_log_format=config.ACCESS_LOG_FORMAT,
            )

        else:

            async def start_polling():
                # self.server.start()
                try:
                    await self.bot.delete_webhook(drop_pending_updates=True)
                    await self.start_polling(
                        self.bot, allowed_updates=self.allowed_updates
                    )
                except asyncio.CancelledError:
                    pass

            asyncio.run(start_polling())

    async def stop(self):
        logger.info("Shutting down...")
        if config.ENV == "production":
            await self.bot.delete_webhook(drop_pending_updates=True)

    async def update_collection(self, message: Message, urls: list[str]):
        try:
            await self.bot.update_collection(urls, message)
            if config.FEEDBACK_TYPE in [
                FeedbackType.REPLY,
                FeedbackType.BOTH,
            ]:
                await message.reply("Done!")
            if config.FEEDBACK_TYPE in [
                FeedbackType.REACTION,
                FeedbackType.BOTH,
            ]:
                await message.react([ReactionTypeEmoji(emoji="❤")])
        except AlreadyExistsError as error:
            await message.reply(error.msg)
