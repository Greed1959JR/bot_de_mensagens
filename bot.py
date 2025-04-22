import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes, ConversationHandler
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from pytz import timezone  # ✅ Importação adicionada para fuso horário
import logging
import asyncio

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

app = Application.builder().token(TELEGRAM_TOKEN).build()

ESCOLHER_MENSAGEM, ESCOLHER_CONTEUDO, ESCOLHER_GRUPO, ESCOLHER_DIA, ESCOLHER_HORA, AGENDAMENTO_MANUAL = range(6)

mensagens_agendadas = []

GRUPOS = {
    "vip": -1002600167995,
    "free": -1002508674229,
}

flask_app = Flask(__name__)

# ✅ Definindo o fuso horário para horário de Brasília
fuso_brasilia = timezone('America/Sao_Paulo')

# ✅ Usando o timezone na instância do scheduler
scheduler = BackgroundScheduler(timezone=fuso_brasilia)
scheduler.start()

@flask_app.route("/")
def home():
    return "Bot online!"

def rodar_flask():
    flask_app.run(host="0.0.0.0", port=3000)

# ✅ Utilitário seguro para agendamento de envio no apscheduler
# Isso evita o erro de execução atrasada em ambientes como Render
def agendar_envio_seguro(application, grupo_id, mensagem, data):
    def tarefa():
        asyncio.run_coroutine_threadsafe(_enviar_mensagem_agendada(application, grupo_id, mensagem), application.loop)
    scheduler.add_job(tarefa, trigger='date', run_date=data)

# Etapas da conversa
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botoes = [["📸 Enviar Foto"], ["📝 Enviar Texto"], ["❌ Cancelar"]]
    await update.message.reply_text("Escolha o tipo de conteúdo que deseja enviar:",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True))
    return ESCOLHER_CONTEUDO

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Ação cancelada. Digite /start para começar novamente.",
        reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
    return ConversationHandler.END

async def capturar_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "cancelar" in update.message.text.lower():
        return await cancelar(update, context)
    context.user_data['tipo'] = "foto" if "foto" in update.message.text.lower() else "texto"
    await update.message.reply_text("Me envie a mensagem que deseja agendar.")
    return ESCOLHER_MENSAGEM

async def capturar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mensagem'] = update.message
    botoes = [["VIP"], ["FREE"], ["❌ Cancelar"]]
    await update.message.reply_text("Para qual grupo deseja enviar?",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True))
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
    await update.message.reply_text("Deseja agendar para hoje, amanhã ou inserir manualmente?",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True))
    return ESCOLHER_DIA

async def escolher_dia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dia = update.message.text.strip().lower()
    if "cancelar" in dia:
        return await cancelar(update, context)
    hoje = datetime.now(fuso_brasilia)  # ✅ Data com fuso horário
    if dia == "hoje":
        context.user_data['data_base'] = hoje
    elif dia in ["amanhã", "amanha"]:
        context.user_data['data_base'] = hoje + timedelta(days=1)
    elif "manual" in dia:
        await update.message.reply_text("Digite a data e hora no formato dd/mm/aaaa hh:mm")
        return AGENDAMENTO_MANUAL
    else:
        await update.message.reply_text("Escolha 'Hoje', 'Amanhã' ou 'Inserir manualmente'.")
        return ESCOLHER_DIA
    botoes = [[str(h) for h in range(6, 13)], [str(h) for h in range(13, 19)], [str(h) for h in range(19, 24)], ["❌ Cancelar"]]
    await update.message.reply_text("Escolha o horário para envio (hora cheia):",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True))
    return ESCOLHER_HORA

async def escolher_hora(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        hora = int(update.message.text)
        data = context.user_data['data_base'].replace(hour=hora, minute=0, second=0, microsecond=0)
        grupo_id = GRUPOS[context.user_data['grupo']]
        mensagem = context.user_data['mensagem']
        agendar_envio_seguro(context.application, grupo_id, mensagem, data)
        mensagens_agendadas.append({"data": data.strftime("%d/%m/%Y %H:%M"), "grupo": context.user_data['grupo']})
        await update.message.reply_text(f"✅ Mensagem agendada para {data.strftime('%d/%m/%Y %H:%M')} no grupo {context.user_data['grupo'].upper()}.")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Horário inválido. Tente novamente.")
        return ESCOLHER_HORA

async def agendamento_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        data = fuso_brasilia.localize(datetime.strptime(update.message.text.strip(), "%d/%m/%Y %H:%M"))  # ✅ Adicionado fuso na data manual
        grupo_id = GRUPOS[context.user_data['grupo']]
        mensagem = context.user_data['mensagem']
        agendar_envio_seguro(context.application, grupo_id, mensagem, data)
        mensagens_agendadas.append({"data": data.strftime("%d/%m/%Y %H:%M"), "grupo": context.user_data['grupo']})
        await update.message.reply_text(f"✅ Mensagem agendada para {data.strftime('%d/%m/%Y %H:%M')} no grupo {context.user_data['grupo'].upper()}.")
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Formato inválido. Tente novamente: dd/mm/aaaa hh:mm")
        return AGENDAMENTO_MANUAL

async def _enviar_mensagem_agendada(app, chat_id, mensagem):
    if mensagem.text:
        await app.bot.send_message(chat_id=chat_id, text=mensagem.text)
    elif mensagem.photo:
        await app.bot.send_photo(chat_id=chat_id, photo=mensagem.photo[-1].file_id, caption=mensagem.caption or "")

# Comandos auxiliares
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    botoes = [["/start"], ["/listar"]]
    await update.message.reply_text("\ud83d\udccb Menu principal:",
        reply_markup=ReplyKeyboardMarkup(botoes, one_time_keyboard=True, resize_keyboard=True))

async def listar_agendadas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not mensagens_agendadas:
        await update.message.reply_text("\ud83d\udceb Nenhuma mensagem agendada.")
        return
    texto = "\ud83d\udd52 Mensagens agendadas:\n\n"
    for i, msg in enumerate(mensagens_agendadas, 1):
        texto += f"{i}. {msg['data']} - Grupo: {msg['grupo'].upper()}\n"
    await update.message.reply_text(texto)

async def cancelar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not mensagens_agendadas:
        await update.message.reply_text("\ud83d\udceb Nenhuma mensagem para cancelar.")
        return
    try:
        index = int(update.message.text.split()[1]) - 1
        if 0 <= index < len(mensagens_agendadas):
            mensagem_removida = mensagens_agendadas.pop(index)
            await update.message.reply_text(f"\u274c Mensagem para {mensagem_removida['data']} no grupo {mensagem_removida['grupo'].upper()} foi cancelada.")
        else:
            await update.message.reply_text("Número inválido. Use /listar para ver os agendamentos.")
    except:
        await update.message.reply_text("Formato inválido. Use: /cancelar <número da mensagem>")

async def repetir_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not mensagens_agendadas:
        await update.message.reply_text("\ud83d\udceb Nenhuma mensagem para repetir.")
        return
    try:
        index = int(update.message.text.split()[1]) - 1
        if 0 <= index < len(mensagens_agendadas):
            agendada = mensagens_agendadas[index]
            grupo_id = GRUPOS[agendada['grupo']]
            now = datetime.now(brasilia) + timedelta(seconds=5)
            def tarefa():
                context.application.create_task(
                    context.application.bot.send_message(chat_id=grupo_id, text=f"\ud83d\udd01 Reenvio: mensagem agendada para {agendada['data']}")
                )
            scheduler.add_job(lambda: context.application.job_queue._dispatcher.application.loop.call_soon_threadsafe(tarefa),
                              trigger='date', run_date=now)
            await update.message.reply_text("\ud83d\udd01 Mensagem será reenviada em instantes!")
        else:
            await update.message.reply_text("Número inválido. Use /listar para ver os agendamentos.")
    except:
        await update.message.reply_text("Formato inválido. Use: /repetir <número da mensagem>")

def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token("TELEGRAM_TOKEN").build()

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
        fallbacks=[MessageHandler(filters.Regex("(?i)^\u274c Cancelar$"), cancelar)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("listar", listar_agendadas))
    app.add_handler(CommandHandler("cancelar", cancelar_mensagem))
    app.add_handler(CommandHandler("repetir", repetir_mensagem))

    print("Bot rodando...")
    Thread(target=rodar_flask).start()
    app.run_polling()

if __name__ == "__main__":
    main()
