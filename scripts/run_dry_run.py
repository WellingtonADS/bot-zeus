import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Permitir flags via CLI: --rpc, --duration, --interval, --dry
args = sys.argv[1:]
arg_map = { }
for i, a in enumerate(args):
    if a.startswith('--') and i + 1 < len(args) and not args[i+1].startswith('--'):
        arg_map[a] = args[i+1]

if '--rpc' in arg_map:
    os.environ['CUSTOM_RPC_URL'] = arg_map['--rpc']
if '--duration' in arg_map:
    os.environ['AUTO_DURATION_SECONDS'] = arg_map['--duration']
if '--interval' in arg_map:
    os.environ['SCAN_INTERVAL_SECONDS'] = arg_map['--interval']
if '--dry' in args:
    os.environ['DRY_RUN'] = '1'
else:
    # respeita .env se não passado
    pass

# Sempre autostart neste runner
os.environ['BOT_AUTOSTART'] = '1'

from src.bot_main import main

if __name__ == '__main__':
    main()
