import argparse
import re
from pathlib import Path
from datetime import datetime


TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})")
SCAN_RE = re.compile(r"Procurando nova oportunidade de arbitragem")
NO_OPP_RE = re.compile(r"Nenhuma oportunidade.*encontrada no momento\.")
NEW_OPP_RE = re.compile(r"Nova oportunidade .* encontrada: ([\-0-9\.]+) USDC\.")
BEST_SEL_RE = re.compile(r"Melhor oportunidade de teste selecionada .*Lucro: ([\-0-9\.]+)")
EXEC_RE = re.compile(r"A executar\.\.\.")
START_SIZE_RE = re.compile(r"A procurar oportunidades com ([0-9\.]+) USDC\.")
TOP3_RE = re.compile(r"TOP3: rank=(\d+) lucro=([\-0-9\.]+) USDC compra=([^\s]+) venda=([^\s]+).+?size_base=(\d+) token_alvo=([0-9xa-fA-F]+)")


def parse_log(file_path: Path):
    stats = {
        "scans": 0,
        "no_opportunity": 0,
        "new_opportunities": 0,
        "profits": [],
        "best_selections": 0,
        "best_profits": [],
        "executions": 0,
        "start_sizes": set(),
        "top3_total": 0,
        "top1_count": 0,
        "top1_profits": [],
        "first_ts": None,
        "last_ts": None,
    }

    if not file_path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {file_path}")

    with file_path.open('r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # timestamps
            m = TS_RE.match(line)
            if m:
                try:
                    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S,%f")
                    if stats["first_ts"] is None:
                        stats["first_ts"] = ts
                    stats["last_ts"] = ts
                except Exception:
                    pass

            if SCAN_RE.search(line):
                stats["scans"] += 1
            if NO_OPP_RE.search(line):
                stats["no_opportunity"] += 1
            m = NEW_OPP_RE.search(line)
            if m:
                stats["new_opportunities"] += 1
                try:
                    profit = float(m.group(1))
                    stats["profits"].append(profit)
                except Exception:
                    pass
            m = BEST_SEL_RE.search(line)
            if m:
                stats["best_selections"] += 1
                try:
                    profit = float(m.group(1))
                    stats["best_profits"].append(profit)
                except Exception:
                    pass
            if EXEC_RE.search(line):
                stats["executions"] += 1
            m = START_SIZE_RE.search(line)
            if m:
                try:
                    stats["start_sizes"].add(float(m.group(1)))
                except Exception:
                    pass
            m = TOP3_RE.search(line)
            if m:
                stats["top3_total"] += 1
                try:
                    rank = int(m.group(1))
                    lucro = float(m.group(2))
                    if rank == 1:
                        stats["top1_count"] += 1
                        stats["top1_profits"].append(lucro)
                except Exception:
                    pass

    return stats


def main():
    parser = argparse.ArgumentParser(description="Resumo objetivo do log do bot")
    parser.add_argument("--file", default=str(Path("logs") / "bot_zeus.log"), help="Caminho do arquivo de log")
    args = parser.parse_args()

    file_path = Path(args.file)
    stats = parse_log(file_path)

    scans = stats["scans"]
    no_opp = stats["no_opportunity"]
    new_opp = stats["new_opportunities"]
    profits = stats["profits"]
    best_sel = stats["best_selections"]
    best_profits = stats["best_profits"]
    execs = stats["executions"]
    sizes = sorted(stats["start_sizes"]) if stats["start_sizes"] else []
    top3_total = stats["top3_total"]
    top1_count = stats["top1_count"]
    top1_profits = stats["top1_profits"]

    def fmt_range(values):
        if not values:
            return "n/a"
        return f"min {min(values):.6f}, max {max(values):.6f}, média {sum(values)/len(values):.6f}"

    window = "n/a"
    if stats["first_ts"] and stats["last_ts"]:
        window = f"{stats['first_ts']} → {stats['last_ts']}"

    positives = [p for p in profits if p > 0]

    print("=== Resumo do Log ===")
    print(f"Arquivo: {file_path}")
    print(f"Janela de tempo: {window}")
    print("")
    print(f"Varreduras (scans): {scans}")
    print(f"Sem oportunidade: {no_opp}")
    print(f"Oportunidades detectadas (linhas 'Nova oportunidade'): {new_opp}")
    print(f"Lucros (todos) → {fmt_range(profits)}")
    print(f"Lucros positivos detectados: {len(positives)}")
    print(f"Seleções de melhor oportunidade: {best_sel}")
    print(f"Lucro das seleções → {fmt_range(best_profits)}")
    print(f"Eventos 'A executar...': {execs}")
    if sizes:
        print(f"Tamanhos de entrada observados (USDC): {', '.join(str(s) for s in sizes)}")
    print("")
    print("— Diagnóstico TOP3 —")
    print(f"Linhas TOP3 registradas: {top3_total}")
    print(f"Ciclos com TOP1: {top1_count}")
    print(f"Lucros TOP1 → {fmt_range(top1_profits)}")


if __name__ == "__main__":
    main()
