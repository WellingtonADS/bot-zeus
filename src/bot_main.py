"""
Ponto de entrada principal para o Bot de Arbitragem ZEUS.
"""
import os
import sys
import threading
import time

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from src.arbitrage import iniciar_bot_arbitragem
from utils.config import logger

def run_bot_thread(stop_event: threading.Event):
    try:
        logger.info("Thread do bot iniciada. A chamar a lógica de arbitragem...")
        iniciar_bot_arbitragem(stop_event)
    except Exception as e:
        logger.critical(f"Erro fatal na thread do bot: {e}", exc_info=True)
    finally:
        logger.info("Thread do bot finalizada.")

def main():
    logger.info("========================================")
    logger.info("Bem-vindo ao Painel de Controle do Bot ZEUS")
    logger.info("========================================")
    
    stop_event = threading.Event()
    bot_thread: threading.Thread | None = None

    try:
        while True:
            command = input("Digite 'start', 'stop' ou 'exit': ").strip().lower()

            if command == "start":
                if bot_thread and bot_thread.is_alive():
                    logger.warning("O bot já está em execução.")
                else:
                    logger.info("Comando 'start' recebido. A iniciar o bot em uma nova thread...")
                    stop_event.clear()
                    bot_thread = threading.Thread(target=run_bot_thread, args=(stop_event,), daemon=True)
                    bot_thread.start()
            
            elif command == "stop":
                if not bot_thread or not bot_thread.is_alive():
                    logger.warning("O bot não está em execução.")
                else:
                    logger.info("Comando 'stop' recebido. A sinalizar para o bot parar...")
                    stop_event.set()
            
            elif command == "exit":
                logger.info("Comando 'exit' recebido. A encerrar o programa...")
                if bot_thread and bot_thread.is_alive():
                    logger.info("A sinalizar para o bot parar antes de sair...")
                    stop_event.set()
                    bot_thread.join(timeout=10)
                
                logger.info("Programa encerrado.")
                break
            
            else:
                logger.warning(f"Comando desconhecido: '{command}'. Comandos válidos: start, stop, exit.")
    
    except KeyboardInterrupt:
        logger.info("\nInterrupção de teclado (Ctrl+C) detectada. A encerrar...")
        if bot_thread and bot_thread.is_alive():
            stop_event.set()
            bot_thread.join(timeout=10)
    
    finally:
        logger.info("Controle principal finalizado.")

if __name__ == "__main__":
    main()
