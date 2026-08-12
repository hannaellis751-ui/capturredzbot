"""
@capturredzbot - Telegram Content Capture Bot
Professional-grade bot for fetching content from protected Telegram channels
Author: Senior Developer
Version: 2.0.0
"""

import os
import re
import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional, Tuple, List

from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from pyrogram.errors import UserNotParticipant, FloodWait, RPCError

# ==================== CONFIGURATION ====================

# Logging setup with proper formatting
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
    API_ID: int
    API_HASH: str
    BOT_TOKEN: str
    SESSION: str
    AUTH: int
    
    # Optional variables
    FORCESUB: Optional[str] = None
    
    @classmethod
    def load(cls) -> bool:
        """Load and validate all environment variables."""
        
        def get_var(name: str, required: bool = True, default: any = None) -> any:
            """Safely get environment variable."""
            value = os.environ.get(name)
            if required and (value is None or value.strip() == ""):
                logger.error(f"❌ Missing required variable: {name}")
                return None
            return value if value and value.strip() != "" else default
        
        # Load all variables
        api_id = get_var("API_ID")
        api_hash = get_var("API_HASH")
        bot_token = get_var("BOT_TOKEN")
        session = get_var("SESSION")
        auth = get_var("AUTH")
        forcesub = get_var("FORCESUB", required=False)
        
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
            logger.info("💡 Please set all required variables in Railway dashboard")
            return False
        
        logger.info("✅ All environment variables loaded successfully")
        logger.info(f"👑 Owner ID: {cls.AUTH}")
        logger.info(f"📢 Force Subscribe: {cls.FORCESUB if cls.FORCESUB else 'Disabled'}")
        return True

# ==================== INITIALIZE CLIENTS ====================

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
            logger.error(f"❌ Client initialization failed: {e}")
            return False
    
    async def start(self) -> bool:
        """Start both clients."""
        try:
            await self.user_client.start()
            logger.info("✅ User client started")
            
            await self.bot_client.start()
            logger.info("✅ Bot client started")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Client start failed: {e}")
            return False
    
    async def stop(self):
        """Stop both clients gracefully."""
        if self.user_client:
            await self.user_client.stop()
        if self.bot_client:
            await self.bot_client.stop()

# ==================== UTILITY FUNCTIONS ====================

class LinkExtractor:
    """Handles Telegram link extraction and parsing."""
    
    @staticmethod
    def extract_link_info(link: str) -> Tuple[Optional[str], Optional[int]]:
        """
        Extract chat identifier and message ID from a Telegram link.
        
        Args:
            link: Telegram message link (e.g., https://t.me/channel/123)
            
        Returns:
            Tuple of (chat_identifier, message_id) or (None, None)
        """
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
        
        # Command handlers
        bot.on_message(filters.command("start") & filters.private)(self.start_command)
        bot.on_message(filters.command("help") & filters.private)(self.help_command)
        bot.on_message(filters.command("stats") & filters.private & filters.user(Config.AUTH))(self.stats_command)
        bot.on_message(filters.command("batch") & filters.private & filters.user(Config.AUTH))(self.batch_command)
        
        # Callback query handler
        bot.on_callback_query(filters.regex("check_sub"))(self.check_sub_callback)
        
        # Message handler
        bot.on_message(filters.private & filters.text & ~filters.command(["start", "help", "stats", "batch"]))(self.handle_message)
    
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
            return True  # Allow access on error
    
    async def start_command(self, client, message: Message):
        """Handle /start command."""
        user_id = message.from_user.id
        user_name = message.from_user.first_name or "User"
        
        # Check subscription
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
        
        # Welcome message
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
            f"🤖 Bot Username: @capturredzbot\n"
            f"⏰ Uptime: Since last restart",
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
        status_msg = await message.reply_text("⏳ Processing links...")
        
        for link in links:
            if await self.process_single_link(link, message.from_user.id):
                processed += 1
            else:
                failed += 1
            await asyncio.sleep(0.5)  # Rate limiting
        
        await status_msg.edit_text(
            f"✅ **Batch Complete**\n\n"
            f"✓ Successful: {processed}\n"
            f"✗ Failed: {failed}\n"
            f"📊 Total: {len(links)}"
        )
    
    async def check_sub_callback(self, client, callback_query):
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
        """
        Process a single Telegram link and send content to user.
        
        Args:
            link: Telegram message link
            user_id: User to send content to
            
        Returns:
            bool: Success status
        """
        # Extract link info
        chat_id, msg_id = LinkExtractor.extract_link_info(link)
        if not chat_id or not msg_id:
            logger.warning(f"Invalid link format: {link}")
            return False
        
        try:
            # Fetch message using user client
            message = await self.clients.user_client.get_messages(chat_id, msg_id)
            
            if not message or message.empty:
                logger.warning(f"Message not found: {chat_id}/{msg_id}")
                return False
            
            # Send to user
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
        
        # Check subscription
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
        
        # Extract links
        links = LinkExtractor.extract_all_links(message.text)
        
        if not links:
            await message.reply_text(
                "❌ No valid Telegram message links found.\n"
                "Send a link like: `https://t.me/channel_name/123`",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return
        
        # Process links
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
            # Load configuration
            if not Config.load():
                sys.exit(1)
            
            # Initialize clients
            if not await self.clients.initialize():
                sys.exit(1)
            
            # Setup handlers
            self.handlers = BotHandlers(self.clients)
            
            # Start clients
            if not await self.clients.start():
                sys.exit(1)
            
            # Display startup banner
            self.display_banner()
            
            # Keep running
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
