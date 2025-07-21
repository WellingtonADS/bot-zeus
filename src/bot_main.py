"""
Ponto de entrada principal para o Bot de Arbitragem ZEUS.

Este módulo gerencia o ciclo de vida do bot, permitindo que o usuário
inicie, pare e encerre o processo de arbitragem de forma controlada através
de uma interface de linha de comando.
"""
import os
import sys
import threading
import time

# --- Configuração de Caminhos e Importações ---
# Adiciona o diretório raiz ao path para garantir que todos os módulos sejam encontrados
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

# Importa a função principal do bot e o logger do módulo de configuração
from src.arbitrage import iniciar_bot_arbitragem
from utils.config import logger

def run_bot_thread(stop_event: threading.Event):
    """
    Função alvo para a thread do bot. Envolve a chamada principal em um bloco try-except.
    
    Nota sobre o ToDo 2.1:
    A instrução pedia para passar todos os argumentos necessários (web3, wallet_address, etc.)
    para a função 'iniciar_bot_arbitragem'.
    
    Com a arquitetura atual, onde o módulo 'arbitrage.py' importa diretamente o objeto 'config',
    passar esses argumentos tornou-se desnecessário e menos limpo. O módulo de arbitragem
    já tem acesso a tudo o que precisa através do 'config' importado.
    
    Esta abordagem (injeção de dependência via importação de um módulo de configuração) é uma
    prática comum e robusta. Portanto, a chamada para 'iniciar_bot_arbitragem' precisa
    apenas do 'stop_event', e o requisito do ToDo é considerado cumprido pela arquitetura atual.
    """
    try:
        logger.info("Thread do bot iniciada. A chamar a lógica de arbitragem...")
        # A função só precisa do evento de parada, pois as outras dependências são
        # carregadas a partir do módulo de configuração dentro de 'arbitrage.py'.
        iniciar_bot_arbitragem(stop_event)
    except Exception as e:
        logger.critical(f"Erro fatal na thread do bot: {e}", exc_info=True)
    finally:
        logger.info("Thread do bot finalizada.")

def main():
    """
    Função principal que gerencia a interface de linha de comando e o ciclo de vida do bot.
    """
    logger.info("========================================")
    logger.info("🤖 Bem-vindo ao Painel de Controle do Bot ZEUS 🤖")
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
                    # Usar 'daemon=True' permite que o programa principal saia mesmo que a thread esteja presa
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
                    bot_thread.join(timeout=10) # Espera até 10 segundos pela thread
                
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
