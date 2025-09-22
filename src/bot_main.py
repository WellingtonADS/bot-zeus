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

LOCK_PATH = os.path.join(base_dir, "logs", "bot_zeus.lock")

def _acquire_singleton_lock():
    try:
        os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
        if os.path.exists(LOCK_PATH):
            allow_multi = os.getenv("ALLOW_MULTIPLE", "0").lower() in ("1","true","yes","on")
            if not allow_multi:
                # Se o lock tem menos de 5 minutos, assumir instância ativa
                mtime = os.path.getmtime(LOCK_PATH)
                if time.time() - mtime < 300:
                    logger.critical(
                        "Outra instância do bot parece estar ativa (lock recente em %s). Defina ALLOW_MULTIPLE=1 para ignorar.",
                        LOCK_PATH
                    )
                    sys.exit(1)
        with open(LOCK_PATH, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logger.warning("Não foi possível criar/verificar lockfile: %s", e)

def run_bot_thread(stop_event: threading.Event):
    try:
        logger.info("Thread do bot iniciada. A chamar a lógica de arbitragem...")
        iniciar_bot_arbitragem(stop_event)
    except Exception as e:
        logger.critical(f"Erro fatal na thread do bot: {e}", exc_info=True)
    finally:
        logger.info("Thread do bot finalizada.")

def main():
    _acquire_singleton_lock()
    logger.info("========================================")
    logger.info("Bem-vindo ao Painel de Controle do Bot ZEUS")
    logger.info("========================================")
    
    stop_event = threading.Event()
    bot_thread: threading.Thread | None = None

    try:
        # Modo autostart: permite iniciar automaticamente sem interação
        auto = os.getenv("BOT_AUTOSTART", "0").lower() in ("1", "true", "yes", "on")
        auto_duration = int(os.getenv("AUTO_DURATION_SECONDS", "0"))  # 0 = até stop manual

        if auto:
            logger.info("BOT_AUTOSTART=on: iniciando bot automaticamente.")
            stop_event.clear()
            bot_thread = threading.Thread(target=run_bot_thread, args=(stop_event,), daemon=True)
            bot_thread.start()

            if auto_duration > 0:
                logger.info(f"Execução automática por {auto_duration}s. Depois irá parar e sair.")
                time.sleep(auto_duration)
                stop_event.set()
                bot_thread.join(timeout=10)
                logger.info("Encerrando após modo autostart temporizado.")
                return

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
        # Remover lock ao sair
        try:
            if os.path.exists(LOCK_PATH):
                os.remove(LOCK_PATH)
        except Exception:
            pass
        logger.info("Controle principal finalizado.")

if __name__ == "__main__":
    main()
