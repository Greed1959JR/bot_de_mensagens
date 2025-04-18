from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, ConversationHandler
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from flask import Flask
from threading import Thread
import logging

# Estados do agendamento
ESCOLHER_GRUPO, ESCOLHER_DATA = range(2)

# Onde você salva mensagens agendadas
agendamentos = {}

# Inicia o scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Dicionário de grupos
GRUPOS = {
    "vip": -1001234567890,   # substitua pelo ID real do grupo VIP
    "free": -1009876543210,  # substitua pelo ID real do grupo FREE
}

# Flask app para manter vivo no UptimeRobot
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot online!"

def rodar_flask():
    flask_app.run(host="0.0.0.0", port=3000)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Me envie a mensagem que deseja agendar (pode ser texto, foto, etc).")
    return ESCOLHER_GRUPO

async def capturar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mensagem'] = update.message  # Salva a mensagem completa (pode ser texto, foto, etc)
    await update.message.reply_text("Para qual grupo deseja enviar? (vip / free)")
    return ESCOLHER_DATA

async def escolher_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    grupo = update.message.text.lower()
    if grupo not in GRUPOS:
        await update.message.reply_text("Grupo inválido. Digite 'vip' ou 'free'.")
        return ESCOLHER_DATA

    context.user_data['grupo'] = grupo
    await update.message.reply_text("Quando deseja enviar? (formato: dd/mm/aaaa hh:mm)")
    return ConversationHandler.END

async def agendar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        horario = datetime.strptime(update.message.text, "%d/%m/%Y %H:%M")
        grupo_id = GRUPOS[context.user_data['grupo']]
        mensagem = context.user_data['mensagem']

        # Agenda o envio
        scheduler.add_job(
            func=enviar_mensagem_agendada,
            trigger='date',
            run_date=horario,
            args=[context.application, grupo_id, mensagem],
        )

        await update.message.reply_text(f"✅ Mensagem agendada para {horario.strftime('%d/%m/%Y %H:%M')} no grupo {context.user_data['grupo'].upper()}.")

    except Exception as e:
        await update.message.reply_text("❌ Data/hora inválida. Tente novamente. (formato: dd/mm/aaaa hh:mm)")
        print(e)

async def enviar_mensagem_agendada(app, chat_id, mensagem):
    if mensagem.text:
        await app.bot.send_message(chat_id=chat_id, text=mensagem.text)
    elif mensagem.photo:
        await app.bot.send_photo(chat_id=chat_id, photo=mensagem.photo[-1].file_id, caption=mensagem.caption or "")
    # Pode adicionar outros tipos (vídeo, áudio, etc) se quiser

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token("8071917672:AAG4R5z7b7w6PrOOLQ7Bi4nafMLy0LOL0I4").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ESCOLHER_GRUPO: [MessageHandler(filters.ALL & ~filters.COMMAND, capturar_mensagem)],
            ESCOLHER_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_grupo)],
        },
        fallbacks=[],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, agendar_mensagem))

    print("Bot rodando...")
    Thread(target=rodar_flask).start()  # Inicia o servidor Flask numa thread separada
    app.run_polling()

if __name__ == "__main__":
    main()
