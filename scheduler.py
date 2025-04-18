# scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
import logging

scheduler = BackgroundScheduler()
scheduler.start()

def agendar_mensagem(func, data_hora, args=()):
    try:
        scheduler.add_job(
            func=func,
            trigger='date',
            run_date=data_hora,
            args=args
        )
        return True
    except Exception as e:
        logging.error(f"Erro ao agendar mensagem: {e}")
        return False
