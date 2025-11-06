import logging
import os
import sys
import json
import re
import asyncio
import datetime
import sqlite3
from urllib.parse import quote
from typing import Dict, List

# Try to import required packages
try:
    import requests
except ImportError:
    print("Installing requests module...")
    os.system("pip install requests")
    import requests

try:
    from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
    from telegram.ext import (
        Application, 
        CommandHandler, 
        MessageHandler, 
        filters, 
        CallbackContext,
        ConversationHandler
    )
except ImportError:
    print("Installing python-telegram-bot module...")
    os.system("pip install python-telegram-bot")
    from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
    from telegram.ext import (
        Application, 
        CommandHandler, 
        MessageHandler, 
        filters, 
        CallbackContext,
        ConversationHandler
    )

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = "8401166496:AAGt5nHdc2Rf9x71H4X5fwB7tMS4TPSN_sk"
ADMIN_ID = 5840922366  # Your admin user ID

# API Endpoints
API_CONFIG = {
    "phone": {
        "url": "https://demon.taitanx.workers.dev/?mobile={query}",
        "name": "📱 Phone Lookup",
        "command": "/phone",
        "example": "9876543210",
        "pattern": r'^[6-9]\d{9}$',
        "credits": 1
    },
    "aadhaar": {
        "url": "https://family-members-n5um.vercel.app/fetch?aadhaar={query}&key=paidchx",
        "name": "🆔 Aadhaar Lookup", 
        "command": "/aadhaar",
        "example": "123456789012",
        "pattern": r'^\d{12}$',
        "credits": 1
    },
    "vehicle": {
        "url": "https://vehicleinfo-v2.zerovault.workers.dev/?vehicle_number={query}",
        "name": "🚗 Vehicle Lookup",
        "command": "/vehicle",
        "example": "KA04EQ4521",
        "pattern": r'^[A-Z]{2}\d{1,2}[A-Z]{1,2}\d{1,4}$',
        "credits": 1
    },
    "ifsc": {
        "url": "https://ifsc.razorpay.com/{query}",
        "name": "🏦 IFSC Lookup",
        "command": "/ifsc", 
        "example": "SBIN0000001",
        "pattern": r'^[A-Z]{4}0[A-Z0-9]{6}$',
        "credits": 1
    },
    "ip": {
        "url": "https://ip-info.bjcoderx.workers.dev/?ip={query}",
        "name": "🌐 IP Lookup",
        "command": "/ip",
        "example": "149.154.167.91",
        "pattern": r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$',
        "credits": 1
    },
    "pincode": {
        "url": "http://www.postalpincode.in/api/pincode/{query}",
        "name": "📮 Pincode Lookup",
        "command": "/pincode",
        "example": "110006",
        "pattern": r'^\d{6}$',
        "credits": 1
    }
}

# Conversation states
(
    PHONE_INPUT, AADHAAR_INPUT, VEHICLE_INPUT, 
    IFSC_INPUT, IP_INPUT, PINCODE_INPUT,
    ADMIN_ADD_CREDITS, ADMIN_REMOVE_CREDITS, ADMIN_ULTIMATE_CREDITS,
    ADMIN_BAN_USER, ADMIN_UNBAN_USER, ADMIN_PROTECT_NUMBER
) = range(12)

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('users.db', check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        """Create necessary database tables"""
        cursor = self.conn.cursor()
        
        # Drop old tables if they exist to recreate with new schema
        cursor.execute('DROP TABLE IF EXISTS users')
        cursor.execute('DROP TABLE IF EXISTS search_history')
        cursor.execute('DROP TABLE IF EXISTS protected_numbers')
        
        # Users table with all required columns
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                credits INTEGER DEFAULT 0,
                total_searches INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT FALSE,
                ban_reason TEXT DEFAULT '',
                banned_by INTEGER DEFAULT NULL,
                ban_date TIMESTAMP DEFAULT NULL,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Search history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service_type TEXT,
                query TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Protected numbers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS protected_numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_number TEXT UNIQUE,
                protected_by INTEGER,
                protected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reason TEXT DEFAULT '',
                FOREIGN KEY (protected_by) REFERENCES users (user_id)
            )
        ''')
        
        self.conn.commit()
        print("✅ Database tables created successfully")
    
    def get_user(self, user_id: int):
        """Get user data"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return cursor.fetchone()
    
    def create_user(self, user_id: int, username: str, first_name: str, last_name: str = ""):
        """Create new user"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, credits)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, 5))  # Give 5 free credits on start
        self.conn.commit()
    
    def update_user_activity(self, user_id: int):
        """Update user's last active time"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def get_credits(self, user_id: int) -> int:
        """Get user's credits"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT credits FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0
    
    def is_user_banned(self, user_id: int) -> bool:
        """Check if user is banned"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else False
    
    def ban_user(self, user_id: int, admin_id: int, reason: str = "No reason provided"):
        """Ban a user"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET is_banned = TRUE, ban_reason = ?, banned_by = ?, ban_date = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        ''', (reason, admin_id, user_id))
        self.conn.commit()
    
    def unban_user(self, user_id: int):
        """Unban a user"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE users 
            SET is_banned = FALSE, ban_reason = '', banned_by = NULL, ban_date = NULL 
            WHERE user_id = ?
        ''', (user_id,))
        self.conn.commit()
    
    def get_banned_users(self):
        """Get all banned users"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE is_banned = TRUE ORDER BY ban_date DESC')
        return cursor.fetchall()
    
    def is_number_protected(self, phone_number: str) -> bool:
        """Check if phone number is protected"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT id FROM protected_numbers WHERE phone_number = ?', (phone_number,))
        return cursor.fetchone() is not None
    
    def protect_number(self, phone_number: str, admin_id: int, reason: str = "Admin protection"):
        """Protect a phone number"""
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO protected_numbers (phone_number, protected_by, reason)
                VALUES (?, ?, ?)
            ''', (phone_number, admin_id, reason))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # Number already protected
    
    def unprotect_number(self, phone_number: str):
        """Remove protection from a phone number"""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM protected_numbers WHERE phone_number = ?', (phone_number,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_protected_numbers(self):
        """Get all protected numbers"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT pn.phone_number, pn.reason, pn.protected_date, u.username 
            FROM protected_numbers pn
            LEFT JOIN users u ON pn.protected_by = u.user_id
            ORDER BY pn.protected_date DESC
        ''')
        return cursor.fetchall()
    
    def get_protected_numbers_count(self) -> int:
        """Get count of protected numbers"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM protected_numbers')
        return cursor.fetchone()[0]
    
    def deduct_credits(self, user_id: int, amount: int) -> bool:
        """Deduct credits from user"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET credits = credits - ? WHERE user_id = ? AND credits >= ?', 
                      (amount, user_id, amount))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def add_credits(self, user_id: int, amount: int):
        """Add credits to user"""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE users SET credits = credits + ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()
    
    def add_search_history(self, user_id: int, service_type: str, query: str):
        """Add search to history"""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO search_history (user_id, service_type, query)
            VALUES (?, ?, ?)
        ''', (user_id, service_type, query))
        
        # Update total searches
        cursor.execute('UPDATE users SET total_searches = total_searches + 1 WHERE user_id = ?', (user_id,))
        self.conn.commit()
    
    def get_all_users(self):
        """Get all users"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users ORDER BY joined_date DESC')
        return cursor.fetchall()
    
    def get_search_stats(self):
        """Get search statistics"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT service_type, COUNT(*) as count 
            FROM search_history 
            GROUP BY service_type 
            ORDER BY count DESC
        ''')
        return cursor.fetchall()
    
    def get_total_users(self) -> int:
        """Get total number of users"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        return cursor.fetchone()[0]
    
    def get_banned_users_count(self) -> int:
        """Get total number of banned users"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users WHERE is_banned = TRUE')
        return cursor.fetchone()[0]
    
    def get_total_searches(self) -> int:
        """Get total number of searches"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM search_history')
        return cursor.fetchone()[0]

class ProfessionalInfoBot:
    def __init__(self):
        self.token = BOT_TOKEN
        self.admin_id = ADMIN_ID
        self.api_config = API_CONFIG
        self.db = Database()
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id == self.admin_id
    
    def validate_input(self, query_type: str, input_text: str) -> bool:
        """Validate input based on type"""
        pattern = self.api_config[query_type]["pattern"]
        return bool(re.match(pattern, input_text, re.IGNORECASE))
    
    def create_main_keyboard(self, user_id: int):
        """Create professional main menu keyboard"""
        credits = self.db.get_credits(user_id)
        
        keyboard = [
            [
                KeyboardButton("📱 Phone"), 
                KeyboardButton("🆔 Aadhaar"),
                KeyboardButton("🚗 Vehicle")
            ],
            [
                KeyboardButton("🏦 IFSC"), 
                KeyboardButton("🌐 IP Lookup"),
                KeyboardButton("📮 Pincode")
            ],
            [
                KeyboardButton("💎 My Credits"),
                KeyboardButton("🛒 Buy Credits"),
                KeyboardButton("ℹ️ Help")
            ]
        ]
        
        # Add admin panel for admin users
        if self.is_admin(user_id):
            keyboard.append([KeyboardButton("👑 Admin Panel")])
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    def create_admin_keyboard(self):
        """Create admin panel keyboard"""
        keyboard = [
            [KeyboardButton("📊 User Statistics"), KeyboardButton("👥 All Users")],
            [KeyboardButton("➕ Add Credits"), KeyboardButton("➖ Remove Credits")],
            [KeyboardButton("⚡ Ultimate Credits"), KeyboardButton("📈 Search Stats")],
            [KeyboardButton("🔨 Ban User"), KeyboardButton("🔓 Unban User")],
            [KeyboardButton("🛡️ Protect Number"), KeyboardButton("🛡️ Protected Numbers")],
            [KeyboardButton("🚫 Banned Users"), KeyboardButton("🏠 Main Menu")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    def create_cancel_keyboard(self):
        """Create cancel keyboard for conversations"""
        return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancel")]], resize_keyboard=True)
    
    async def start(self, update: Update, context: CallbackContext) -> None:
        """Send professional welcome message"""
        user = update.effective_user
        
        # Check if user is banned
        if self.db.is_user_banned(user.id):
            banned_user = self.db.get_user(user.id)
            ban_reason = banned_user[7] if banned_user else "No reason provided"
            ban_date = banned_user[9] if banned_user else "Unknown"
            
            ban_text = f"""
🚫 **ACCOUNT BANNED**

❌ **Your account has been banned from using this bot.**

📋 **Reason:** {ban_reason}
📅 **Banned on:** {ban_date}

🔍 **If you think this is a mistake, contact the administrator.**
            """
            await update.message.reply_text(ban_text, parse_mode='Markdown')
            return
        
        # Create or update user in database
        self.db.create_user(user.id, user.username, user.first_name, user.last_name or "")
        self.db.update_user_activity(user.id)
        
        credits = self.db.get_credits(user.id)
        
        welcome_text = f"""
✨ **Welcome {user.first_name}!** ✨

🤖 **Professional Multi-Info Bot**
*Your all-in-one information lookup solution*

💎 **Available Credits:** `{credits}`
*Each search costs 1 credit*

🔍 **Available Lookups:**
• 📱 **Phone Numbers** - 10-digit mobile numbers
• 🆔 **Aadhaar Cards** - 12-digit Aadhaar numbers  
• 🚗 **Vehicle Info** - Vehicle registration numbers
• 🏦 **Bank IFSC** - 11-character IFSC codes
• 🌐 **IP Addresses** - IPv4 address information
• 📮 **Pincode Info** - 6-digit postal pincode details

💡 **Quick Usage:**
Simply send any number or use the buttons below!

⚡ **Commands:**
/credits - Check your credits
/help - Detailed guide

*Choose an option below to get started!*
        """
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=self.create_main_keyboard(user.id),
            parse_mode='Markdown'
        )
    
    async def help_command(self, update: Update, context: CallbackContext) -> None:
        """Send comprehensive help guide"""
        user = update.effective_user
        
        # Check if user is banned
        if self.db.is_user_banned(user.id):
            return
        
        help_text = f"""
📚 **Professional Help Guide** 📚

🔍 **Available Lookup Services:**

📱 **Phone Number Lookup** - 1 credit
• Format: 10-digit number
• Example: `9876543210`

🆔 **Aadhaar Lookup** - 1 credit
• Format: 12-digit number
• Example: `123456789012`

🚗 **Vehicle Information** - 1 credit
• Format: Vehicle registration
• Example: `KA04EQ4521`

🏦 **IFSC Bank Details** - 1 credit
• Format: 11-character code
• Example: `SBIN0000001`

🌐 **IP Address Information** - 1 credit
• Format: IPv4 address
• Example: `149.154.167.91`

📮 **Pincode Information** - 1 credit
• Format: 6-digit pincode
• Example: `110006`

💎 **Credits System:**
• Each search costs 1 credit
• Check credits with /credits
• Buy more credits with "🛒 Buy Credits"

🛒 **Buy Credits:**
Contact @DARK_RAJDEB to purchase credits:
• 50 credits: ₹100
• 100 credits: ₹180  
• 200 credits: ₹300
• 500 credits: ₹600

⚡ **Quick Tips:**
• Send numbers directly without commands
• Use buttons for easy navigation
• All data returned in JSON format
• Cancel anytime with /cancel

👑 **Admin:** @DARK_RAJDEB
        """
        
        await update.message.reply_text(
            help_text,
            reply_markup=self.create_main_keyboard(user.id),
            parse_mode='Markdown'
        )
    
    async def credits_command(self, update: Update, context: CallbackContext) -> None:
        """Show user credits"""
        user = update.effective_user
        
        # Check if user is banned
        if self.db.is_user_banned(user.id):
            return
        
        credits = self.db.get_credits(user.id)
        
        credits_text = f"""
💎 **Your Credits**

🆔 **User:** {user.first_name}
💳 **Available Credits:** `{credits}`
🔍 **Cost per search:** `1 credit`

📊 **Usage:**
• Phone Lookup: 1 credit
• Aadhaar Lookup: 1 credit  
• Vehicle Lookup: 1 credit
• IFSC Lookup: 1 credit
• IP Lookup: 1 credit
• Pincode Lookup: 1 credit

🛒 **Need more credits?**
Click "🛒 Buy Credits" or contact @DARK_RAJDEB

💳 **Pricing:**
• 50 credits: ₹100
• 100 credits: ₹180
• 200 credits: ₹300  
• 500 credits: ₹600
        """
        
        await update.message.reply_text(
            credits_text,
            reply_markup=self.create_main_keyboard(user.id),
            parse_mode='Markdown'
        )
    
    async def buy_credits(self, update: Update, context: CallbackContext) -> None:
        """Show buy credits information"""
        user = update.effective_user
        
        # Check if user is banned
        if self.db.is_user_banned(user.id):
            return
        
        buy_text = f"""
🛒 **Buy Credits**

💎 **Credit Packages Available:**

💰 **50 Credits** - ₹100
• Perfect for light users
• 50 searches

💰 **100 Credits** - ₹180  
• Great for regular users
• 100 searches (Save ₹20)

💰 **200 Credits** - ₹300
• Best value for money
• 200 searches (Save ₹100)

💰 **500 Credits** - ₹600
• Ultimate package
• 500 searches (Save ₹400)

📲 **How to Buy:**
1. Contact @RAJDEBgsm
2. Choose your package
3. Make payment via UPI/Google Pay/Paytm
4. Receive credits instantly!

💳 **Payment Methods:**
• Google Pay
• PhonePe  
• Paytm
• UPI
• Bank Transfer

⚡ **Instant Activation**
Credits added immediately after payment!

👑 **Contact Admin:** @RAJDEBgsm
        """
        
        await update.message.reply_text(
            buy_text,
            reply_markup=self.create_main_keyboard(user.id),
            parse_mode='Markdown'
        )
    
    # Generic lookup handler
    async def start_lookup_conversation(self, update: Update, context: CallbackContext, lookup_type: str) -> int:
        """Start generic lookup conversation"""
        user = update.effective_user
        
        # Check if user is banned
        if self.db.is_user_banned(user.id):
            await update.message.reply_text("🚫 Your account is banned from using this bot.")
            return ConversationHandler.END
        
        credits = self.db.get_credits(user.id)
        
        if credits < 1:
            await update.message.reply_text(
                f"❌ **Insufficient Credits**\n\nYou have `{credits}` credits. You need `1` credit for this search.\n\nClick '🛒 Buy Credits' or contact @DARK_RAJDEB for more credits.",
                reply_markup=self.create_main_keyboard(user.id),
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        
        config = self.api_config[lookup_type]
        
        prompt_text = f"""
🔍 **{config['name']}**

📝 *Please enter {lookup_type} number:*
**Example:** `{config['example']}`

💎 **Credits required:** `1 credit`
💳 **Your credits:** `{credits}`

⚡ *Just type the number or /cancel to stop*
        """
        
        await update.message.reply_text(
            prompt_text,
            reply_markup=self.create_cancel_keyboard(),
            parse_mode='Markdown'
        )
        
        # Return appropriate state
        state_map = {
            'phone': PHONE_INPUT,
            'aadhaar': AADHAAR_INPUT,
            'vehicle': VEHICLE_INPUT,
            'ifsc': IFSC_INPUT,
            'ip': IP_INPUT,
            'pincode': PINCODE_INPUT
        }
        return state_map[lookup_type]
    
    async def process_lookup(self, update: Update, query: str, lookup_type: str) -> None:
        """Process generic lookup and return results"""
        user = update.effective_user
        
        # Check if user is banned
        if self.db.is_user_banned(user.id):
            await update.message.reply_text("🚫 Your account is banned from using this bot.")
            return
        
        # Check if phone number is protected (for phone lookup only)
        if lookup_type == 'phone' and self.db.is_number_protected(query):
            await update.message.reply_text(
                f"🛡️ **Protected Number**\n\n❌ The phone number `{query}` is protected and cannot be searched.\n\nThis number has been secured by admin for privacy reasons.",
                reply_markup=self.create_main_keyboard(user.id),
                parse_mode='Markdown'
            )
            return
        
        config = self.api_config[lookup_type]
        
        # Check credits
        if not self.db.deduct_credits(user.id, 1):
            await update.message.reply_text(
                f"❌ **Insufficient Credits**\n\nYou don't have enough credits for this search.\n\nClick '🛒 Buy Credits' or contact @DARK_RAJDEB for more credits.",
                reply_markup=self.create_main_keyboard(user.id),
                parse_mode='Markdown'
            )
            return
        
        # Validate input
        if not self.validate_input(lookup_type, query):
            # Refund credits for invalid input
            self.db.add_credits(user.id, 1)
            error_text = f"""
❌ **Invalid Input**

Please enter a valid {lookup_type} number:
**Format:** `{config['example']}`
            """
            await update.message.reply_text(
                error_text,
                reply_markup=self.create_main_keyboard(user.id),
                parse_mode='Markdown'
            )
            return
        
        # Show processing message
        processing_msg = await update.message.reply_text(
            f"🔍 *Searching {lookup_type}:* `{query}`\n\n⏳ *Please wait...*",
            parse_mode='Markdown'
        )
        
        try:
            # Make API request
            url = config['url'].format(query=quote(query.upper() if lookup_type in ['vehicle', 'ifsc'] else query))
            logger.info(f"API Call: {url}")
            
            headers = {
                'User-Agent': 'ProfessionalInfoBot/2.1',
                'Accept': 'application/json'
            }
            
            # Special handling for pincode API
            if lookup_type == 'pincode':
                headers['Referer'] = 'http://www.postalpincode.in/'
            
            response = requests.get(url, headers=headers, timeout=15)
            logger.info(f"API Response: {response.status_code}")
            
            if response.status_code == 200:
                # Handle different API response formats
                if lookup_type == 'pincode':
                    api_data = response.json()
                else:
                    api_data = response.json()
                
                # Add to search history
                self.db.add_search_history(user.id, lookup_type, query)
                
                # Format JSON response
                json_response = json.dumps(api_data, indent=2, ensure_ascii=False)
                
                # Success message
                remaining_credits = self.db.get_credits(user.id)
                success_text = f"""
✅ **{config['name']} Successful**

📋 **Query:** `{query}`
💎 **Credits deducted:** `1`
💳 **Remaining credits:** `{remaining_credits}`
📊 **Results Below:**
                """
                
                await processing_msg.edit_text(success_text, parse_mode='Markdown')
                
                # Send JSON results
                if len(json_response) > 4000:
                    # Split large responses
                    for i in range(0, len(json_response), 4000):
                        chunk = json_response[i:i+4000]
                        await update.message.reply_text(
                            f"```json\n{chunk}\n```",
                            parse_mode='MarkdownV2'
                        )
                else:
                    await update.message.reply_text(
                        f"```json\n{json_response}\n```",
                        parse_mode='MarkdownV2',
                        reply_markup=self.create_main_keyboard(user.id)
                    )
                    
            else:
                # Refund credits for API error
                self.db.add_credits(user.id, 1)
                error_text = f"""
❌ **API Error**

🔍 **Lookup:** {config['name']}
📡 **Status:** {response.status_code}
💡 **Solution:** Try again later
                """
                await processing_msg.edit_text(
                    error_text,
                    reply_markup=self.create_main_keyboard(user.id),
                    parse_mode='Markdown'
                )
                
        except requests.exceptions.Timeout:
            # Refund credits for timeout
            self.db.add_credits(user.id, 1)
            error_text = f"""
⏰ **Request Timeout**

🔍 **Lookup:** {config['name']}
❌ **Error:** API took too long to respond
💡 **Solution:** Try again in a moment
            """
            await processing_msg.edit_text(
                error_text,
                reply_markup=self.create_main_keyboard(user.id),
                parse_mode='Markdown'
            )
            
        except requests.exceptions.RequestException as e:
            # Refund credits for network error
            self.db.add_credits(user.id, 1)
            error_text = f"""
🌐 **Network Error**

🔍 **Lookup:** {config['name']}
❌ **Error:** {str(e)}
💡 **Solution:** Check connection and retry
            """
            await processing_msg.edit_text(
                error_text,
                reply_markup=self.create_main_keyboard(user.id),
                parse_mode='Markdown'
            )
            
        except Exception as e:
            # Refund credits for unexpected error
            self.db.add_credits(user.id, 1)
            error_text = f"""
⚠️ **Unexpected Error**

🔍 **Lookup:** {config['name']}
❌ **Error:** {str(e)}
💡 **Solution:** Contact administrator
            """
            await processing_msg.edit_text(
                error_text,
                reply_markup=self.create_main_keyboard(user.id),
                parse_mode='Markdown'
            )
    
    # Individual command handlers
    async def phone_command(self, update: Update, context: CallbackContext) -> int:
        return await self.start_lookup_conversation(update, context, 'phone')
    
    async def aadhaar_command(self, update: Update, context: CallbackContext) -> int:
        return await self.start_lookup_conversation(update, context, 'aadhaar')
    
    async def vehicle_command(self, update: Update, context: CallbackContext) -> int:
        return await self.start_lookup_conversation(update, context, 'vehicle')
    
    async def ifsc_command(self, update: Update, context: CallbackContext) -> int:
        return await self.start_lookup_conversation(update, context, 'ifsc')
    
    async def ip_command(self, update: Update, context: CallbackContext) -> int:
        return await self.start_lookup_conversation(update, context, 'ip')
    
    async def pincode_command(self, update: Update, context: CallbackContext) -> int:
        return await self.start_lookup_conversation(update, context, 'pincode')
    
    # Input handlers
    async def handle_phone_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_lookup(update, text, 'phone')
        return ConversationHandler.END
    
    async def handle_aadhaar_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_lookup(update, text, 'aadhaar')
        return ConversationHandler.END
    
    async def handle_vehicle_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_lookup(update, text, 'vehicle')
        return ConversationHandler.END
    
    async def handle_ifsc_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_lookup(update, text, 'ifsc')
        return ConversationHandler.END
    
    async def handle_ip_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_lookup(update, text, 'ip')
        return ConversationHandler.END
    
    async def handle_pincode_input(self, update: Update, context: CallbackContext) -> int:
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        await self.process_lookup(update, text, 'pincode')
        return ConversationHandler.END
    
    # Admin functions
    async def admin_panel(self, update: Update, context: CallbackContext) -> None:
        """Show admin panel"""
        if not self.is_admin(update.effective_user.id):
            await update.message.reply_text("❌ Access denied.")
            return
        
        total_users = self.db.get_total_users()
        banned_users = self.db.get_banned_users_count()
        protected_numbers = self.db.get_protected_numbers_count()
        
        stats_text = f"""
👑 **Admin Panel**

📊 **Statistics:**
• Total Users: `{total_users}`
• Banned Users: `{banned_users}`
• Protected Numbers: `{protected_numbers}`
• Total Searches: `{self.db.get_total_searches()}`
• Active Services: `{len(API_CONFIG)}`

🛠 **Admin Tools:**
• User Statistics & Management
• Credit Management System  
• Ban/Unban System
• Number Protection System
• Search Analytics

*Choose an option below:*
        """
        
        await update.message.reply_text(
            stats_text,
            reply_markup=self.create_admin_keyboard(),
            parse_mode='Markdown'
        )
    
    async def admin_user_stats(self, update: Update, context: CallbackContext) -> None:
        """Show user statistics"""
        if not self.is_admin(update.effective_user.id):
            return
        
        total_users = self.db.get_total_users()
        total_searches = self.db.get_total_searches()
        banned_users = self.db.get_banned_users_count()
        protected_numbers = self.db.get_protected_numbers_count()
        search_stats = self.db.get_search_stats()
        
        stats_text = f"""
📊 **User Statistics**

👥 **Total Users:** `{total_users}`
🚫 **Banned Users:** `{banned_users}`
✅ **Active Users:** `{total_users - banned_users}`
🛡️ **Protected Numbers:** `{protected_numbers}`
🔍 **Total Searches:** `{total_searches}`
📈 **Average per user:** `{total_searches/total_users if total_users > 0 else 0:.1f}`

📋 **Search Distribution:**
"""
        
        for service_type, count in search_stats:
            service_name = API_CONFIG.get(service_type, {}).get('name', service_type)
            stats_text += f"• {service_name}: `{count}`\n"
        
        await update.message.reply_text(
            stats_text,
            reply_markup=self.create_admin_keyboard(),
            parse_mode='Markdown'
        )
    
    async def admin_all_users(self, update: Update, context: CallbackContext) -> None:
        """Show all users"""
        if not self.is_admin(update.effective_user.id):
            return
        
        users = self.db.get_all_users()
        
        if not users:
            await update.message.reply_text("No users found.")
            return
        
        users_text = "👥 **All Users**\n\n"
        
        for user in users[:10]:  # Show first 10 users
            user_id, username, first_name, last_name, credits, total_searches, is_banned, ban_reason, banned_by, ban_date, joined_date, last_active = user
            status = "🚫 BANNED" if is_banned else "✅ ACTIVE"
            users_text += f"🆔 **User:** {first_name} {last_name or ''} ({status})\n"
            users_text += f"📛 **Username:** @{username or 'N/A'}\n"
            users_text += f"💎 **Credits:** `{credits}`\n"
            users_text += f"🔍 **Searches:** `{total_searches}`\n"
            users_text += f"📅 **Joined:** `{joined_date[:10]}`\n\n"
        
        if len(users) > 10:
            users_text += f"... and {len(users) - 10} more users"
        
        await update.message.reply_text(
            users_text,
            reply_markup=self.create_admin_keyboard(),
            parse_mode='Markdown'
        )
    
    async def admin_add_credits(self, update: Update, context: CallbackContext) -> int:
        """Start add credits conversation"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        await update.message.reply_text(
            "➕ **Add Credits**\n\nSend user ID and amount in format:\n`user_id amount`\n\nExample: `123456789 10`",
            reply_markup=self.create_cancel_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_ADD_CREDITS
    
    async def admin_remove_credits(self, update: Update, context: CallbackContext) -> int:
        """Start remove credits conversation"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        await update.message.reply_text(
            "➖ **Remove Credits**\n\nSend user ID and amount in format:\n`user_id amount`\n\nExample: `123456789 5`",
            reply_markup=self.create_cancel_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_REMOVE_CREDITS
    
    async def admin_ultimate_credits(self, update: Update, context: CallbackContext) -> int:
        """Start ultimate credits conversation"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        await update.message.reply_text(
            "⚡ **Ultimate Credits**\n\nSend user ID to give unlimited credits:\n`user_id`\n\nExample: `123456789`",
            reply_markup=self.create_cancel_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_ULTIMATE_CREDITS
    
    async def admin_ban_user(self, update: Update, context: CallbackContext) -> int:
        """Start ban user conversation"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🔨 **Ban User**\n\nSend user ID and reason in format:\n`user_id reason`\n\nExample: `123456789 Spamming`",
            reply_markup=self.create_cancel_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_BAN_USER
    
    async def admin_unban_user(self, update: Update, context: CallbackContext) -> int:
        """Start unban user conversation"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🔓 **Unban User**\n\nSend user ID to unban:\n`user_id`\n\nExample: `123456789`",
            reply_markup=self.create_cancel_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_UNBAN_USER
    
    async def admin_protect_number(self, update: Update, context: CallbackContext) -> int:
        """Start protect number conversation"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        await update.message.reply_text(
            "🛡️ **Protect Number**\n\nSend phone number to protect:\n`phone_number`\n\nExample: `9876543210`",
            reply_markup=self.create_cancel_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_PROTECT_NUMBER
    
    async def admin_protected_numbers(self, update: Update, context: CallbackContext) -> None:
        """Show protected numbers"""
        if not self.is_admin(update.effective_user.id):
            return
        
        protected_numbers = self.db.get_protected_numbers()
        
        if not protected_numbers:
            await update.message.reply_text("No protected numbers found.")
            return
        
        protected_text = "🛡️ **Protected Numbers**\n\n"
        
        for number_data in protected_numbers[:10]:  # Show first 10 protected numbers
            phone_number, reason, protected_date, protected_by = number_data
            protected_text += f"📱 **Number:** `{phone_number}`\n"
            protected_text += f"📋 **Reason:** {reason}\n"
            protected_text += f"👤 **Protected by:** {protected_by or 'Admin'}\n"
            protected_text += f"📅 **Protected on:** {protected_date[:10] if protected_date else 'Unknown'}\n\n"
        
        if len(protected_numbers) > 10:
            protected_text += f"... and {len(protected_numbers) - 10} more protected numbers"
        
        await update.message.reply_text(
            protected_text,
            reply_markup=self.create_admin_keyboard(),
            parse_mode='Markdown'
        )
    
    async def admin_banned_users(self, update: Update, context: CallbackContext) -> None:
        """Show banned users"""
        if not self.is_admin(update.effective_user.id):
            return
        
        banned_users = self.db.get_banned_users()
        
        if not banned_users:
            await update.message.reply_text("No banned users found.")
            return
        
        banned_text = "🚫 **Banned Users**\n\n"
        
        for user in banned_users[:10]:  # Show first 10 banned users
            user_id, username, first_name, last_name, credits, total_searches, is_banned, ban_reason, banned_by, ban_date, joined_date, last_active = user
            banned_text += f"🆔 **User:** {first_name} {last_name or ''}\n"
            banned_text += f"📛 **Username:** @{username or 'N/A'}\n"
            banned_text += f"📋 **Ban Reason:** {ban_reason}\n"
            banned_text += f"📅 **Banned on:** {ban_date[:10] if ban_date else 'Unknown'}\n"
            banned_text += f"🔍 **Total Searches:** `{total_searches}`\n\n"
        
        if len(banned_users) > 10:
            banned_text += f"... and {len(banned_users) - 10} more banned users"
        
        await update.message.reply_text(
            banned_text,
            reply_markup=self.create_admin_keyboard(),
            parse_mode='Markdown'
        )
    
    async def handle_admin_add_credits(self, update: Update, context: CallbackContext) -> int:
        """Handle add credits input"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        
        try:
            user_id, amount = map(int, text.split())
            self.db.add_credits(user_id, amount)
            
            await update.message.reply_text(
                f"✅ **Credits Added**\n\nUser: `{user_id}`\nAmount: `{amount}` credits",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text(
                "❌ **Invalid Format**\n\nUse: `user_id amount`\nExample: `123456789 10`",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        
        return ConversationHandler.END
    
    async def handle_admin_remove_credits(self, update: Update, context: CallbackContext) -> int:
        """Handle remove credits input"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        
        try:
            user_id, amount = map(int, text.split())
            if self.db.deduct_credits(user_id, amount):
                await update.message.reply_text(
                    f"✅ **Credits Removed**\n\nUser: `{user_id}`\nAmount: `{amount}` credits",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"❌ **Failed**\n\nUser doesn't have enough credits.",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
        except ValueError:
            await update.message.reply_text(
                "❌ **Invalid Format**\n\nUse: `user_id amount`\nExample: `123456789 5`",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        
        return ConversationHandler.END
    
    async def handle_admin_ultimate_credits(self, update: Update, context: CallbackContext) -> int:
        """Handle ultimate credits input"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        
        try:
            user_id = int(text)
            # Give a very large amount of credits (practically unlimited)
            self.db.add_credits(user_id, 1000000)
            
            await update.message.reply_text(
                f"⚡ **Ultimate Credits Granted**\n\nUser: `{user_id}`\nCredits: `1,000,000` (Unlimited)",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text(
                "❌ **Invalid Format**\n\nUse: `user_id`\nExample: `123456789`",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        
        return ConversationHandler.END
    
    async def handle_admin_ban_user(self, update: Update, context: CallbackContext) -> int:
        """Handle ban user input"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        
        try:
            parts = text.split(' ', 1)
            user_id = int(parts[0])
            reason = parts[1] if len(parts) > 1 else "No reason provided"
            
            # Check if user exists
            user = self.db.get_user(user_id)
            if not user:
                await update.message.reply_text(
                    f"❌ **User Not Found**\n\nUser ID `{user_id}` not found in database.",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            
            # Ban the user
            self.db.ban_user(user_id, self.admin_id, reason)
            
            await update.message.reply_text(
                f"🔨 **User Banned**\n\nUser: `{user_id}`\nReason: `{reason}`",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text(
                "❌ **Invalid Format**\n\nUse: `user_id reason`\nExample: `123456789 Spamming`",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        
        return ConversationHandler.END
    
    async def handle_admin_unban_user(self, update: Update, context: CallbackContext) -> int:
        """Handle unban user input"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        
        try:
            user_id = int(text)
            
            # Check if user exists and is banned
            user = self.db.get_user(user_id)
            if not user:
                await update.message.reply_text(
                    f"❌ **User Not Found**\n\nUser ID `{user_id}` not found in database.",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            
            if not self.db.is_user_banned(user_id):
                await update.message.reply_text(
                    f"❌ **User Not Banned**\n\nUser ID `{user_id}` is not banned.",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            
            # Unban the user
            self.db.unban_user(user_id)
            
            await update.message.reply_text(
                f"🔓 **User Unbanned**\n\nUser: `{user_id}`\nStatus: ✅ Active",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text(
                "❌ **Invalid Format**\n\nUse: `user_id`\nExample: `123456789`",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        
        return ConversationHandler.END
    
    async def handle_admin_protect_number(self, update: Update, context: CallbackContext) -> int:
        """Handle protect number input"""
        if not self.is_admin(update.effective_user.id):
            return ConversationHandler.END
        
        text = update.message.text.strip()
        if text.lower() == 'cancel':
            await self.cancel(update, context)
            return ConversationHandler.END
        
        try:
            phone_number = text
            # Validate phone number format
            if not re.match(r'^[6-9]\d{9}$', phone_number):
                await update.message.reply_text(
                    "❌ **Invalid Phone Number**\n\nPlease enter a valid 10-digit phone number starting with 6-9.",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            
            # Protect the number
            if self.db.protect_number(phone_number, self.admin_id, "Admin protection"):
                await update.message.reply_text(
                    f"🛡️ **Number Protected**\n\nPhone: `{phone_number}`\nStatus: 🔒 Protected from lookups",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ **Already Protected**\n\nPhone: `{phone_number}`\nStatus: Already protected",
                    reply_markup=self.create_admin_keyboard(),
                    parse_mode='Markdown'
                )
        except Exception as e:
            await update.message.reply_text(
                f"❌ **Error**\n\nFailed to protect number: {str(e)}",
                reply_markup=self.create_admin_keyboard(),
                parse_mode='Markdown'
            )
        
        return ConversationHandler.END
    
    async def admin_search_stats(self, update: Update, context: CallbackContext) -> None:
        """Show search statistics"""
        if not self.is_admin(update.effective_user.id):
            return
        
        search_stats = self.db.get_search_stats()
        
        stats_text = "📈 **Search Statistics**\n\n"
        
        for service_type, count in search_stats:
            service_name = API_CONFIG.get(service_type, {}).get('name', service_type)
            percentage = (count / self.db.get_total_searches()) * 100 if self.db.get_total_searches() > 0 else 0
            stats_text += f"• {service_name}: `{count}` ({percentage:.1f}%)\n"
        
        await update.message.reply_text(
            stats_text,
            reply_markup=self.create_admin_keyboard(),
            parse_mode='Markdown'
        )
    
    # Direct input handler
    async def handle_direct_input(self, update: Update, context: CallbackContext) -> None:
        """Handle direct number input"""
        user_input = update.message.text.strip()
        user = update.effective_user
        
        # Check if user is banned
        if self.db.is_user_banned(user.id):
            return
        
        # Update user activity
        self.db.update_user_activity(user.id)
        
        # Try to match input with each type
        for lookup_type, config in self.api_config.items():
            if self.validate_input(lookup_type, user_input):
                await self.process_lookup(update, user_input, lookup_type)
                return
        
        # If no match, check for button clicks
        await self.handle_button(update, context)
    
    # Button handler
    async def handle_button(self, update: Update, context: CallbackContext) -> None:
        """Handle button clicks"""
        text = update.message.text
        user = update.effective_user
        
        # Check if user is banned (for non-admin buttons)
        if not self.is_admin(user.id) and text not in ["❌ Cancel"]:
            if self.db.is_user_banned(user.id):
                await update.message.reply_text("🚫 Your account is banned from using this bot.")
                return
        
        button_actions = {
            "📱 Phone": self.phone_command,
            "🆔 Aadhaar": self.aadhaar_command,
            "🚗 Vehicle": self.vehicle_command,
            "🏦 IFSC": self.ifsc_command,
            "🌐 IP Lookup": self.ip_command,
            "📮 Pincode": self.pincode_command,
            "💎 My Credits": self.credits_command,
            "🛒 Buy Credits": self.buy_credits,
            "ℹ️ Help": self.help_command,
            "👑 Admin Panel": self.admin_panel,
            "📊 User Statistics": self.admin_user_stats,
            "👥 All Users": self.admin_all_users,
            "➕ Add Credits": self.admin_add_credits,
            "➖ Remove Credits": self.admin_remove_credits,
            "⚡ Ultimate Credits": self.admin_ultimate_credits,
            "🔨 Ban User": self.admin_ban_user,
            "🔓 Unban User": self.admin_unban_user,
            "🛡️ Protect Number": self.admin_protect_number,
            "🛡️ Protected Numbers": self.admin_protected_numbers,
            "🚫 Banned Users": self.admin_banned_users,
            "📈 Search Stats": self.admin_search_stats,
            "🏠 Main Menu": self.start,
            "❌ Cancel": self.cancel
        }
        
        action = button_actions.get(text)
        if action:
            if text == "❌ Cancel":
                await action(update, context)
            else:
                await action(update, context)
        else:
            await update.message.reply_text(
                "Please choose a valid option from the menu below:",
                reply_markup=self.create_main_keyboard(user.id)
            )
    
    async def cancel(self, update: Update, context: CallbackContext) -> int:
        """Cancel conversation"""
        await update.message.reply_text(
            "❌ *Operation cancelled*\n\n🏠 *Returning to main menu...*",
            reply_markup=self.create_main_keyboard(update.effective_user.id),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

def main():
    """Start the professional bot"""
    # Check required packages
    try:
        import requests
        from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
        from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ConversationHandler
    except ImportError as e:
        print(f"❌ Missing required packages: {e}")
        print("💡 Please run: pip install requests python-telegram-bot")
        return
    
    # Initialize bot
    bot = ProfessionalInfoBot()
    
    try:
        # Create application with proper initialization
        application = Application.builder().token(bot.token).build()
        
        # Conversation handlers for lookups
        conv_handlers = [
            ConversationHandler(
                entry_points=[
                    CommandHandler('phone', bot.phone_command),
                    MessageHandler(filters.Regex("^📱 Phone$"), bot.phone_command)
                ],
                states={PHONE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_phone_input)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    CommandHandler('aadhaar', bot.aadhaar_command),
                    MessageHandler(filters.Regex("^🆔 Aadhaar$"), bot.aadhaar_command)
                ],
                states={AADHAAR_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_aadhaar_input)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    CommandHandler('vehicle', bot.vehicle_command),
                    MessageHandler(filters.Regex("^🚗 Vehicle$"), bot.vehicle_command)
                ],
                states={VEHICLE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_vehicle_input)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    CommandHandler('ifsc', bot.ifsc_command),
                    MessageHandler(filters.Regex("^🏦 IFSC$"), bot.ifsc_command)
                ],
                states={IFSC_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_ifsc_input)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    CommandHandler('ip', bot.ip_command),
                    MessageHandler(filters.Regex("^🌐 IP Lookup$"), bot.ip_command)
                ],
                states={IP_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_ip_input)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    CommandHandler('pincode', bot.pincode_command),
                    MessageHandler(filters.Regex("^📮 Pincode$"), bot.pincode_command)
                ],
                states={PINCODE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_pincode_input)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            # Admin conversation handlers
            ConversationHandler(
                entry_points=[
                    MessageHandler(filters.Regex("^➕ Add Credits$"), bot.admin_add_credits)
                ],
                states={ADMIN_ADD_CREDITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_admin_add_credits)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    MessageHandler(filters.Regex("^➖ Remove Credits$"), bot.admin_remove_credits)
                ],
                states={ADMIN_REMOVE_CREDITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_admin_remove_credits)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    MessageHandler(filters.Regex("^⚡ Ultimate Credits$"), bot.admin_ultimate_credits)
                ],
                states={ADMIN_ULTIMATE_CREDITS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_admin_ultimate_credits)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    MessageHandler(filters.Regex("^🔨 Ban User$"), bot.admin_ban_user)
                ],
                states={ADMIN_BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_admin_ban_user)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    MessageHandler(filters.Regex("^🔓 Unban User$"), bot.admin_unban_user)
                ],
                states={ADMIN_UNBAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_admin_unban_user)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            ),
            ConversationHandler(
                entry_points=[
                    MessageHandler(filters.Regex("^🛡️ Protect Number$"), bot.admin_protect_number)
                ],
                states={ADMIN_PROTECT_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_admin_protect_number)]},
                fallbacks=[CommandHandler('cancel', bot.cancel)]
            )
        ]
        
        # Add all handlers
        for handler in conv_handlers:
            application.add_handler(handler)
        
        # Command handlers
        application.add_handler(CommandHandler("start", bot.start))
        application.add_handler(CommandHandler("help", bot.help_command))
        application.add_handler(CommandHandler("credits", bot.credits_command))
        application.add_handler(CommandHandler("status", bot.help_command))
        
        # Message handler for direct input and buttons
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_direct_input))
        
        # Startup message
        print("🚀 Professional Multi-Info Bot Starting...")
        print("✅ System Initialized")
        print("🔌 APIs Connected")
        print("💾 Database Ready")
        print("👑 Admin Panel Enabled")
        print("🔨 Ban System Activated")
        print("🛡️ Number Protection Activated")
        print("🛒 Buy Credits System Ready")
        print("🎯 Ready for Operations")
        print(f"\n📊 Available Services: {len(API_CONFIG)}")
        print("💎 Credits System: Active")
        print("🚫 Ban System: Active")
        print("🛡️ Number Protection: Active")
        print("🛒 Buy Credits: Active")
        print("👥 User Tracking: Enabled")
        print(f"👑 Admin: @DARK_RAJDEB")
        print("\n💎 Professional Edition v5.0")
        print("🤖 Bot is now running...")
        
        # Start polling with error handling
        print("🔄 Starting bot polling...")
        application.run_polling()
        
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        print("💡 Check your bot token and internet connection")

if __name__ == '__main__':
    main()
