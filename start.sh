#!/bin/bash
echo "🚀 Starting bot..."
echo "📋 Environment variables loaded:"
echo "API_ID: ${API_ID:0:5}..."
echo "API_HASH: ${API_HASH:0:5}..."
echo "BOT_TOKEN: ${BOT_TOKEN:0:10}..."
echo "SESSION: ${SESSION:0:10}..."
echo "AUTH: ${AUTH}"
echo "FORCESUB: ${FORCESUB:-Not Set}"
echo ""

# Run the bot
python -u bot.py
