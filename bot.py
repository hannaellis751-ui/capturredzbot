"""
@capturredzbot - Professional Telegram Content Capture Bot
Version: 2.0.0
Description: Fetches content from protected Telegram channels
"""

import os
import re
import asyncio
import logging
import sys
from typing import Optional, Tuple, List

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from pyrogram.errors import UserNotParticipant, FloodWait, RPCError

# ==================== LOGGING CONFIGURATION ====================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== ENVIRONMENT VARIABLES ====================

class Config:
    """Centralized configuration management with validation."""
    
    # Required variables
    API_ID: int = 0
    API_HASH: str = ""
    BOT_TOKEN: str = ""
    SESSION: str = ""
    AUTH: int = 0
    
    # Optional variables
    FORCESUB: Optional[str] = None
    
    @classmethod
    def load(cls) -> bool:
        """Load and validate all environment variables."""
        
        def get_var(name: str, required: bool = True, default: any = None) -> any:
            """Safely get environment variable."""
            value = os.environ.get(name)
            if required and (value is None or value.strip() == ""):
                return None
            return value if value and value.strip() != "" else default
        
        logger.info("=" * 60)
        logger.info("🔍 Loading environment variables...")
        
        # Load all variables
        api_id = get_var("API_ID")
        api_hash = get_var("API_HASH")
        bot_token = get_var("BOT_TOKEN")
        session = get_var("SESSION")
        auth = get_var("AUTH")
        forcesub = get_var("FORCESUB", required=False)
        
        # Display status
        logger.info(f"API_ID: {'✅ Loaded' if api_id else '❌ Missing'}")
        logger.info(f"API_HASH: {'✅ Loaded' if api_hash else '❌ Missing'}")
        logger.info(f"BOT_TOKEN: {'✅ Loaded' if bot_token else '❌ Missing'}")
        logger.info(f"SESSION: {'✅ Loaded' if session else '❌ Missing'}")
        logger.info(f"AUTH: {'✅ Loaded' if auth else '❌ Missing'}")
        logger.info(f"FORCESUB: {forcesub if forcesub else 'Not Set'}")
        
        # Validate and convert
        errors = []
        
        if api_id is None:
            errors.append("API_ID")
        else:
            try:
                cls.API_ID = int(api_id)
            except ValueError:
                errors.append("API_ID (must be a number)")
        
        if api_hash is None:
            errors.append("API_HASH")
        else:
            cls.API_HASH = api_hash
        
        if bot_token is None:
            errors.append("BOT_TOKEN")
        else:
            cls.BOT_TOKEN = bot_token
        
        if session is None:
            errors.append("SESSION")
        else:
            cls.SESSION = session
        
        if auth is None:
            errors.append("AUTH")
        else:
            try:
                cls.AUTH = int(auth)
            except ValueError:
                errors.append("AUTH (must be a number)")
        
        if forcesub:
            cls.FORCESUB = forcesub.strip()
        
        if errors:
            logger.error(f"❌ Missing/Invalid variables: {', '.join(errors)}")
            logger.info("💡 Please add these variables in Railway dashboard:")
            for error in errors:
                logger.info(f"   - {error}")
            return False
        
        logger.info("✅ All environment variables loaded successfully!")
        logger.info("=" * 60)
        return True

# ==================== BOT CLIENTS ====================

class BotClients:
    """Manages both user and bot clients."""
    
    def __init__(self):
        self.user_client: Optional[Client] = None
        self.bot_client: Optional[Client] = None
    
    async def initialize(self) -> bool:
        """Initialize both clients with proper error handling."""
        try:
            # User client (for accessing protected content)
            self.user_client = Client(
                "user_session",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                session_string=Config.SESSION,
                in_memory=True,
                sleep_threshold=30
            )
            logger.info("✅ User client initialized")
            
            # Bot client (for handling user interactions)
            self.bot_client = Client(
                "bot_session",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                bot_token=Config.BOT_TOKEN,
                sleep_threshold=30
            )
            logger.info("✅ Bot client initialized")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Client initialization error: {e}")
            return False
    
    async def start(self) -> bool:
        """Start both clients."""
        try:
            await self.user_client.start()
            logger.info("✅ User client started successfully")
            
            await self.bot_client.start()
            logger.info("✅ Bot client started successfully")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Client start error: {e}")
            return False
    
    async def stop(self):
        """Stop both clients gracefully."""
        if self.user_client:
            await self.user_client.stop()
        if self.bot_client:
            await self.bot_client.stop()

# ==================== UTILITY CLASSES ====================

class LinkExtractor:
    """Handles Telegram link extraction and parsing."""
    
    @staticmethod
    def extract_link_info(link: str) -> Tuple[Optional[str], Optional[int]]:
        """Extract chat identifier and message ID from a Telegram link."""
        patterns = [
            r'https?://(?:t\.me|telegram\.me)/(?:c/)?([^/]+)/(\d+)',
            r'https?://(?:t\.me|telegram\.me)/([^/]+)/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, link)
            if match:
                return match.group(1), int(match.group(2))
        
        return None, None
    
    @staticmethod
    def extract_all_links(text: str) -> List[str]:
        """Extract all Telegram message links from text."""
        pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?[^/\s]+/\d+'
        return re.findall(pattern, text)

# ==================== BOT HANDLERS ====================

class BotHandlers:
    """All bot message handlers organized by functionality."""
    
    def __init__(self, clients: BotClients):
        self.clients = clients
        self.setup_handlers()
    
    def setup_handlers(self):
        """Register all message handlers."""
        bot = self.clients.bot_client
        
        @bot.on_message(filters.command("start") & filters.private)
        async def start_command(client, message: Message):
            await self.start_command(client, message)
        
        @bot.on_message(filters.command("help") & filters.private)
        async def help_command(client, message: Message):
            await self.help_command(client, message)
        
        @bot.on_message(filters.command("stats") & filters.private & filters.user(Config.AUTH))
        async def stats_command(client, message: Message):
            await self.stats_command(client, message)
        
        @bot.on_message(filters.command("batch") & filters.private & filters.user(Config.AUTH))
        async def batch_command(client, message: Message):
            await self.batch_command(client, message)
        
        @bot.on_callback_query(filters.regex("check_sub"))
        async def check_sub_callback(client, callback_query: CallbackQuery):
            await self.check_sub_callback(client, callback_query)
        
        @bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "stats", "batch"]))
        async def handle_message(client, message: Message):
            await self.handle_message(client, message)
    
    async def check_subscription(self, user_id: int) -> bool:
        """Check if user is subscribed to the required channel."""
        if not Config.FORCESUB:
            return True
        
        try:
            member = await self.clients.bot_client.get_chat_member(
                Config.FORCESUB, 
                user_id
            )
            return member.status in [
                enums.ChatMemberStatus.OWNER,
                enums.ChatMemberStatus.ADMINISTRATOR,
                enums.ChatMemberStatus.MEMBER
            ]
        except UserNotParticipant:
            return False
        except Exception as e:
            logger.error(f"Subscription check error: {e}")
            return True
    
    async def start_command(self, client, message: Message):
        """Handle /start command."""
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "User"
        
        if Config.FORCESUB and not await self.check_subscription(user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{Config.FORCESUB}")],
                [InlineKeyboardButton("✅ Check Subscription", callback_data="check_sub")]
            ])
            
            await message.reply_text(
                f"**🚫 Access Restricted**\n\n"
                f"Dear {user_name},\n"
                f"You must join our channel to use this bot.\n\n"
                f"👆 Tap the button below to join, then check subscription.",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        await message.reply_text(
            f"**👋 Hello {user_name}!**\n\n"
            f"I can fetch content from protected Telegram channels.\n\n"
            f"**📌 How to use:**\n"
            f"• Send me a message link like:\n"
            f"`https://t.me/channel_name/123`\n"
            f"• Send multiple links in one message\n"
            f"• I'll return the content from each link\n\n"
            f"**Supported formats:**\n"
            f"📝 Text\n"
            f"🖼️ Photos\n"
            f"🎬 Videos\n"
            f"📄 Documents\n"
            f"🎵 Audio\n\n"
            f"👑 **Owner:** @{message.from_user.username if message.from_user.username else 'N/A'}",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    
    async def help_command(self, client, message: Message):
        """Handle /help command."""
        await message.reply_text(
            "**📚 Help Guide**\n\n"
            "**Commands:**\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/stats - Bot statistics (Owner only)\n"
            "/batch - Process multiple links (Owner only)\n\n"
            "**📌 How to use:**\n"
            "1. Send me a Telegram message link\n"
            "2. I'll fetch the content for you\n"
            "3. Works with protected channels too!\n\n"
            "**Link Format:**\n"
            "`https://t.me/channel_name/123`\n"
            "`https://t.me/c/1234567890/123`\n\n"
            "**🛡️ Protected Content:**\n"
            "I can access content even when screenshots and copying are disabled.",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    
    async def stats_command(self, client, message: Message):
        """Handle /stats command (owner only)."""
        await message.reply_text(
            "📊 **Bot Status**\n\n"
            "✅ Bot is running successfully!\n"
            f"👑 Owner ID: `{Config.AUTH}`\n"
            f"📢 Force Subscribe: `{Config.FORCESUB if Config.FORCESUB else 'Disabled'}`\n"
            f"🤖 Bot Username: @capturredzbot",
            parse_mode=enums.ParseMode.MARKDOWN
        )
    
    async def batch_command(self, client, message: Message):
        """Handle /batch command (owner only)."""
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text(
                "**Usage:** `/batch link1 link2 link3 ...`\n\n"
                "**Example:**\n"
                "`/batch https://t.me/channel/123 https://t.me/channel/456`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        links = args[1].split()
        processed = 0
        failed = 0
        status_msg = await message.reply_text(f"⏳ Processing {len(links)} links...")
        
        for link in links:
            if await self.process_single_link(link, message.from_user.id):
                processed += 1
            else:
                failed += 1
            await asyncio.sleep(0.5)
        
        await status_msg.edit_text(
            f"✅ **Batch Complete**\n\n"
            f"✓ Successful: {processed}\n"
            f"✗ Failed: {failed}\n"
            f"📊 Total: {len(links)}"
        )
    
    async def check_sub_callback(self, client, callback_query: CallbackQuery):
        """Handle subscription check callback."""
        user_id = callback_query.from_user.id
        
        if await self.check_subscription(user_id):
            await callback_query.message.edit_text(
                "✅ **Subscription verified!**\n\n"
                "You can now use the bot. Send me any Telegram message link!",
                parse_mode=enums.ParseMode.MARKDOWN
            )
        else:
            await callback_query.answer(
                "❌ You haven't joined the channel yet. Please join and try again.",
                show_alert=True
            )
    
    async def process_single_link(self, link: str, user_id: int) -> bool:
        """Process a single Telegram link and send content to user."""
        chat_id, msg_id = LinkExtractor.extract_link_info(link)
        if not chat_id or not msg_id:
            logger.warning(f"Invalid link format: {link}")
            return False
        
        try:
            message = await self.clients.user_client.get_messages(chat_id, msg_id)
            
            if not message or message.empty:
                logger.warning(f"Message not found: {chat_id}/{msg_id}")
                return False
            
            if message.media:
                await message.copy(
                    chat_id=user_id,
                    caption=message.caption or "",
                    parse_mode=enums.ParseMode.HTML if message.caption else None
                )
            else:
                await self.clients.bot_client.send_message(
                    chat_id=user_id,
                    text=message.text or "Empty message",
                    parse_mode=enums.ParseMode.HTML if message.text else None
                )
            
            return True
            
        except FloodWait as e:
            logger.warning(f"Flood wait: {e.value} seconds")
            await asyncio.sleep(e.value)
            return await self.process_single_link(link, user_id)
            
        except RPCError as e:
            logger.error(f"RPC Error: {e}")
            return False
            
        except Exception as e:
            logger.error(f"Error processing {link}: {e}")
            return False
    
    async def handle_message(self, client, message: Message):
        """Handle regular messages with links."""
        user_id = message.from_user.id
        
        if Config.FORCESUB and not await self.check_subscription(user_id):
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{Config.FORCESUB}")]
            ])
            await message.reply_text(
                f"**🚫 Access Restricted**\n\nPlease join our channel first.",
                reply_markup=keyboard,
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        links = LinkExtractor.extract_all_links(message.text)
        
        if not links:
            await message.reply_text(
                "❌ No valid Telegram message links found.\n"
                "Send a link like: `https://t.me/channel_name/123`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        status_msg = await message.reply_text(f"⏳ Processing {len(links)} link(s)...")
        
        successful = 0
        for link in links:
            if await self.process_single_link(link, user_id):
                successful += 1
            await asyncio.sleep(0.5)
        
        await status_msg.edit_text(
            f"✅ **Done!**\n\n"
            f"✓ Successfully retrieved: {successful}\n"
            f"✗ Failed: {len(links) - successful}\n\n"
            f"📤 Send more links anytime!",
            parse_mode=enums.ParseMode.MARKDOWN
        )

# ==================== MAIN APPLICATION ====================

class BotApplication:
    """Main bot application orchestrator."""
    
    def __init__(self):
        self.clients = BotClients()
        self.handlers = None
    
    async def run(self):
        """Start and run the bot application."""
        try:
            if not Config.load():
                sys.exit(1)
            
            if not await self.clients.initialize():
                sys.exit(1)
            
            self.handlers = BotHandlers(self.clients)
            
            if not await self.clients.start():
                sys.exit(1)
            
            self.display_banner()
            
            await asyncio.Event().wait()
            
        except KeyboardInterrupt:
            logger.info("🛑 Shutting down gracefully...")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
        finally:
            await self.clients.stop()
            logger.info("✅ Cleanup complete")
    
    def display_banner(self):
        """Display startup banner with bot information."""
        logger.info("=" * 60)
        logger.info("🤖 @capturredzbot - Content Capture Bot")
        logger.info("=" * 60)
        logger.info(f"👑 Owner ID: {Config.AUTH}")
        logger.info(f"📢 Force Subscribe: {Config.FORCESUB if Config.FORCESUB else 'Disabled'}")
        logger.info("💡 Send /start to @capturredzbot on Telegram")
        logger.info("=" * 60)

# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    app = BotApplication()
    asyncio.run(app.run())
