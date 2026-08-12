import os
import re
import asyncio
import logging
import sys
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============ ENVIRONMENT VARIABLES ============
logger.info("=" * 60)
logger.info("🔍 Loading environment variables...")

API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SESSION = os.environ.get("SESSION")
AUTH = os.environ.get("AUTH")
FORCESUB = os.environ.get("FORCESUB")

logger.info(f"API_ID: {'✅ Loaded' if API_ID else '❌ Missing'}")
logger.info(f"API_HASH: {'✅ Loaded' if API_HASH else '❌ Missing'}")
logger.info(f"BOT_TOKEN: {'✅ Loaded' if BOT_TOKEN else '❌ Missing'}")
logger.info(f"SESSION: {'✅ Loaded' if SESSION else '❌ Missing'}")
logger.info(f"AUTH: {'✅ Loaded' if AUTH else '❌ Missing'}")
logger.info(f"FORCESUB: {FORCESUB if FORCESUB else 'Not Set'}")

missing = []
if not API_ID:
    missing.append("API_ID")
if not API_HASH:
    missing.append("API_HASH")
if not BOT_TOKEN:
    missing.append("BOT_TOKEN")
if not SESSION:
    missing.append("SESSION")
if not AUTH:
    missing.append("AUTH")

if missing:
    logger.error(f"❌ Missing variables: {', '.join(missing)}")
    sys.exit(1)

try:
    API_ID = int(API_ID)
    AUTH = int(AUTH)
except ValueError as e:
    logger.error(f"❌ Invalid number format: {e}")
    sys.exit(1)

logger.info("✅ All environment variables loaded successfully!")
logger.info("=" * 60)

# ============ INITIALIZE CLIENTS ============
try:
    user_client = Client(
        "user_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION,
        in_memory=True,
        sleep_threshold=30
    )
    
    bot_client = Client(
        "bot_session",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        sleep_threshold=30
    )
    logger.info("✅ Clients initialized")
except Exception as e:
    logger.error(f"❌ Client initialization error: {e}")
    logger.error("💡 Your SESSION may be invalid. Generate a new one!")
    sys.exit(1)

# ============ HELPER FUNCTIONS ============
async def is_subscribed(user_id):
    if not FORCESUB:
        return True
    try:
        member = await bot_client.get_chat_member(FORCESUB, user_id)
        return member.status in [
            enums.ChatMemberStatus.OWNER,
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.MEMBER
        ]
    except UserNotParticipant:
        return False
    except Exception:
        return True

def extract_link(link):
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        return match.group(1), int(match.group(2))
    return None, None

# ============ COMMANDS ============
@bot_client.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user = message.from_user
    user_name = user.first_name or "User"
    
    if FORCESUB and not await is_subscribed(user.id):
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCESUB}")],
            [InlineKeyboardButton("✅ Check Subscription", callback_data="check_sub")]
        ])
        await message.reply_text(
            f"🚫 **Access Restricted**\n\nDear {user_name},\nPlease join our channel first.",
            reply_markup=btn,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return
    
    await message.reply_text(
        f"👋 **Hello {user_name}!**\n\n"
        f"I can fetch content from protected Telegram channels.\n\n"
        f"**Send me a message link like:**\n"
        f"`https://t.me/channel_name/123`\n\n"
        f"I'll fetch the content for you!",
        parse_mode=enums.ParseMode.MARKDOWN
    )

@bot_client.on_callback_query(filters.regex("check_sub"))
async def check_sub_callback(client, query):
    if await is_subscribed(query.from_user.id):
        await query.message.edit_text("✅ **Verified!** Send me any link now.")
    else:
        await query.answer("❌ Please join the channel first!", show_alert=True)

@bot_client.on_message(filters.private & filters.text & ~filters.command(["start"]))
async def handle_message(client, message):
    user_id = message.from_user.id
    
    if FORCESUB and not await is_subscribed(user_id):
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCESUB}")]
        ])
        await message.reply_text("🚫 Join our channel first!", reply_markup=btn)
        return
    
    links = re.findall(r'https?://(?:t\.me|telegram\.me)/(?:c/)?[^/\s]+/\d+', message.text)
    
    if not links:
        await message.reply_text("❌ No valid Telegram link found!")
        return
    
    status = await message.reply_text(f"⏳ Processing {len(links)} link(s)...")
    
    success = 0
    for link in links:
        chat, msg_id = extract_link(link)
        if not chat or not msg_id:
            continue
        
        try:
            msg = await user_client.get_messages(chat, msg_id)
            if msg and not msg.empty:
                if msg.media:
                    await msg.copy(user_id, caption=msg.caption or "")
                else:
                    await bot_client.send_message(user_id, msg.text or "Empty")
                success += 1
        except Exception as e:
            logger.error(f"Error: {e}")
        await asyncio.sleep(0.5)
    
    await status.edit_text(f"✅ Done!\n✓ Success: {success}\n✗ Failed: {len(links) - success}")

# ============ START BOT ============
async def main():
    try:
        logger.info("🚀 Starting clients...")
        
        await user_client.start()
        logger.info("✅ User client started successfully")
        
        await bot_client.start()
        logger.info("✅ Bot client started successfully")
        
        logger.info("=" * 60)
        logger.info("🤖 @capturredzbot is running!")
        logger.info(f"👑 Owner ID: {AUTH}")
        logger.info(f"📢 Force Subscribe: {FORCESUB if FORCESUB else 'Disabled'}")
        logger.info("💡 Send /start to @capturredzbot on Telegram")
        logger.info("=" * 60)
        
        await asyncio.Event().wait()
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
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
        logger.error(f"❌ Error: {e}")
        sys.exit(1)
