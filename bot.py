import os
import re
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# ============= ENVIRONMENT VARIABLES =============
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SESSION = os.environ.get("SESSION")          # Pyrogram session string for user client
AUTH = int(os.environ.get("AUTH"))            # Owner user ID
FORCESUB = os.environ.get("FORCESUB")         # Optional: channel username without '@'

# ============= INITIALIZE CLIENTS =============
# User client - uses your account to access restricted content
user_client = Client(
    "user",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION,
    in_memory=True
)

# Bot client - handles user interactions
bot_client = Client(
    "capturredzbot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ============= FORCE SUBSCRIPTION CHECK =============
async def is_subscribed(user_id: int) -> bool:
    """Check if user is subscribed to the force subscribe channel."""
    if not FORCESUB:
        return True
    try:
        await bot_client.get_chat_member(FORCESUB, user_id)
        return True
    except UserNotParticipant:
        return False
    except Exception:
        return True  # If bot can't check, allow access

# ============= BOT COMMANDS =============
@bot_client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id

    # Force subscribe check
    if FORCESUB and not await is_subscribed(user_id):
        btn = [
            [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCESUB}")],
            [InlineKeyboardButton("✅ Check Subscription", callback_data="check_sub")]
        ]
        await message.reply_text(
            f"**🚫 Access Restricted**\n\n"
            f"Dear {message.from_user.first_name},\n"
            f"You must join our channel to use this bot.\n\n"
            f"👆 Tap the button below to join, then check subscription.",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    await message.reply_text(
        f"**👋 Hello {message.from_user.first_name}!**\n\n"
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
            "✅ **Subscription verified!**\n\nYou can now use the bot. Send me any Telegram message link!",
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

    # Expect: /batch link1 link2 link3 ...
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Usage: `/batch link1 link2 link3 ...`")
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
        await asyncio.sleep(0.5)  # Avoid flood wait

    await status_msg.edit_text(
        f"✅ **Batch Complete**\n\n"
        f"✓ Successful: {processed}\n"
        f"✗ Failed: {failed}\n"
        f"Total: {len(links)}"
    )

# ============= LINK PROCESSING =============
def extract_link_info(link: str) -> tuple:
    """
    Extract channel/chat and message ID from a Telegram link.
    Returns (chat_identifier, message_id) or (None, None) on failure.
    """
    # Pattern for: https://t.me/username/123 or https://telegram.me/c/1234567890/123
    pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?([^/]+)/(\d+)'
    match = re.search(pattern, link)
    if match:
        return match.group(1), int(match.group(2))
    return None, None

async def process_single_link(link: str, user_id: int) -> bool:
    """Fetch a single message via user_client and forward/send it via bot_client."""
    chat_identifier, msg_id = extract_link_info(link)
    if not chat_identifier or not msg_id:
        return False

    try:
        # Use user client to get the message (bypasses restrictions)
        message = await user_client.get_messages(chat_identifier, msg_id)

        if not message or message.empty:
            return False

        # Send the message using the bot client
        await message.copy(
            chat_id=user_id,
            caption=message.caption if hasattr(message, 'caption') else None,
            parse_mode=enums.ParseMode.HTML if message.caption else None
        )
        return True

    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await process_single_link(link, user_id)  # Retry after waiting
    except Exception as e:
        logging.error(f"Error processing {link}: {e}")
        return False

@bot_client.on_message(filters.private & filters.text & ~filters.command(["start", "batch"]))
async def handle_message(client, message):
    """Handle regular messages containing links."""
    user_id = message.from_user.id

    # Force subscribe check
    if FORCESUB and not await is_subscribed(user_id):
        btn = [[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCESUB}")]]
        await message.reply_text(
            f"**🚫 Access Restricted**\n\nPlease join our channel first.",
            reply_markup=InlineKeyboardMarkup(btn),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        return

    text = message.text
    # Extract all links from the message
    link_pattern = r'https?://(?:t\.me|telegram\.me)/(?:c/)?[^/\s]+/\d+'
    links = re.findall(link_pattern, text)

    if not links:
        await message.reply_text(
            "❌ No valid Telegram message links found.\n"
            "Send a link like: `https://t.me/channel_name/123`"
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
        f"Send more links anytime!"
    )

# ============= BOT ADMIN COMMANDS =============
@bot_client.on_message(filters.command("stats") & filters.user(AUTH))
async def stats_command(client, message):
    await message.reply_text("📊 Bot is running smoothly! (Stats feature coming soon)")

@bot_client.on_message(filters.command("broadcast") & filters.user(AUTH))
async def broadcast_command(client, message):
    """Owner-only broadcast (requires additional setup for user list)."""
    await message.reply_text("📢 Broadcast feature - implement with database if needed.")

# ============= RUN CLIENTS =============
async def main():
    """Start both clients concurrently."""
    # Start both clients
    await user_client.start()
    await bot_client.start()

    logging.info("🤖 Bot is running!")
    logging.info(f"👑 Owner ID: {AUTH}")
    logging.info(f"📢 Force Subscribe: {FORCESUB if FORCESUB else 'Disabled'}")

    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
