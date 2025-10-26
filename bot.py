import logging
import os
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    CallbackContext,
    ConversationHandler
)
import requests
import json
import re

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = "8102196274:AAGwIogEbF9bmQSlTWK1NrLW0pmNu81CwkM"
PHONE_API_URL = "https://demon.taitanx.workers.dev/?mobile="
AADHAAR_API_URL = "https://family-members-n5um.vercel.app/fetch"

# Conversation states
NUMBER_INPUT, AADHAAR_INPUT = 1, 2

class InfoBot:
    def __init__(self):
        self.token = BOT_TOKEN
        self.phone_api_url = PHONE_API_URL
        self.aadhaar_api_url = AADHAAR_API_URL
    
    def validate_phone_number(self, number: str) -> bool:
        pattern = r'^[6-9]\d{9}$'
        return bool(re.match(pattern, number))
    
    def validate_aadhaar_number(self, number: str) -> bool:
        pattern = r'^\d{12}$'
        return bool(re.match(pattern, number))
    
    def create_main_keyboard(self):
        keyboard = [
            [KeyboardButton("📱 Phone Lookup"), KeyboardButton("🆔 Aadhaar Lookup")],
            [KeyboardButton("ℹ️ Help"), KeyboardButton("🚀 Quick Start")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    async def start(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        
        welcome_text = f"""
👋 Welcome {user.first_name}!

I'm *Multi-Info Bot* — Get information from multiple sources.

🧑‍💻 *Developer:* Rajdeb  
⚠️ *Note:* This bot is made for educational purposes only.  
Misuse of the bot or its data sources is strictly prohibited.  
The developer is *not responsible* for any illegal use.

Choose an option below or send:
- 📱 10-digit phone number  
- 🆔 12-digit Aadhaar number

Commands:
/phone - Phone number lookup  
/aadhaar - Aadhaar number lookup  
/help - Help guide
        """
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=self.create_main_keyboard()
        )
    
    async def help_command(self, update: Update, context: CallbackContext) -> None:
        help_text = """
📘 *Help Guide - Multi-Info Bot*

📱 *Phone Lookup:*
- Send 10-digit mobile number  
  Example: 9876543210

🆔 *Aadhaar Lookup:*
- Send 12-digit Aadhaar number  
  Example: 123456789012

Quick Commands:
/phone - Phone lookup  
/aadhaar - Aadhaar lookup  
/help - This message  

Or use the buttons below!
        """
        await update.message.reply_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=self.create_main_keyboard()
        )
    
    async def phone_command(self, update: Update, context: CallbackContext) -> int:
        await update.message.reply_text(
            "📱 Enter 10-digit mobile number:\nExample: 9876543210\n\nType /cancel to stop.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Cancel")]], resize_keyboard=True)
        )
        return NUMBER_INPUT
    
    async def process_phone_lookup(self, update: Update, phone_number: str) -> None:
        if not self.validate_phone_number(phone_number):
            await update.message.reply_text(
                "❌ Invalid phone number. Enter 10-digit number like 9876543210",
                reply_markup=self.create_main_keyboard()
            )
            return
        
        processing_msg = await update.message.reply_text(f"🔍 Searching phone: {phone_number}...")
        
        try:
            url = f"{self.phone_api_url}{phone_number}"
            logger.info(f"Calling Phone API: {url}")
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                api_data = response.json()
                json_response = json.dumps(api_data, indent=2, ensure_ascii=False)
                await processing_msg.edit_text(f"✅ Phone data found: {phone_number}")
                await update.message.reply_text(
                    f"```json\n{json_response}\n```", 
                    parse_mode='Markdown',
                    reply_markup=self.create_main_keyboard()
                )
            else:
                await processing_msg.edit_text(f"❌ API Error - Status: {response.status_code}")
            
        except Exception as e:
            await processing_msg.edit_text(f"❌ Error - {str(e)}")
    
    async def aadhaar_command(self, update: Update, context: CallbackContext) -> int:
        await update.message.reply_text(
            "🆔 Enter 12-digit Aadhaar number:\nExample: 123456789012\n\nType /cancel to stop.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Cancel")]], resize_keyboard=True)
        )
        return AADHAAR_INPUT
    
    async def process_aadhaar_lookup(self, update: Update, aadhaar_number: str) -> None:
        if not self.validate_aadhaar_number(aadhaar_number):
            await update.message.reply_text(
                "❌ Invalid Aadhaar number. Enter 12-digit number like 123456789012",
                reply_markup=self.create_main_keyboard()
            )
            return
        
        processing_msg = await update.message.reply_text(f"🔍 Searching Aadhaar: {aadhaar_number}...")
        
        try:
            url = f"{self.aadhaar_api_url}?aadhaar={aadhaar_number}&key=paidchx"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            api_data = response.json()
            json_response = json.dumps(api_data, indent=2, ensure_ascii=False)
            await processing_msg.edit_text(f"✅ Aadhaar data found: {aadhaar_number}")
            await update.message.reply_text(
                f"```json\n{json_response}\n```", 
                parse_mode='Markdown',
                reply_markup=self.create_main_keyboard()
            )
        except Exception as e:
            await processing_msg.edit_text("❌ Aadhaar API Error - Please try again later")
    
    async def handle_phone_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_phone_lookup(update, text)
        return ConversationHandler.END
    
    async def handle_aadhaar_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_aadhaar_lookup(update, text)
        return ConversationHandler.END
    
    async def handle_direct_input(self, update: Update, context: CallbackContext) -> None:
        user_input = update.message.text.strip()
        if self.validate_phone_number(user_input):
            await self.process_phone_lookup(update, user_input)
        elif self.validate_aadhaar_number(user_input):
            await self.process_aadhaar_lookup(update, user_input)
        else:
            await self.handle_button(update, context)
    
    async def handle_button(self, update: Update, context: CallbackContext) -> None:
        text = update.message.text
        if text == "📱 Phone Lookup":
            await self.phone_command(update, context)
        elif text == "🆔 Aadhaar Lookup":
            await self.aadhaar_command(update, context)
        elif text == "ℹ️ Help":
            await self.help_command(update, context)
        elif text == "🚀 Quick Start":
            await update.message.reply_text(
                "🚀 Quick Start:\n\n"
                "For Phone Lookup:\n• Send: 9876543210\n• Use: /phone\n\n"
                "For Aadhaar Lookup:\n• Send: 123456789012\n• Use: /aadhaar\n\n"
                "Or use the buttons!",
                reply_markup=self.create_main_keyboard()
            )
        elif text == "Cancel":
            await self.cancel(update, context)
        else:
            await update.message.reply_text(
                "Please send:\n• 10-digit Phone number\n• 12-digit Aadhaar number\n\nOr use the buttons below!",
                reply_markup=self.create_main_keyboard()
            )
    
    async def cancel(self, update: Update, context: CallbackContext) -> int:
        await update.message.reply_text(
            "❌ Operation cancelled.",
            reply_markup=self.create_main_keyboard()
        )
        return ConversationHandler.END


def main():
    bot = InfoBot()
    application = Application.builder().token(bot.token).build()
    
    phone_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('phone', bot.phone_command),
            MessageHandler(filters.Regex("^📱 Phone Lookup$"), bot.phone_command)
        ],
        states={
            NUMBER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_phone_input)]
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    aadhaar_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('aadhaar', bot.aadhaar_command),
            MessageHandler(filters.Regex("^🆔 Aadhaar Lookup$"), bot.aadhaar_command)
        ],
        states={
            AADHAAR_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_aadhaar_input)]
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)]
    )
    
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(phone_conv_handler)
    application.add_handler(aadhaar_conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_direct_input))
    
    print("🤖 Multi-Info Bot is running...")
    print("🧑‍💻 Developer: Rajdeb")
    print("⚠️ For educational purpose only — misuse is not allowed.")
    
    application.run_polling()

if __name__ == '__main__':
    main()