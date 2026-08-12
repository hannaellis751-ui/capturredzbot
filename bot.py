import os
import re
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============= ENVIRONMENT VARIABLES =============
def get_env_var(var_name: str, required: bool = True, default: str = None):
    """Get environment variable with proper error handling."""
    value = os.environ.get(var_name)
    if required and (value is None or value.strip() == ""):
        logger.error(f"❌ Missing required environment variable: {var_name}")
        return None
    return value if value and value.strip() != "" else default

# Get all variables
API_ID = get_env_var("API_ID")
API_HASH = get_env_var("API_HASH")
BOT_TOKEN = get_env_var("BOT_TOKEN")
SESSION = get_env_var("SESSION")
AUTH = get_env_var("AUTH")
FORCESUB = get_env_var("FORCESUB", required=False, default=None)

# Convert numeric variables
if API_ID:
    try:
        API_ID = int(API_ID)
    except ValueError:
        logger.error("❌ API_ID must be a number")
        API_ID = None

if AUTH:
    try:
        AUTH = int(AUTH)
    except ValueError:
        logger.error("❌ AUTH must be a number")
        AUTH = None

# Validate all required variables
missing_vars = []
if API_ID is None:
    missing_vars.append("API_ID")
if API_HASH is None:
    missing_vars.append("API_HASH")
if BOT_TOKEN is None:
    missing_vars.append("BOT_TOKEN")
if SESSION is None:
    missing_vars.append("SESSION")
if AUTH is None:
    missing_vars.append("AUTH")

if missing_vars:
    logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
    logger.error("💡 Please add these variables in Railway dashboard")
    exit(1)

logger.info("✅ All required environment variables are set")

# ============= INITIALIZE CLIENTS =============
# User client - uses your account to access restricted content
try:
    user_client = Client(
        "user",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION,
        in_memory=True
    )
    logger.info("✅ User client initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize user client: {e}")
    exit(1)

# Bot client - handles user interactions
try:
    bot_client = Client(
        "capturredzbot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN
    )
    logger.info("✅ Bot client initialized")
except Exception as e:
    logger.error(f"❌ Failed to initialize bot client: {e}")
    exit(1)

# ============= FORCE SUBSCRIPTION CHECK =============
async def is_subscribed(user_id: int) -> bool:
    """Check if user is subscribed to the force subscribe channel."""
    if not FORCESUB:
        return True
    try:
        member = await bot_client.get_chat_member(FORCESUB, user_id)
        return member.status in [enums.ChatMemberStatus.OWNER, 
                                  enums.ChatMemberStatus.ADMINISTRATOR,
                                  enums.ChatMemberStatus.MEMBER]
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return True

# ============= BOT COMMANDS =============
@bot_client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "User"

    if FORCESUB and not await is_subscribed(user_id):
        btn = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCESUB}")],
            [InlineKeyboardButton("✅ Check Subscription", callback_data="check_sub")]
        ]
        await message.reply_text(
            f"**🚫 Access Restricted**\n\n"
            f"Dear {user_name},\n"
            f"You must join our channel to use this bot.\n\n"
            f"👆 Tap the button below to join, then check subscription.",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    await message.reply_text(
        f"**👋 Hello {user_name}!**\n\n"
        f"I can fetch content from protected Telegram channels.\n\n"
        f"**How to use:**\n"
        f"• Send me a message link like:\n"
        f"`https://t.me/channel_name/123`\n"
        f"• Send multiple links in one message\n"
        f"• I'll return the content from each link\n\n"
        f"**Supported:** Text, Photos, Videos, Documents, Audio\n\n"
        f"👑 **Owner:** @{message.from_user.username if message.from_user.username else 'N/A'}"
    )

@bot_client.on_callback_query(filters.regex("check_sub"))
async def check_sub_callback(client, callback_query):
    user_id = callback_query.from_user.id

    if await is_subscribed(user_id):
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

@bot_client.on_message(filters.command("batch") & filters.private)
async def batch_command(client, message):
    """Owner-only command to process multiple links at once."""
    if message.from_user.id != AUTH:
        await message.reply_text("⛔ This command is for the bot owner only.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text(
            "**Usage:** `/batch link1 link2 link3 ...`\n\n"
            "Example: `/batch https://t.me/channel/123 https://t.me/channel/456`",
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    links = args[1].split()
    processed = 0
    failed = 0
    status_msg = await message.reply_text("⏳ Processing links...")

    for link in links:
        result = await process_single_link(link, message.from_user.id)
        if result:
            processed += 1
        else:
            failed += 1
        await asyncio.sleep(0.5)

    await status_msg.edit_text(
        f"✅ **Batch Complete**\n\n"
        f"✓ Successful: {processed}\n"
        f"✗ Failed: {failed}\n"
        f"Total: {len(links)}"
    )

# ============= LINK PROCESSING =============
def extract_link_info(link: str) -> tuple:
    """Extract channel/chat and message ID from a Telegram link."""
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        return match.group(1), int(match.group(2))
    return None, None

async def process_single_link(link: str, user_id: int) -> bool:
    """Fetch a single message via user_client and send it via bot_client."""
    chat_identifier, msg_id = extract_link_info(link)
    if not chat_identifier or not msg_id:
        logger.warning(f"Invalid link format: {link}")
        return False

    try:
        message = await user_client.get_messages(chat_identifier, msg_id)

        if not message or message.empty:
            logger.warning(f"Message not found: {chat_identifier}/{msg_id}")
            return False

        try:
            if message.media:
                await message.copy(
                    chat_id=user_id,
                    caption=message.caption or "",
                    parse_mode=enums.ParseMode.HTML if message.caption else None
                )
            else:
                await bot_client.send_message(
                    chat_id=user_id,
                    text=message.text or "Empty message",
                    parse_mode=enums.ParseMode.HTML if message.text else None
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            return False

    except FloodWait as e:
        logger.warning(f"Flood wait: {e.value} seconds")
        await asyncio.sleep(e.value)
        return await process_single_link(link, user_id)
    except Exception as e:
        logger.error(f"Error processing {link}: {e}")
        return False

@bot_client.on_message(filters.private & filters.text & ~filters.command(["start", "batch"]))
async def handle_message(client, message):
    """Handle regular messages containing links."""
    user_id = message.from_user.id

    if FORCESUB and not await is_subscribed(user_id):
        btn = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCESUB}")]]
        await message.reply_text(
            f"**🚫 Access Restricted**\n\nPlease join our channel first.",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    text = message.text
    link_pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?[^/\s]+/\d+'
    links = re.findall(link_pattern, text)

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
        if await process_single_link(link, user_id):
            successful += 1
        await asyncio.sleep(0.5)

    await status_msg.edit_text(
        f"✅ **Done!**\n\n"
        f"✓ Successfully retrieved: {successful}\n"
        f"✗ Failed: {len(links) - successful}\n\n"
        f"Send more links anytime!",
        parse_mode=enums.ParseMode.MARKDOWN
    )

# ============= BOT ADMIN COMMANDS =============
@bot_client.on_message(filters.command("stats") & filters.user(AUTH))
async def stats_command(client, message):
    await message.reply_text(
        "📊 **Bot Status**\n\n"
        "✅ Bot is running successfully!\n"
        f"👑 Owner ID: `{AUTH}`\n"
        f"📢 Force Subscribe: `{FORCESUB if FORCESUB else 'Disabled'}`\n"
        f"🤖 Bot Username: @capturredzbot",
        parse_mode=enums.ParseMode.MARKDOWN
    )

@bot_client.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    await message.reply_text(
        "**📚 Help Guide**\n\n"
        "**Commands:**\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/stats - Bot statistics (Owner only)\n"
        "/batch - Process multiple links (Owner only)\n\n"
        "**How to use:**\n"
        "1. Send me a Telegram message link\n"
        "2. I'll fetch the content for you\n"
        "3. Works with protected channels too!\n\n"
        "**Link Format:**\n"
        "`https://t.me/channel_name/123`\n"
        "`https://t.me/c/1234567890/123`\n\n"
        "**Note:** I can fetch text, photos, videos, documents, and audio.",
        parse_mode=enums.ParseMode.MARKDOWN
    )

# ============= RUN CLIENTS =============
async def main():
    """Start both clients concurrently."""
    try:
        logger.info("🚀 Starting clients...")
        
        await user_client.start()
        logger.info("✅ User client started successfully")
        
        await bot_client.start()
        logger.info("✅ Bot client started successfully")
        
        logger.info("=" * 50)
        logger.info("🤖 @capturredzbot is running!")
        logger.info(f"👑 Owner ID: {AUTH}")
        logger.info(f"📢 Force Subscribe: {FORCESUB if FORCESUB else 'Disabled'}")
        logger.info("💡 Send /start to @capturredzbot on Telegram to test")
        logger.info("=" * 50)
        
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        raise
    finally:
        await user_client.stop()
        await bot_client.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        exit(1)
