"""Telegram bot for panel management"""
import asyncio
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Node, Tunnel, Settings
import httpx

logger = logging.getLogger(__name__)

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton  # type: ignore
    from telegram.ext import (  # type: ignore
        Application, CommandHandler, CallbackQueryHandler, ContextTypes,
        ConversationHandler, MessageHandler, filters
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Update = None  # type: ignore
    InlineKeyboardButton = None  # type: ignore
    InlineKeyboardMarkup = None  # type: ignore
    ReplyKeyboardMarkup = None  # type: ignore
    KeyboardButton = None  # type: ignore
    Application = None  # type: ignore
    CommandHandler = None  # type: ignore
    CallbackQueryHandler = None  # type: ignore
    ContextTypes = None  # type: ignore
    ConversationHandler = None  # type: ignore
    MessageHandler = None  # type: ignore
    filters = None  # type: ignore
    logger.warning("python-telegram-bot not installed. Telegram bot will not work.")


# Conversation states
(WAITING_FOR_TUNNEL_NAME, WAITING_FOR_TUNNEL_CORE, WAITING_FOR_TUNNEL_TYPE, WAITING_FOR_TUNNEL_PORTS,
 WAITING_FOR_TUNNEL_IRAN_NODE, WAITING_FOR_TUNNEL_FOREIGN_NODE, WAITING_FOR_TUNNEL_REMOTE_IP,
 WAITING_FOR_TUNNEL_TOKEN) = range(8)


class TelegramBot:
    """Telegram bot for managing panel"""
    
    def __init__(self):
        self.application: Optional[Application] = None
        self.enabled = False
        self.bot_token: Optional[str] = None
        self.admin_ids: List[str] = []
        self.backup_task: Optional[asyncio.Task] = None
        self.backup_enabled = False
        self.backup_interval = 60
        self.backup_interval_unit = "minutes"
        self.user_languages: Dict[str, str] = {}
        self.user_states: Dict[int, Dict[str, Any]] = {}
        self.language_file = Path("/tmp/telegram_bot_languages.json")
        self._load_languages()
        api_url = os.getenv("PANEL_API_URL")
        if not api_url:
            api_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        self.api_base_url = api_url
    
    async def load_settings(self):
        """Load settings from database"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Settings).where(Settings.key == "telegram"))
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                self.enabled = setting.value.get("enabled", False)
                self.bot_token = setting.value.get("bot_token")
                self.admin_ids = setting.value.get("admin_ids", [])
                self.backup_enabled = setting.value.get("backup_enabled", False)
                self.backup_interval = setting.value.get("backup_interval", 60)
                self.backup_interval_unit = setting.value.get("backup_interval_unit", "minutes")
            else:
                self.enabled = False
                self.bot_token = None
                self.admin_ids = []
                self.backup_enabled = False
                self.backup_interval = 60
                self.backup_interval_unit = "minutes"
    
    def _load_languages(self):
        """Load user languages from file"""
        try:
            if self.language_file.exists():
                import json
                with open(self.language_file, 'r') as f:
                    data = json.load(f)
                    self.user_languages = {str(k): v for k, v in data.items()}
        except Exception as e:
            logger.warning(f"Failed to load languages: {e}")
            self.user_languages = {}
    
    def _save_languages(self):
        """Save user languages to file"""
        try:
            import json
            with open(self.language_file, 'w') as f:
                json.dump(self.user_languages, f)
        except Exception as e:
            logger.warning(f"Failed to save languages: {e}")
    
    def get_lang(self, user_id: int) -> str:
        """Get user language"""
        return self.user_languages.get(str(user_id), "en")
    
    def t(self, user_id: int, key: str, **kwargs) -> str:
        """Translate text"""
        lang = self.get_lang(user_id)
        translations = {
            "en": {
                "welcome": "👋 Welcome to Smite Panel Bot!\n\nSelect an action:",
                "access_denied": "❌ Access denied. You are not an admin.",
                "add_iran_node": "➕ Add Iran Node",
                "add_foreign_node": "➕ Add Foreign Node",
                "remove_iran_node": "➖ Remove Iran Node",
                "remove_foreign_node": "➖ Remove Foreign Node",
                "create_tunnel": "🔗 Create Tunnel",
                "remove_tunnel": "🗑️ Remove Tunnel",
                "node_stats": "📊 Node Stats",
                "tunnel_stats": "📊 Tunnel Stats",
                "logs": "📋 Logs",
                "backup": "📦 Backup",
                "language": "🌐 Language",
                "enter_node_name": "Enter node name:",
                "enter_node_ip": "Enter node IP address:",
                "enter_node_port": "Enter node API port (default: 8888):",
                "node_added": "✅ Node added successfully!",
                "node_removed": "✅ Node removed successfully!",
                "select_node_to_remove": "Select node to remove:",
                "enter_tunnel_name": "Enter tunnel name:",
                "select_tunnel_core": "Select tunnel core:",
                "select_tunnel_type": "Select tunnel type:",
                "enter_tunnel_ports": "Enter tunnel ports (comma-separated, e.g., 8080,8081,8082):",
                "select_iran_node": "Select Iran node:",
                "select_foreign_node": "Select foreign node:",
                "enter_remote_ip": "Enter remote IP (default: 127.0.0.1):",
                "tunnel_created": "✅ Tunnel created successfully!",
                "select_tunnel_to_remove": "Select tunnel to remove:",
                "tunnel_removed": "✅ Tunnel removed successfully!",
                "cancel": "❌ Cancelled",
                "back": "🔙 Back",
                "english": "🇬🇧 English",
                "farsi": "🇮🇷 Farsi",
                "language_set": "✅ Language set to {lang}",
                "no_nodes": "📭 No nodes found.",
                "no_tunnels": "📭 No tunnels found.",
                "error": "❌ Error: {error}",
            },
            "fa": {
                "welcome": "👋 به ربات پنل اسمیت خوش آمدید!\n\nیک عمل را انتخاب کنید:",
                "access_denied": "❌ دسترسی رد شد. شما ادمین نیستید.",
                "add_iran_node": "➕ افزودن نود ایران",
                "add_foreign_node": "➕ افزودن نود خارجی",
                "remove_iran_node": "➖ حذف نود ایران",
                "remove_foreign_node": "➖ حذف نود خارجی",
                "create_tunnel": "🔗 ایجاد تونل",
                "remove_tunnel": "🗑️ حذف تونل",
                "node_stats": "📊 آمار نودها",
                "tunnel_stats": "📊 آمار تونل‌ها",
                "logs": "📋 لاگ‌ها",
                "backup": "📦 پشتیبان",
                "language": "🌐 زبان",
                "enter_node_name": "نام نود را وارد کنید:",
                "enter_node_ip": "آدرس IP نود را وارد کنید:",
                "enter_node_port": "پورت API نود را وارد کنید (پیش‌فرض: 8888):",
                "node_added": "✅ نود با موفقیت افزوده شد!",
                "node_removed": "✅ نود با موفقیت حذف شد!",
                "select_node_to_remove": "نود را برای حذف انتخاب کنید:",
                "enter_tunnel_name": "نام تونل را وارد کنید:",
                "select_tunnel_core": "هسته تونل را انتخاب کنید:",
                "select_tunnel_type": "نوع تونل را انتخاب کنید:",
                "enter_tunnel_ports": "پورت‌های تونل را وارد کنید (جدا شده با کاما، مثال: 8080,8081,8082):",
                "select_iran_node": "نود ایران را انتخاب کنید:",
                "select_foreign_node": "نود خارجی را انتخاب کنید:",
                "enter_remote_ip": "IP از راه دور را وارد کنید (پیش‌فرض: 127.0.0.1):",
                "tunnel_created": "✅ تونل با موفقیت ایجاد شد!",
                "select_tunnel_to_remove": "تونل را برای حذف انتخاب کنید:",
                "tunnel_removed": "✅ تونل با موفقیت حذف شد!",
                "cancel": "❌ لغو شد",
                "back": "🔙 بازگشت",
                "english": "🇬🇧 انگلیسی",
                "farsi": "🇮🇷 فارسی",
                "language_set": "✅ زبان به {lang} تنظیم شد",
                "no_nodes": "📭 نودی یافت نشد.",
                "no_tunnels": "📭 تونلی یافت نشد.",
                "error": "❌ خطا: {error}",
            }
        }
        text = translations.get(lang, translations["en"]).get(key, key)
        return text.format(**kwargs) if kwargs else text
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return str(user_id) in self.admin_ids
    
    async def start(self):
        """Start Telegram bot"""
        if not TELEGRAM_AVAILABLE:
            logger.error("python-telegram-bot not available. Cannot start bot.")
            return False
        
        await self.load_settings()
        
        if not self.enabled or not self.bot_token:
            logger.info("Telegram bot not enabled or token not set")
            return False
        
        # Stop existing instance if running
        await self.stop()
        
        try:
            self.application = Application.builder().token(self.bot_token).build()
            
            create_tunnel_conv = ConversationHandler(
                entry_points=[CallbackQueryHandler(self.create_tunnel_start, pattern="^create_tunnel$")],
                states={
                    WAITING_FOR_TUNNEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.create_tunnel_name)],
                    WAITING_FOR_TUNNEL_CORE: [CallbackQueryHandler(self.create_tunnel_core, pattern="^core_")],
                    WAITING_FOR_TUNNEL_TYPE: [CallbackQueryHandler(self.create_tunnel_type, pattern="^type_")],
                    WAITING_FOR_TUNNEL_PORTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.create_tunnel_ports)],
                    WAITING_FOR_TUNNEL_IRAN_NODE: [CallbackQueryHandler(self.create_tunnel_iran_node, pattern="^iran_node_")],
                    WAITING_FOR_TUNNEL_FOREIGN_NODE: [CallbackQueryHandler(self.create_tunnel_foreign_node, pattern="^foreign_node_")],
                    WAITING_FOR_TUNNEL_REMOTE_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.create_tunnel_remote_ip)],
                    WAITING_FOR_TUNNEL_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.create_tunnel_token)],
                },
                fallbacks=[CallbackQueryHandler(self.cancel_operation, pattern="^cancel$")],
            )
            
            remove_tunnel_conv = ConversationHandler(
                entry_points=[CallbackQueryHandler(self.remove_tunnel_start, pattern="^remove_tunnel$")],
                states={
                    WAITING_FOR_TUNNEL_NAME: [CallbackQueryHandler(self.remove_tunnel_confirm, pattern="^rm_tunnel_")],
                },
                fallbacks=[CallbackQueryHandler(self.cancel_operation, pattern="^cancel$")],
            )
            
            self.application.add_handler(CommandHandler("start", self.cmd_start))
            self.application.add_handler(CommandHandler("help", self.cmd_help))
            self.application.add_handler(CommandHandler("nodes", self.cmd_nodes))
            self.application.add_handler(CommandHandler("tunnels", self.cmd_tunnels))
            self.application.add_handler(CommandHandler("status", self.cmd_status))
            self.application.add_handler(CommandHandler("backup", self.cmd_backup))
            self.application.add_handler(CommandHandler("logs", self.cmd_logs))
            self.application.add_handler(create_tunnel_conv)
            self.application.add_handler(remove_tunnel_conv)
            self.application.add_handler(CallbackQueryHandler(self.handle_callback, pattern="^(lang_|select_language|back_to_menu|node_stats|tunnel_stats|logs|cmd_nodes|cmd_tunnels|cmd_backup|cmd_status)$"))
            
            # Handle persistent keyboard buttons - must be after conversation handlers
            self.application.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_text_message
            ))
            
            await self.start_backup_task()
            
            logger.info("Telegram bot started successfully")
            
            asyncio.create_task(self._run_polling())
            
            return True
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}", exc_info=True)
            await self.stop()
            return False
    
    async def _run_polling(self):
        """Run polling in background task"""
        try:
            await self.application.run_polling(drop_pending_updates=True, stop_signals=None)
        except Exception as e:
            logger.error(f"Error in polling: {e}", exc_info=True)
    
    async def stop(self):
        """Stop Telegram bot"""
        await self.stop_backup_task()
        
        if self.application:
            try:
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                logger.warning(f"Error stopping Telegram bot: {e}")
            finally:
                self.application = None
                logger.info("Telegram bot stopped")
    
    async def start_backup_task(self):
        """Start automatic backup task"""
        await self.stop_backup_task()
        await self.load_settings()
        
        if self.backup_enabled and self.admin_ids:
            self.backup_task = asyncio.create_task(self._backup_loop())
            logger.info(f"Automatic backup task started: interval={self.backup_interval} {self.backup_interval_unit}")
    
    async def stop_backup_task(self):
        """Stop automatic backup task"""
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass
            self.backup_task = None
            logger.info("Automatic backup task stopped")
    
    async def _backup_loop(self):
        """Background task for automatic backups"""
        try:
            while True:
                await self.load_settings()
                
                if not self.backup_enabled or not self.admin_ids:
                    await asyncio.sleep(60)
                    continue
                
                if self.backup_interval_unit == "hours":
                    sleep_seconds = self.backup_interval * 3600
                else:
                    sleep_seconds = self.backup_interval * 60
                
                await asyncio.sleep(sleep_seconds)
                
                if not self.backup_enabled:
                    continue
                
                try:
                    backup_path = await self.create_backup()
                    if backup_path and self.application and self.application.bot:
                        for admin_id_str in self.admin_ids:
                            try:
                                admin_id = int(admin_id_str)
                                with open(backup_path, 'rb') as f:
                                    await self.application.bot.send_document(
                                        chat_id=admin_id,
                                        document=f,
                                        filename=f"smite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                                        caption=f"🔄 Automatic backup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                                    )
                            except Exception as e:
                                logger.error(f"Failed to send backup to admin {admin_id_str}: {e}")
                        
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        logger.info("Automatic backup sent successfully")
                except Exception as e:
                    logger.error(f"Error in automatic backup: {e}", exc_info=True)
        except asyncio.CancelledError:
            logger.info("Backup loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Backup loop error: {e}", exc_info=True)
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        try:
            user_id = update.effective_user.id
            reply_markup = self._get_keyboard(user_id)
            
            if not self.is_admin(user_id):
                await update.message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
                return
            
            await update.message.reply_text(self.t(user_id, "welcome"), reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in cmd_start: {e}", exc_info=True)
            try:
                user_id = update.effective_user.id
                reply_markup = self._get_keyboard(user_id)
                await update.message.reply_text("❌ Error: Please try again.", reply_markup=reply_markup)
            except:
                pass
    
    def _get_keyboard(self, user_id: int) -> ReplyKeyboardMarkup:
        """Get persistent keyboard markup"""
        keyboard = [
            [
                KeyboardButton(self.t(user_id, 'node_stats')),
                KeyboardButton(self.t(user_id, 'tunnel_stats'))
            ],
            [
                KeyboardButton(self.t(user_id, 'create_tunnel')),
                KeyboardButton(self.t(user_id, 'remove_tunnel'))
            ],
            [
                KeyboardButton(self.t(user_id, 'logs')),
                KeyboardButton(self.t(user_id, 'backup'))
            ],
            [
                KeyboardButton(self.t(user_id, 'language'))
            ],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    async def show_main_menu(self, message_or_query):
        """Show main menu with persistent keyboard buttons"""
        try:
            # Get user_id and message object
            if hasattr(message_or_query, 'from_user'):
                user_id = message_or_query.from_user.id
                message = message_or_query
            elif hasattr(message_or_query, 'message'):
                user_id = message_or_query.message.from_user.id
                message = message_or_query.message
            else:
                user_id = message_or_query.chat.id if hasattr(message_or_query, 'chat') else 0
                message = message_or_query
            
            reply_markup = self._get_keyboard(user_id)
            text = self.t(user_id, "welcome")
            
            if hasattr(message, 'reply_text'):
                await message.reply_text(text, reply_markup=reply_markup)
            elif hasattr(message_or_query, 'edit_message_text'):
                await message_or_query.edit_message_text(text, reply_markup=reply_markup)
            elif hasattr(message_or_query, 'message'):
                await message_or_query.message.reply_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error showing main menu: {e}", exc_info=True)
            try:
                user_id = message_or_query.from_user.id if hasattr(message_or_query, 'from_user') else 0
                reply_markup = self._get_keyboard(user_id)
                if hasattr(message_or_query, 'reply_text'):
                    await message_or_query.reply_text(self.t(user_id, "welcome"), reply_markup=reply_markup)
            except:
                pass
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = update.effective_user.id
        reply_markup = self._get_keyboard(user_id)
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
            return
        
        help_text = """📋 Available Commands:

/start - Show main menu
/nodes - List all nodes
/tunnels - List all tunnels
/status - Show panel status
/logs - Show recent logs
/backup - Create and send backup

Use buttons in messages to interact with nodes and tunnels."""
        
        await update.message.reply_text(help_text, reply_markup=reply_markup)
    
    async def create_tunnel_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start creating a tunnel"""
        try:
            # Handle both callback query and text message
            if hasattr(update, 'callback_query') and update.callback_query:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                message = query.message
            else:
                user_id = update.effective_user.id
                message = update.message
            
            if not self.is_admin(user_id):
                if hasattr(message, 'edit_message_text'):
                    await message.edit_message_text(self.t(user_id, "access_denied"))
                else:
                    await message.reply_text(self.t(user_id, "access_denied"))
                return ConversationHandler.END
            
            self.user_states[user_id] = {"step": "name"}
            
            cancel_btn = InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")
            reply_markup = InlineKeyboardMarkup([[cancel_btn]])
            if hasattr(message, 'edit_message_text') and message:
                await message.edit_message_text(self.t(user_id, "enter_tunnel_name"), reply_markup=reply_markup)
            else:
                await message.reply_text(self.t(user_id, "enter_tunnel_name"), reply_markup=reply_markup)
            return WAITING_FOR_TUNNEL_NAME
        except Exception as e:
            logger.error(f"Error in create_tunnel_start: {e}", exc_info=True)
            return ConversationHandler.END
    
    async def create_tunnel_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle tunnel name input"""
        user_id = update.message.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        self.user_states[user_id]["name"] = update.message.text
        self.user_states[user_id]["step"] = "core"
        
        keyboard = [
            [InlineKeyboardButton("GOST", callback_data="core_gost")],
            [InlineKeyboardButton("Rathole", callback_data="core_rathole")],
            [InlineKeyboardButton("Backhaul", callback_data="core_backhaul")],
            [InlineKeyboardButton("Chisel", callback_data="core_chisel")],
            [InlineKeyboardButton("FRP", callback_data="core_frp")],
            [InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(self.t(user_id, "select_tunnel_core"), reply_markup=reply_markup)
        return WAITING_FOR_TUNNEL_CORE
    
    async def create_tunnel_core(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle tunnel core selection"""
        query = update.callback_query
        await query.answer()
        
        if not query.message:
            return ConversationHandler.END
        
        user_id = query.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        core = query.data.replace("core_", "")
        self.user_states[user_id]["core"] = core
        self.user_states[user_id]["step"] = "type"
        
        # Determine available types based on core
        types = []
        if core == "gost":
            types = [("TCP", "tcp"), ("UDP", "udp"), ("gRPC", "grpc"), ("TCPMux", "tcpmux")]
        elif core == "rathole":
            types = [("TCP", "tcp"), ("WebSocket", "ws")]
        elif core == "backhaul":
            types = [("TCP", "tcp"), ("UDP", "udp"), ("WebSocket", "ws"), ("WSMux", "wsmux"), ("TCPMux", "tcpmux")]
        elif core == "frp":
            types = [("TCP", "tcp"), ("UDP", "udp")]
        elif core == "chisel":
            types = [("Chisel", "chisel")]
        
        keyboard = []
        for type_name, type_val in types:
            keyboard.append([InlineKeyboardButton(type_name, callback_data=f"type_{type_val}")])
        keyboard.append([InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(self.t(user_id, "select_tunnel_type"), reply_markup=reply_markup)
        return WAITING_FOR_TUNNEL_TYPE
    
    async def create_tunnel_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle tunnel type selection"""
        query = update.callback_query
        await query.answer()
        
        if not query.message:
            return ConversationHandler.END
        
        user_id = query.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        tunnel_type = query.data.replace("type_", "")
        self.user_states[user_id]["type"] = tunnel_type
        self.user_states[user_id]["step"] = "ports"
        
        cancel_btn = InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")
        reply_markup = InlineKeyboardMarkup([[cancel_btn]])
        await query.edit_message_text(self.t(user_id, "enter_tunnel_ports"), reply_markup=reply_markup)
        return WAITING_FOR_TUNNEL_PORTS
    
    async def create_tunnel_ports(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle tunnel ports input"""
        user_id = update.message.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        ports_str = update.message.text
        ports = [int(p.strip()) for p in ports_str.split(",") if p.strip().isdigit()]
        
        if not ports:
            reply_markup = self._get_keyboard(user_id)
            await update.message.reply_text("Invalid ports. Please enter comma-separated numbers.", reply_markup=reply_markup)
            return WAITING_FOR_TUNNEL_PORTS
        
        self.user_states[user_id]["ports"] = ports
        core = self.user_states[user_id]["core"]
        
        if core == "rathole":
            self.user_states[user_id]["step"] = "iran_node"
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Node))
                nodes = result.scalars().all()
                iran_nodes = [n for n in nodes if n.node_metadata.get("role") == "iran"]
                
                if not iran_nodes:
                    reply_markup = self._get_keyboard(user_id)
                    await update.message.reply_text("No Iran nodes found. Please add an Iran node first.", reply_markup=reply_markup)
                    del self.user_states[user_id]
                    return ConversationHandler.END
                
                keyboard = []
                for node in iran_nodes:
                    keyboard.append([InlineKeyboardButton(
                        f"🇮🇷 {node.name}",
                        callback_data=f"iran_node_{node.id}"
                    )])
                keyboard.append([InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(self.t(user_id, "select_iran_node"), reply_markup=reply_markup)
                return WAITING_FOR_TUNNEL_IRAN_NODE
        
        if core in ["backhaul", "frp", "chisel"]:
            self.user_states[user_id]["step"] = "iran_node"
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Node))
                nodes = result.scalars().all()
                iran_nodes = [n for n in nodes if n.node_metadata.get("role") == "iran"]
                
                if not iran_nodes:
                    reply_markup = self._get_keyboard(user_id)
                    await update.message.reply_text("No Iran nodes found. Please add an Iran node first.", reply_markup=reply_markup)
                    del self.user_states[user_id]
                    return ConversationHandler.END
                
                keyboard = []
                for node in iran_nodes:
                    keyboard.append([InlineKeyboardButton(
                        f"🇮🇷 {node.name}",
                        callback_data=f"iran_node_{node.id}"
                    )])
                keyboard.append([InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(self.t(user_id, "select_iran_node"), reply_markup=reply_markup)
                return WAITING_FOR_TUNNEL_IRAN_NODE
        else:
            self.user_states[user_id]["step"] = "remote_ip"
            cancel_btn = InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")
            reply_markup = InlineKeyboardMarkup([[cancel_btn]])
            await update.message.reply_text(self.t(user_id, "enter_remote_ip"), reply_markup=reply_markup)
            return WAITING_FOR_TUNNEL_REMOTE_IP
    
    async def create_tunnel_token(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle Rathole token input"""
        user_id = update.message.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        token = update.message.text.strip()
        if not token:
            await update.message.reply_text("Token cannot be empty. Please enter a valid token.")
            return WAITING_FOR_TUNNEL_TOKEN
        
        self.user_states[user_id]["token"] = token
        self.user_states[user_id]["step"] = "iran_node"
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Node))
            nodes = result.scalars().all()
            iran_nodes = [n for n in nodes if n.node_metadata.get("role") == "iran"]
            
            if not iran_nodes:
                reply_markup = self._get_keyboard(user_id)
                await update.message.reply_text("No Iran nodes found. Please add an Iran node first.", reply_markup=reply_markup)
                del self.user_states[user_id]
                return ConversationHandler.END
            
            keyboard = []
            for node in iran_nodes:
                keyboard.append([InlineKeyboardButton(
                    f"🇮🇷 {node.name}",
                    callback_data=f"iran_node_{node.id}"
                )])
            keyboard.append([InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(self.t(user_id, "select_iran_node"), reply_markup=reply_markup)
            return WAITING_FOR_TUNNEL_IRAN_NODE
    
    async def create_tunnel_iran_node(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle Iran node selection"""
        query = update.callback_query
        await query.answer()
        
        if not query.message:
            return ConversationHandler.END
        
        user_id = query.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        iran_node_id = query.data.replace("iran_node_", "")
        self.user_states[user_id]["iran_node_id"] = iran_node_id
        self.user_states[user_id]["step"] = "foreign_node"
        
        # Get foreign nodes
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Node))
            nodes = result.scalars().all()
            foreign_nodes = [n for n in nodes if n.node_metadata.get("role") == "foreign"]
            
            if not foreign_nodes:
                await query.edit_message_text("No foreign nodes found. Please add a foreign node first.")
                del self.user_states[user_id]
                return ConversationHandler.END
            
            keyboard = []
            for node in foreign_nodes:
                keyboard.append([InlineKeyboardButton(
                    f"🌍 {node.name}",
                    callback_data=f"foreign_node_{node.id}"
                )])
            keyboard.append([InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(self.t(user_id, "select_foreign_node"), reply_markup=reply_markup)
            return WAITING_FOR_TUNNEL_FOREIGN_NODE
    
    async def create_tunnel_foreign_node(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle foreign node selection and create tunnel"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        foreign_node_id = query.data.replace("foreign_node_", "")
        state = self.user_states[user_id]
        
        spec = {"ports": state["ports"]}
        
        if state["core"] == "rathole" and "token" in state:
            spec["token"] = state["token"]
        
        if state["core"] == "gost":
            spec["remote_ip"] = state.get("remote_ip", "127.0.0.1")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/api/tunnels",
                    json={
                        "name": state["name"],
                        "core": state["core"],
                        "type": state["type"],
                        "iran_node_id": state.get("iran_node_id"),
                        "foreign_node_id": foreign_node_id,
                        "spec": spec
                    }
                )
                if not query.message:
                    return ConversationHandler.END
                if response.status_code == 200:
                    await query.edit_message_text(self.t(user_id, "tunnel_created"))
                else:
                    error_msg = response.text[:200] if response.text else "Unknown error"
                    await query.edit_message_text(self.t(user_id, "error", error=error_msg))
        except Exception as e:
            logger.error(f"Error creating tunnel: {e}", exc_info=True)
            if query.message:
                await query.edit_message_text(self.t(user_id, "error", error=str(e)[:200]))
        
        del self.user_states[user_id]
        return ConversationHandler.END
    
    async def create_tunnel_remote_ip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle remote IP input and create GOST tunnel"""
        user_id = update.message.from_user.id
        if user_id not in self.user_states:
            return ConversationHandler.END
        
        remote_ip = update.message.text.strip() or "127.0.0.1"
        state = self.user_states[user_id]
        
        spec = {
            "ports": state["ports"],
            "remote_ip": remote_ip
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/api/tunnels",
                    json={
                        "name": state["name"],
                        "core": state["core"],
                        "type": state["type"],
                        "spec": spec
                    }
                )
                if response.status_code == 200:
                    reply_markup = self._get_keyboard(user_id)
                    await update.message.reply_text(self.t(user_id, "tunnel_created"), reply_markup=reply_markup)
                else:
                    error_msg = response.text[:200] if response.text else "Unknown error"
                    reply_markup = self._get_keyboard(user_id)
                    await update.message.reply_text(self.t(user_id, "error", error=error_msg), reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating tunnel: {e}", exc_info=True)
            reply_markup = self._get_keyboard(user_id)
            await update.message.reply_text(self.t(user_id, "error", error=str(e)[:200]), reply_markup=reply_markup)
        
        del self.user_states[user_id]
        return ConversationHandler.END
    
    async def remove_tunnel_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start removing a tunnel"""
        try:
            # Handle both callback query and text message
            if hasattr(update, 'callback_query') and update.callback_query:
                query = update.callback_query
                await query.answer()
                user_id = query.from_user.id
                message = query.message
            else:
                user_id = update.effective_user.id
                message = update.message
            
            if not self.is_admin(user_id):
                reply_markup = self._get_keyboard(user_id)
                if hasattr(message, 'edit_message_text') and message:
                    await message.edit_message_text(self.t(user_id, "access_denied"))
                else:
                    await message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
                return ConversationHandler.END
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Tunnel))
                tunnels = result.scalars().all()
                
                if not tunnels:
                    reply_markup = self._get_keyboard(user_id)
                    if hasattr(message, 'edit_message_text') and message:
                        await message.edit_message_text(self.t(user_id, "no_tunnels"))
                    else:
                        await message.reply_text(self.t(user_id, "no_tunnels"), reply_markup=reply_markup)
                    return ConversationHandler.END
                
                keyboard = []
                for tunnel in tunnels:
                    keyboard.append([InlineKeyboardButton(
                        f"🗑️ {tunnel.name} ({tunnel.core})",
                        callback_data=f"rm_tunnel_{tunnel.id}"
                    )])
                keyboard.append([InlineKeyboardButton(self.t(user_id, "cancel"), callback_data="cancel")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                if hasattr(message, 'edit_message_text') and message:
                    await message.edit_message_text(self.t(user_id, "select_tunnel_to_remove"), reply_markup=reply_markup)
                else:
                    await message.reply_text(self.t(user_id, "select_tunnel_to_remove"), reply_markup=reply_markup)
                return WAITING_FOR_TUNNEL_NAME
        except Exception as e:
            logger.error(f"Error in remove_tunnel_start: {e}", exc_info=True)
            try:
                user_id = update.effective_user.id if hasattr(update, 'effective_user') else update.from_user.id if hasattr(update, 'from_user') else 0
                reply_markup = self._get_keyboard(user_id)
                if hasattr(update, 'message') and update.message:
                    await update.message.reply_text("❌ Error processing request", reply_markup=reply_markup)
            except:
                pass
            return ConversationHandler.END
    
    async def remove_tunnel_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm and remove tunnel"""
        query = update.callback_query
        await query.answer()
        
        if not query.message:
            return ConversationHandler.END
        
        tunnel_id = query.data.replace("rm_tunnel_", "")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(f"{self.api_base_url}/api/tunnels/{tunnel_id}")
                if response.status_code == 200:
                    await query.edit_message_text(self.t(query.from_user.id, "tunnel_removed"))
                else:
                    error_msg = response.text[:200] if response.text else "Unknown error"
                    await query.edit_message_text(self.t(query.from_user.id, "error", error=error_msg))
        except Exception as e:
            logger.error(f"Error removing tunnel: {e}", exc_info=True)
            await query.edit_message_text(self.t(query.from_user.id, "error", error=str(e)[:200]))
        
        return ConversationHandler.END
    
    async def cancel_operation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current operation"""
        query = update.callback_query
        await query.answer()
        
        if not query.message:
            return ConversationHandler.END
        
        user_id = query.from_user.id
        if user_id in self.user_states:
            del self.user_states[user_id]
        
        await query.edit_message_text(self.t(user_id, "cancel"))
        return ConversationHandler.END
    
    async def cmd_nodes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /nodes command"""
        user_id = update.effective_user.id
        reply_markup = self._get_keyboard(user_id)
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
            return
        
        await self.cmd_nodes_callback(update.message)
    
    async def cmd_tunnels(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tunnels command"""
        user_id = update.effective_user.id
        reply_markup = self._get_keyboard(user_id)
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
            return
        
        await self.cmd_tunnels_callback(update.message)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        user_id = update.effective_user.id
        reply_markup = self._get_keyboard(user_id)
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
            return
        
        await self.cmd_status_callback(update.message)
    
    async def cmd_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /backup command"""
        user_id = update.effective_user.id
        reply_markup = self._get_keyboard(user_id)
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
            return
        
        await update.message.reply_text("📦 Creating backup...", reply_markup=reply_markup)
        
        try:
            backup_path = await self.create_backup()
            if backup_path:
                with open(backup_path, 'rb') as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"smite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        caption="✅ Backup created successfully",
                        reply_markup=reply_markup
                    )
                os.remove(backup_path)
            else:
                await update.message.reply_text("❌ Failed to create backup", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error creating backup: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error creating backup: {str(e)}", reply_markup=reply_markup)
    
    async def cmd_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /logs command"""
        user_id = update.effective_user.id
        reply_markup = self._get_keyboard(user_id)
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.t(user_id, "access_denied"), reply_markup=reply_markup)
            return
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base_url}/api/logs?limit=20")
                if response.status_code == 200:
                    logs = response.json().get("logs", [])
                    if logs:
                        text = "📋 Recent Logs:\n\n"
                        for log in logs[-10:]:
                            text += f"`{log.get('level', 'INFO')}` {log.get('message', '')[:100]}\n\n"
                        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
                    else:
                        await update.message.reply_text("No logs available.", reply_markup=reply_markup)
                else:
                    await update.message.reply_text("Failed to fetch logs.", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error fetching logs: {e}", exc_info=True)
            await update.message.reply_text(f"Error: {str(e)}", reply_markup=reply_markup)
    
    async def create_backup(self) -> Optional[str]:
        """Create backup archive"""
        try:
            from app.config import settings
            import os
            
            backup_dir = Path("/tmp/smite_backup")
            backup_dir.mkdir(exist_ok=True)
            
            panel_root = Path(os.getcwd())
            if not (panel_root / "data").exists():
                for possible_root in [Path("/opt/smite"), Path(__file__).parent.parent.parent]:
                    if (possible_root / "data").exists():
                        panel_root = possible_root
                        break
            
            db_path = panel_root / "data" / "smite.db"
            if db_path.exists():
                shutil.copy2(db_path, backup_dir / "smite.db")
            
            env_path = panel_root / ".env"
            if env_path.exists():
                shutil.copy2(env_path, backup_dir / ".env")
            
            docker_compose = panel_root / "docker-compose.yml"
            if docker_compose.exists():
                shutil.copy2(docker_compose, backup_dir / "docker-compose.yml")
            
            certs_dir = panel_root / "certs"
            if certs_dir.exists():
                shutil.copytree(certs_dir, backup_dir / "certs", dirs_exist_ok=True)
            
            node_cert_path = Path(settings.node_cert_path)
            if not node_cert_path.is_absolute():
                node_cert_path = panel_root / node_cert_path
            if node_cert_path.exists():
                (backup_dir / "node_certs").mkdir(exist_ok=True)
                shutil.copy2(node_cert_path, backup_dir / "node_certs" / "ca.crt")
            
            node_key_path = Path(settings.node_key_path)
            if not node_key_path.is_absolute():
                node_key_path = panel_root / node_key_path
            if node_key_path.exists():
                (backup_dir / "node_certs").mkdir(exist_ok=True)
                shutil.copy2(node_key_path, backup_dir / "node_certs" / "ca.key")
            
            server_cert_path = Path(settings.node_server_cert_path)
            if not server_cert_path.is_absolute():
                server_cert_path = panel_root / server_cert_path
            if server_cert_path.exists():
                (backup_dir / "server_certs").mkdir(exist_ok=True)
                shutil.copy2(server_cert_path, backup_dir / "server_certs" / "ca-server.crt")
            
            server_key_path = Path(settings.node_server_key_path)
            if not server_key_path.is_absolute():
                server_key_path = panel_root / server_key_path
            if server_key_path.exists():
                (backup_dir / "server_certs").mkdir(exist_ok=True)
                shutil.copy2(server_key_path, backup_dir / "server_certs" / "ca-server.key")
            
            data_dir = panel_root / "data"
            if data_dir.exists():
                (backup_dir / "data").mkdir(exist_ok=True)
                for item in data_dir.iterdir():
                    if item.is_file() and item.suffix in ['.json', '.yaml', '.toml']:
                        shutil.copy2(item, backup_dir / "data" / item.name)
            
            from app.config import settings
            if settings.https_enabled and settings.panel_domain:
                nginx_dir = panel_root / "nginx"
                if nginx_dir.exists():
                    shutil.copytree(nginx_dir, backup_dir / "nginx", dirs_exist_ok=True)
                
                letsencrypt_dir = Path("/etc/letsencrypt")
                if letsencrypt_dir.exists():
                    domain_dir = letsencrypt_dir / "live" / settings.panel_domain
                    if domain_dir.exists():
                        (backup_dir / "letsencrypt" / "live" / settings.panel_domain).mkdir(parents=True, exist_ok=True)
                        for cert_file in ["fullchain.pem", "privkey.pem", "chain.pem", "cert.pem"]:
                            cert_path = domain_dir / cert_file
                            if cert_path.exists():
                                shutil.copy2(cert_path, backup_dir / "letsencrypt" / "live" / settings.panel_domain / cert_file)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = f"/tmp/smite_backup_{timestamp}.zip"
            
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(backup_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(backup_dir)
                        zipf.write(file_path, arcname)
            
            shutil.rmtree(backup_dir)
            
            return backup_file
        except Exception as e:
            logger.error(f"Error creating backup: {e}", exc_info=True)
            return None
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages from persistent keyboard"""
        try:
            if not self.is_admin(update.effective_user.id):
                return
            
            # Skip if user is in a conversation (let conversation handlers handle it)
            user_id = update.effective_user.id
            if user_id in self.user_states:
                return
            
            text = update.message.text
            if not text:
                return
            
            # Check if it's a keyboard button (translations already have emojis)
            if self.t(user_id, "node_stats") in text:
                await self.cmd_nodes_callback(update.message)
            elif self.t(user_id, "tunnel_stats") in text:
                await self.cmd_tunnels_callback(update.message)
            elif self.t(user_id, "create_tunnel") in text:
                await self.create_tunnel_start(update, context)
            elif self.t(user_id, "remove_tunnel") in text:
                await self.remove_tunnel_start(update, context)
            elif self.t(user_id, "logs") in text:
                await self.cmd_logs(update, context)
            elif self.t(user_id, "backup") in text:
                await self.cmd_backup(update, context)
            elif self.t(user_id, "language") in text:
                # Show language selection with persistent keyboard
                keyboard = [
                    [InlineKeyboardButton(self.t(user_id, "english"), callback_data="lang_en")],
                    [InlineKeyboardButton(self.t(user_id, "farsi"), callback_data="lang_fa")],
                ]
                inline_markup = InlineKeyboardMarkup(keyboard)
                persistent_keyboard = self._get_keyboard(user_id)
                await update.message.reply_text("🌐 Select Language:", reply_markup=inline_markup)
                await asyncio.sleep(0.1)
                await update.message.reply_text("⬇️", reply_markup=persistent_keyboard)
        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            try:
                user_id = update.effective_user.id
                reply_markup = self._get_keyboard(user_id)
                await update.message.reply_text("❌ Error processing request", reply_markup=reply_markup)
            except:
                pass
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        try:
            query = update.callback_query
            await query.answer()
            
            if not query.message:
                return
            
            if not self.is_admin(query.from_user.id):
                await query.edit_message_text(self.t(query.from_user.id, "access_denied"))
                return
        except Exception as e:
            logger.error(f"Error in handle_callback: {e}", exc_info=True)
            return
        
        data = query.data
        
        if data == "select_language":
            keyboard = [
                [InlineKeyboardButton(self.t(query.from_user.id, "english"), callback_data="lang_en")],
                [InlineKeyboardButton(self.t(query.from_user.id, "farsi"), callback_data="lang_fa")],
                [InlineKeyboardButton(self.t(query.from_user.id, "back"), callback_data="back_to_menu")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("🌐 Select Language:", reply_markup=reply_markup)
        elif data.startswith("lang_"):
            lang = data.replace("lang_", "")
            self.user_languages[str(query.from_user.id)] = lang
            self._save_languages()
            lang_name = "English" if lang == "en" else "Farsi"
            if query.message:
                await query.edit_message_text(self.t(query.from_user.id, "language_set", lang=lang_name))
        elif data == "back_to_menu":
            if query.message:
                text = self.t(query.from_user.id, "welcome")
                await query.edit_message_text(text)
        elif data == "node_stats":
            await self.cmd_nodes_callback(query)
        elif data == "tunnel_stats":
            await self.cmd_tunnels_callback(query)
        elif data == "logs":
            await self.cmd_logs_callback(query)
        elif data == "cmd_nodes":
            await self.cmd_nodes_callback(query)
        elif data == "cmd_tunnels":
            await self.cmd_tunnels_callback(query)
        elif data == "cmd_backup":
            await self.cmd_backup_callback(query)
        elif data == "cmd_status":
            await self.cmd_status_callback(query)
    
    async def cmd_nodes_callback(self, message_or_query):
        """Handle nodes command from callback"""
        try:
            # Get user_id and message object
            if hasattr(message_or_query, 'from_user'):
                user_id = message_or_query.from_user.id
                message = message_or_query
            elif hasattr(message_or_query, 'message') and hasattr(message_or_query.message, 'from_user'):
                user_id = message_or_query.message.from_user.id
                message = message_or_query.message
            else:
                user_id = message_or_query.chat.id if hasattr(message_or_query, 'chat') else 0
                message = message_or_query
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Node))
                nodes = result.scalars().all()
                
                reply_markup = self._get_keyboard(user_id)
                
                if not nodes:
                    text = self.t(user_id, "no_nodes")
                    if hasattr(message, 'edit_message_text') and message:
                        await message.edit_message_text(text)
                    elif hasattr(message, 'reply_text'):
                        await message.reply_text(text, reply_markup=reply_markup)
                    return
                
                text = f"📊 {self.t(user_id, 'node_stats')}:\n\n"
                active = sum(1 for n in nodes if n.status == "active")
                text += f"Total: {len(nodes)}\n"
                text += f"Active: {active}\n\n"
                
                for node in nodes:
                    status = "🟢" if node.status == "active" else "🔴"
                    role = node.node_metadata.get("role", "unknown") if node.node_metadata else "unknown"
                    text += f"{status} {node.name} ({role})\n"
                    text += f"   ID: {node.id[:8]}...\n\n"
                
                if hasattr(message, 'edit_message_text') and message:
                    await message.edit_message_text(text)
                elif hasattr(message, 'reply_text'):
                    await message.reply_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in cmd_nodes_callback: {e}", exc_info=True)
            try:
                user_id = message_or_query.from_user.id if hasattr(message_or_query, 'from_user') else 0
                reply_markup = self._get_keyboard(user_id)
                if hasattr(message_or_query, 'reply_text'):
                    await message_or_query.reply_text("❌ Error loading nodes", reply_markup=reply_markup)
                elif hasattr(message_or_query, 'edit_message_text') and message_or_query:
                    await message_or_query.edit_message_text("❌ Error loading nodes")
                elif hasattr(message_or_query, 'message'):
                    await message_or_query.message.reply_text("❌ Error loading nodes", reply_markup=reply_markup)
            except:
                pass
    
    async def cmd_tunnels_callback(self, message_or_query):
        """Handle tunnels command from callback"""
        try:
            if hasattr(message_or_query, 'from_user'):
                user_id = message_or_query.from_user.id
            elif hasattr(message_or_query, 'message') and hasattr(message_or_query.message, 'from_user'):
                user_id = message_or_query.message.from_user.id
            else:
                user_id = message_or_query.chat.id if hasattr(message_or_query, 'chat') else 0
            
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Tunnel))
                tunnels = result.scalars().all()
                
                reply_markup = self._get_keyboard(user_id)
                
                if not tunnels:
                    text = self.t(user_id, "no_tunnels")
                    if hasattr(message_or_query, 'edit_message_text') and message_or_query:
                        await message_or_query.edit_message_text(text)
                    elif hasattr(message_or_query, 'reply_text'):
                        await message_or_query.reply_text(text, reply_markup=reply_markup)
                    else:
                        await message_or_query.message.reply_text(text, reply_markup=reply_markup)
                    return
                
                text = f"📊 {self.t(user_id, 'tunnel_stats')}:\n\n"
                active = sum(1 for t in tunnels if t.status == "active")
                text += f"Total: {len(tunnels)}\n"
                text += f"Active: {active}\n"
                text += f"Error: {len(tunnels) - active}\n\n"
                
                for tunnel in tunnels[:10]:
                    status = "🟢" if tunnel.status == "active" else "🔴"
                    text += f"{status} {tunnel.name} ({tunnel.core})\n"
                
                if len(tunnels) > 10:
                    text += f"\n... and {len(tunnels) - 10} more"
                
                if hasattr(message_or_query, 'edit_message_text') and message_or_query:
                    await message_or_query.edit_message_text(text)
                elif hasattr(message_or_query, 'reply_text'):
                    reply_markup = self._get_keyboard(user_id)
                    await message_or_query.reply_text(text, reply_markup=reply_markup)
                else:
                    reply_markup = self._get_keyboard(user_id)
                    await message_or_query.message.reply_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in cmd_tunnels_callback: {e}", exc_info=True)
            try:
                user_id = message_or_query.from_user.id if hasattr(message_or_query, 'from_user') else 0
                reply_markup = self._get_keyboard(user_id)
                if hasattr(message_or_query, 'reply_text'):
                    await message_or_query.reply_text("❌ Error loading tunnels", reply_markup=reply_markup)
                elif hasattr(message_or_query, 'edit_message_text') and message_or_query:
                    await message_or_query.edit_message_text("❌ Error loading tunnels")
                elif hasattr(message_or_query, 'message'):
                    await message_or_query.message.reply_text("❌ Error loading tunnels", reply_markup=reply_markup)
            except:
                pass
    
    async def cmd_status_callback(self, message_or_query):
        """Handle status command from callback"""
        try:
            if hasattr(message_or_query, 'from_user'):
                user_id = message_or_query.from_user.id
            elif hasattr(message_or_query, 'message') and hasattr(message_or_query.message, 'from_user'):
                user_id = message_or_query.message.from_user.id
            else:
                user_id = message_or_query.chat.id if hasattr(message_or_query, 'chat') else 0
            
            async with AsyncSessionLocal() as session:
                nodes_result = await session.execute(select(Node))
                nodes = nodes_result.scalars().all()
                
                tunnels_result = await session.execute(select(Tunnel))
                tunnels = tunnels_result.scalars().all()
                
                active_nodes = sum(1 for n in nodes if n.status == "active")
                active_tunnels = sum(1 for t in tunnels if t.status == "active")
                
                text = f"""📊 Panel Status:

🖥️ Nodes: {active_nodes}/{len(nodes)} active
🔗 Tunnels: {active_tunnels}/{len(tunnels)} active
"""
                
                if hasattr(message_or_query, 'edit_message_text') and message_or_query:
                    await message_or_query.edit_message_text(text)
                elif hasattr(message_or_query, 'reply_text'):
                    reply_markup = self._get_keyboard(user_id)
                    await message_or_query.reply_text(text, reply_markup=reply_markup)
                else:
                    reply_markup = self._get_keyboard(user_id)
                    await message_or_query.message.reply_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in cmd_status_callback: {e}", exc_info=True)
            try:
                user_id = message_or_query.from_user.id if hasattr(message_or_query, 'from_user') else 0
                if hasattr(message_or_query, 'reply_text'):
                    reply_markup = self._get_keyboard(user_id)
                    await message_or_query.reply_text("❌ Error loading status", reply_markup=reply_markup)
                elif hasattr(message_or_query, 'edit_message_text') and message_or_query:
                    await message_or_query.edit_message_text("❌ Error loading status")
                elif hasattr(message_or_query, 'message'):
                    await message_or_query.message.reply_text("❌ Error loading status", reply_markup=reply_markup)
            except:
                pass
    
    async def cmd_backup_callback(self, query):
        """Handle backup command from callback"""
        user_id = query.from_user.id
        if not query.message:
            return
        
        await query.edit_message_text("📦 Creating backup...")
        
        try:
            backup_path = await self.create_backup()
            if backup_path:
                reply_markup = self._get_keyboard(user_id)
                with open(backup_path, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=f"smite_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                        caption="✅ Backup created successfully",
                        reply_markup=reply_markup
                    )
                os.remove(backup_path)
                await query.edit_message_text("✅ Backup created and sent successfully!")
            else:
                await query.edit_message_text("❌ Failed to create backup")
        except Exception as e:
            logger.error(f"Error creating backup: {e}", exc_info=True)
            await query.edit_message_text(f"❌ Error creating backup: {str(e)}")
    
    async def cmd_logs_callback(self, query):
        """Handle logs command from callback"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.api_base_url}/api/logs?limit=20")
                if response.status_code == 200:
                    logs = response.json().get("logs", [])
                    if logs:
                        text = "📋 Recent Logs:\n\n"
                        for log in logs[-10:]:
                            text += f"`{log.get('level', 'INFO')}` {log.get('message', '')[:100]}\n\n"
                        await query.edit_message_text(text, parse_mode="Markdown")
                    else:
                        await query.edit_message_text("No logs available.")
                else:
                    await query.edit_message_text("Failed to fetch logs.")
        except Exception as e:
            logger.error(f"Error fetching logs: {e}", exc_info=True)
            await query.edit_message_text(f"Error: {str(e)}")


telegram_bot = TelegramBot()
