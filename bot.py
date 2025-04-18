from telegram import Update, InputMediaPhoto, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, ConversationHandler
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import logging
import asyncio

# Estados do agendamento
ESCOLHER_MENSAGEM, ESCOLHER_CONTEUDO, ESCOLHER_GRUPO, ESCOLHER_DIA, ESCOLHER_HORA, AGENDAMENTO_MANUAL = range(6)

# Onde você salva mensagens agendadas
agendamentos = {}

# Inicia o scheduler
scheduler = BackgroundScheduler()
scheduler.start()

# Dicionário de grupos
GRUPOS = {
    "vip": -1001234567890,
    "free": -1009876543210,
}

# Flask app para manter vivo no UptimeRobot
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot online!"

def rodar_flask():
    flask_app.run(host="0.0.0.0", port=3000)

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Ação cancelada. Digite /start para começar novamente.", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botoes = [["📸 Enviar Foto"], ["📝 Enviar Texto"], ["❌ Cancelar"]]
    await update.message.reply_text(
        "Escolha o tipo de conteúdo que deseja enviar:",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True)
    )
    return ESCOLHER_CONTEUDO

async def capturar_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "cancelar" in update.message.text.lower():
        return await cancelar(update, context)
    context.user_data['tipo'] = "foto" if "foto" in update.message.text.lower() else "texto"
    await update.message.reply_text("Me envie a mensagem que deseja agendar.")
    return ESCOLHER_MENSAGEM

async def capturar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mensagem'] = update.message
    botoes = [["VIP"], ["FREE"], ["❌ Cancelar"]]
    await update.message.reply_text(
        "Para qual grupo deseja enviar?",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True)
    )
    return ESCOLHER_GRUPO

async def escolher_grupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    grupo = update.message.text.lower().strip()
    if "cancelar" in grupo:
        return await cancelar(update, context)
    if grupo not in GRUPOS:
        await update.message.reply_text("Grupo inválido. Escolha 'VIP' ou 'FREE'.")
        return ESCOLHER_GRUPO
    context.user_data['grupo'] = grupo
    botoes = [["Hoje"], ["Amanhã"], ["✍️ Inserir data manualmente"], ["❌ Cancelar"]]
    await update.message.reply_text(
        "Deseja agendar para hoje, amanhã ou inserir manualmente?",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True)
    )
    return ESCOLHER_DIA

async def escolher_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dia = update.message.text.strip().lower()
    if "cancelar" in dia:
        return await cancelar(update, context)
    hoje = datetime.now()
    if dia == "hoje":
        context.user_data['data_base'] = hoje
    elif dia == "amanhã" or dia == "amanha":
        context.user_data['data_base'] = hoje + timedelta(days=1)
    elif "manual" in dia:
        await update.message.reply_text("Digite a data e hora no formato dd/mm/aaaa hh:mm")
        return AGENDAMENTO_MANUAL
    else:
        await update.message.reply_text("Escolha 'Hoje', 'Amanhã' ou 'Inserir manualmente'.")
        return ESCOLHER_DIA

    botoes = [[str(h) for h in range(6, 13)], [str(h) for h in range(13, 19)], [str(h) for h in range(19, 24)], ["❌ Cancelar"]]
    await update.message.reply_text(
        "Escolha o horário para envio (hora cheia):",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True)
    )
    return ESCOLHER_HORA

async def _enviar_mensagem_agendada(app, chat_id, mensagem):
    if mensagem.text:
        await app.bot.send_message(chat_id=chat_id, text=mensagem.text)
    elif mensagem.photo:
        await app.bot.send_photo(chat_id=chat_id, photo=mensagem.photo[-1].file_id, caption=mensagem.caption or "")

async def agendamento_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = datetime.strptime(update.message.text.strip(), "%d/%m/%Y %H:%M")
        grupo_id = GRUPOS[context.user_data['grupo']]
        mensagem = context.user_data['mensagem']

        def tarefa():
            context.application.create_task(_enviar_mensagem_agendada(context.application, grupo_id, mensagem))

        scheduler.add_job(
            func=lambda: context.application.job_queue._dispatcher.application.loop.call_soon_threadsafe(tarefa),
            trigger='date',
            run_date=data,
        )

        await update.message.reply_text(f"✅ Mensagem agendada para {data.strftime('%d/%m/%Y %H:%M')} no grupo {context.user_data['grupo'].upper()}.")
        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text("❌ Formato inválido. Tente novamente: dd/mm/aaaa hh:mm")
        print(e)
        return AGENDAMENTO_MANUAL

async def escolher_hora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        hora = int(update.message.text)
        data = context.user_data['data_base'].replace(hour=hora, minute=0, second=0, microsecond=0)
        grupo_id = GRUPOS[context.user_data['grupo']]
        mensagem = context.user_data['mensagem']

        def tarefa():
            context.application.create_task(_enviar_mensagem_agendada(context.application, grupo_id, mensagem))

        scheduler.add_job(
            func=lambda: context.application.job_queue._dispatcher.application.loop.call_soon_threadsafe(tarefa),
            trigger='date',
            run_date=data,
        )

        await update.message.reply_text(f"✅ Mensagem agendada para {data.strftime('%d/%m/%Y %H:%M')} no grupo {context.user_data['grupo'].upper()}.")
        return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text("❌ Horário inválido. Tente novamente escolhendo um número inteiro de hora.")
        print(e)
        return ESCOLHER_HORA

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token("8071917672:AAG4R5z7b7w6PrOOLQ7Bi4nafMLy0LOL0I4").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ESCOLHER_CONTEUDO: [MessageHandler(filters.TEXT & ~filters.COMMAND, capturar_tipo)],
            ESCOLHER_MENSAGEM: [MessageHandler(filters.ALL & ~filters.COMMAND, capturar_mensagem)],
            ESCOLHER_GRUPO: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_grupo)],
            ESCOLHER_DIA: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_dia)],
            ESCOLHER_HORA: [MessageHandler(filters.TEXT & ~filters.COMMAND, escolher_hora)],
            AGENDAMENTO_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, agendamento_manual)],
        },
        fallbacks=[MessageHandler(filters.Regex("(?i)^❌ Cancelar$"), cancelar)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    print("Bot rodando...")
    Thread(target=rodar_flask).start()
    app.run_polling()

if __name__ == "__main__":
    main()
