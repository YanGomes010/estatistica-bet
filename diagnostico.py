import sys, os
sys.path.insert(0, '.')

print("Python:", sys.version)
print("Pasta :", os.getcwd())
print()

testes = [
    ("config",   "from config import COMPETITIONS, DEFAULT_SEASON, get_current_season, APISPORTS_KEY"),
    ("helpers",  "from src.utils.helpers import check_api_configured"),
    ("cache",    "from src.cache.cache_manager import get_cache"),
    ("espn",     "from src.fetchers import espn"),
    ("fetcher",  "from src.fetchers.api_football import get_fetcher, FootballDataFetcher"),
    ("form",     "from src.analytics.form import compute_form"),
    ("h2h",      "from src.analytics.h2h import compute_h2h"),
    ("betting",  "from src.analytics.betting import generate_betting_report"),
]

ok = 0
for nome, cmd in testes:
    try:
        exec(cmd)
        print(f"  OK   {nome}")
        ok += 1
    except Exception as e:
        print(f"  ERRO {nome}: {e}")

print()
if ok == len(testes):
    print("TODOS OS IMPORTS OK!")
else:
    print(f"{ok}/{len(testes)} imports funcionando")

print()
print("Pressione Enter para fechar...")
input()
