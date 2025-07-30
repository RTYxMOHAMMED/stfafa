from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import subprocess
import sqlite3
import asyncio
import os

# الإعدادات
BOT_TOKEN = "8295167666:AAGgCn4TsE-3U3QgE22Om_VCpqlJVzTnzmg"
ADMIN_USER_IDS = [8436319138]  # أضف أيدي المستخدمين المسموح لهم
DATABASE = 'hosting.db'
TOOLS_DIR = 'tools'

# إنشاء مجلد الأدوات
os.makedirs(TOOLS_DIR, exist_ok=True)

# إعداد قاعدة البيانات
conn = sqlite3.connect(DATABASE, check_same_thread=False)
cursor = conn.cursor()

# إنشاء الجدول (بدون جدول السجلات)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tools (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        file_path TEXT NOT NULL,
        status TEXT DEFAULT 'stopped',
        pid INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

# التحقق من الصلاحيات
def is_authorized(user_id):
    return user_id in ADMIN_USER_IDS

# تحديث حالة الأداة
def update_tool_status(name, status, pid=None):
    cursor.execute('''
        UPDATE tools SET status = ?, pid = ? WHERE name = ?
    ''', (status, pid, name))
    conn.commit()

# الحصول على الأداة
def get_tool(name):
    cursor.execute('SELECT * FROM tools WHERE name = ?', (name,))
    return cursor.fetchone()

# ----------------------------------------
# الأوامر الأساسية
# ----------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.message.from_user.id):
        await update.message.reply_text("عذراً، ليس لديك صلاحية.")
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة أداة", callback_data="add_tool")],
        [InlineKeyboardButton("🖥️ لوحة التحكم", callback_data="control_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("> مرحباً بكم في بوت وهم ذكريات هذا بوت مميز", reply_markup=reply_markup)

# إضافة أداة جديدة
async def add_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_authorized(query.from_user.id):
        await query.edit_message_text("عذراً، ليس لديك صلاحية.")
        return
    await query.edit_message_text("إرسـل ملف الأداة Python (.py) مباشرةً:")

# معالجة رفع الملف
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.message.from_user.id):
        return
    
    document = update.message.document
    if not document.file_name.endswith('.py'):
        await update.message.reply_text("يرجى رفع ملفات Python فقط (.py)")
        return
    
    if ' ' in document.file_name:
        await update.message.reply_text("❌ أسماء الملفات لا يمكن أن تحتوي على مسافات")
        return
    
    try:
        # حفظ الملف
        file_path = os.path.join(TOOLS_DIR, document.file_name)
        with open(file_path, 'wb') as f:
            file = await context.bot.get_file(document.file_id)
            await file.download_to_memory(f)
        
        # إضافة إلى قاعدة البيانات
        cursor.execute('''
            INSERT INTO tools (name, file_path) VALUES (?, ?)
        ''', (document.file_name, file_path))
        conn.commit()
        await update.message.reply_text(f"✅ تم تثبيت: {document.file_name} بنجاح!")
        await control_panel(update, context)  # تحديث اللوحة
        
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

# ----------------------------------------
# لوحة التحكم
# ----------------------------------------
async def control_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        if not is_authorized(query.from_user.id):
            await query.edit_message_text("عذراً، ليس لديك صلاحية.")
            return
    
    cursor.execute('SELECT name, status FROM tools')
    tools = cursor.fetchall()
    
    if not tools:
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await (query.edit_message_text if query else update.message.reply_text)(
            "لا يوجد أدوات مضافة.",
            reply_markup=reply_markup
        )
        return
    
    keyboard = []
    for tool in tools:
        name, status = tool
        status_emoji = "🟢" if status == 'running' else "🔴"
        keyboard.append([
            InlineKeyboardButton(f"{status_emoji} {name}", callback_data=f"manage:{name}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="start")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = "لوحة التحكم بالادوات:\n" + "\n".join([f"{row[0].text}" for row in keyboard[:-1]])
    
    if query:
        await query.edit_message_text(message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, reply_markup=reply_markup)

# إدارة الأداة
async def manage_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tool_name = query.data.split(':')[1]
    tool = get_tool(tool_name)
    
    if not tool:
        await query.edit_message_text("الأداة غير موجودة.")
        return
    
    keyboard = [
        [InlineKeyboardButton("🚀 تشغيل" if tool[3] == 'stopped' else "🛑 إيقاف", callback_data=f"toggle:{tool_name}")],
        [InlineKeyboardButton("🗑️ حذف", callback_data=f"delete:{tool_name}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="control_panel")]
    ]
    
    status_emoji = "🟢" if tool[3] == 'running' else "🔴"
    message = f"الأداة: {tool[1]}\nالحالة: {status_emoji} {tool[3]}"
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

# تبديل حالة الأداة (تشغيل/إيقاف)
async def toggle_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tool_name = query.data.split(':')[1]
    tool = get_tool(tool_name)
    
    if not tool:
        await query.edit_message_text("الأداة غير موجودة.")
        return
    
    if tool[3] == 'stopped':
        await execute_tool(tool_name, query.message.chat_id, context)
    else:
        await stop_tool(tool_name, query.message.chat_id, context)
    
    await control_panel(update, context)  # تحديث اللوحة

# تشغيل الأداة
async def execute_tool(tool_name, chat_id, context):
    tool = get_tool(tool_name)
    if not tool:
        await context.bot.send_message(chat_id, "الأداة غير موجودة.")
        return
    
    try:
        process = await asyncio.create_subprocess_exec(
            'python3', tool[2],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        update_tool_status(tool[1], 'running', process.pid)
        asyncio.create_task(monitor_tool(tool_name, process, chat_id, context))
        await context.bot.send_message(chat_id, f"🚀 جارٍ تشغيل الأداة {tool_name}...")
        
    except FileNotFoundError:
        await context.bot.send_message(chat_id, "❌ خطأ: تأكد من تثبيت Python 3")
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ خطأ في التشغيل: {str(e)}")

# مراقبة الأداة
async def monitor_tool(tool_name, process, chat_id, context):
    stdout, stderr = await process.communicate()
    if process.returncode == 0:
        await context.bot.send_message(chat_id, f"✅ ناتج الأداة {tool_name}:\n{stdout.decode()}")
    else:
        await context.bot.send_message(chat_id, f"❌ خطأ في الأداة {tool_name}:\n{stderr.decode()}")
        update_tool_status(tool_name, 'stopped')

# إيقاف الأداة
async def stop_tool(tool_name, chat_id, context):
    tool = get_tool(tool_name)
    if not tool:
        await context.bot.send_message(chat_id, "الأداة غير موجودة.")
        return
    
    try:
        if tool[4]:
            process = await asyncio.create_subprocess_exec(
                'kill', '-9', str(tool[4]),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            await process.communicate()
        update_tool_status(tool[1], 'stopped')
        await context.bot.send_message(chat_id, f"🛑 تم إيقاف الأداة {tool_name}")
        
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ خطأ: {str(e)}")

# حذف الأداة
async def delete_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tool_name = query.data.split(':')[1]
    tool = get_tool(tool_name)
    
    if not tool:
        await query.edit_message_text("الأداة غير موجودة.")
        return
    
    try:
        if tool[3] == 'running':
            await stop_tool(tool_name, query.message.chat_id, context)
        
        if os.path.exists(tool[2]):
            os.remove(tool[2])
        
        cursor.execute('DELETE FROM tools WHERE name = ?', (tool[1],))
        conn.commit()
        await query.edit_message_text(f"🗑️ تم حذف: {tool_name} من النظام")
        await control_panel(update, context)  # تحديث اللوحة
        
    except Exception as e:
        await query.edit_message_text(f"❌ خطأ: {str(e)}")

# ----------------------------------------
# إعداد البوت
# ----------------------------------------
if __name__ == '__main__':
    application = Application.builder().token(BOT_TOKEN).build()
    
    # معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # معالجات الأزرار التفاعلية
    application.add_handler(CallbackQueryHandler(add_tool, pattern=r"^add_tool$"))
    application.add_handler(CallbackQueryHandler(control_panel, pattern=r"^control_panel$"))
    application.add_handler(CallbackQueryHandler(toggle_tool, pattern=r"^toggle:"))
    application.add_handler(CallbackQueryHandler(manage_tool, pattern=r"^manage:"))
    application.add_handler(CallbackQueryHandler(delete_tool, pattern=r"^delete:"))
    
    # تشغيل البوت
    application.run_polling()