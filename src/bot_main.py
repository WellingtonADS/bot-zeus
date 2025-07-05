# src/bot_main.py
"""
bot_main.py
Este módulo é responsável por controlar a execução principal do bot de arbitragem. Ele permite iniciar, parar e encerrar o bot com base nos comandos do usuário.
Funções:
- start_bot(stop_event): Inicia a rotina principal do bot de arbitragem.
- stop_bot(stop_event): Para a execução do bot de arbitragem.
- __main__: Controla a execução do bot com base nos comandos do usuário ('start', 'stop', 'exit').
Dependências:
- os
- sys
- threading
- time
- src.arbitrage.iniciar_bot_arbitragem
- utils.config.logger
"""
import os
import sys
import threading
import time

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from src.arbitrage import iniciar_bot_arbitragem
from utils.config import logger

def start_bot(stop_event):
    try:
        logger.info("Iniciando rotina principal do bot de arbitragem.")
        iniciar_bot_arbitragem(stop_event)
    except Exception as e:
        logger.error(f"Ocorreu um erro durante a execução do bot: {e}")
        logger.debug("Detalhes do erro", exc_info=True)

def stop_bot(stop_event):
    if stop_event.is_set():
        logger.warning("O bot já foi parado.")
    else:
        logger.info("Parando o bot de arbitragem.")
        stop_event.set()

if __name__ == "__main__":
    logger.info("Inicializando o controle principal do bot de arbitragem.")
    stop_event = threading.Event()
    bot_thread = None

    try:
        while True:
            logger.debug("Aguardando comando de entrada do usuário.")
            command = input("Digite 'start' para iniciar o bot, 'stop' para parar ou 'exit' para sair: ").strip().lower()

            if command == "start":
                if bot_thread and bot_thread.is_alive():
                    logger.warning("O bot já está em execução.")
                else:
                    logger.info("Comando 'start' recebido. Iniciando o bot de arbitragem.")
                    stop_event.clear()
                    bot_thread = threading.Thread(target=start_bot, args=(stop_event,))
                    bot_thread.start()
            elif command == "stop":
                logger.info("Comando 'stop' recebido. Parando o bot.")
                stop_bot(stop_event)
            elif command == "exit":
                logger.info("Comando 'exit' recebido. Encerrando o bot e saindo.")
                stop_bot(stop_event)
                if bot_thread:
                    bot_thread.join()
                logger.info("Bot encerrado com sucesso.")
                break
            else:
                logger.warning(f"Comando desconhecido recebido: '{command}'.")
    except KeyboardInterrupt:
        logger.critical("Execução interrompida pelo usuário (CTRL+C). Parando o bot.")
        stop_bot(stop_event)
        if bot_thread:
            bot_thread.join()
        logger.info("Bot encerrado devido à interrupção do teclado.")


