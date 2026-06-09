from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import csv
import time
import os
import sys
import random  # Importado para gerar o delay aleatório

# ---------------------------------------------------------------------------
# CONFIGURAÇÕES — edite aqui
# ---------------------------------------------------------------------------
START_PAGE          = 1
END_PAGE            = 1778   # Agora você pode colocar o limite máximo com segurança
OUTPUT_CSV          = "bgg_ranking.csv"
MIN_DELAY           = 4.0    # Tempo mínimo de espera em segundos
MAX_DELAY           = 7.5    # Tempo máximo de espera em segundos
# ---------------------------------------------------------------------------

BASE_URL = "https://boardgamegeek.com/browse/boardgame"


def build_driver() -> webdriver.Chrome:
    """Cria o Chrome com configurações mínimas para estabilidade."""
    print("Iniciando o navegador...")
    options = Options()
    
    # Manteremos apenas os essenciais para evitar crash por falta de memória no Windows
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(options=options)
    return driver


def get_page_html(driver: webdriver.Chrome, page_num: int) -> str | None:
    """Navega até a página e retorna o HTML após o carregamento da tabela."""
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/page/{page_num}"
    try:
        driver.get(url)
        # Aguarda a tabela de jogos aparecer (até 15 s)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "collectionitems"))
        )
        return driver.page_source
    except Exception as e:
        print(f"  [ERRO] Página {page_num}: {e}", file=sys.stderr)
        return None


def parse_page(html: str) -> list[dict]:
    """Extrai os dados dos jogos do HTML da página."""
    soup = BeautifulSoup(html, "lxml")
    games = []

    for row in soup.select("tr[id='row_']"):
        game = {}

        # Rank
        rank_td = row.select_one("td.collection_rank")
        if not rank_td:
            continue
        game["rank"] = rank_td.get_text(strip=True)

        # Título e ano
        name_div = row.select_one("div[id^='results_objectname']")
        if name_div:
            title_a = name_div.select_one("a.primary")
            game["title"] = title_a.get_text(strip=True) if title_a else ""
            year_span = name_div.select_one("span.smallerfont.dull")
            game["year"] = year_span.get_text(strip=True).strip("()") if year_span else ""
        else:
            game["title"] = game["year"] = ""

        # Descrição
        desc_p = row.select_one("p.smallefont.dull")
        game["description"] = desc_p.get_text(strip=True) if desc_p else ""

        # Ratings
        rtds = row.select("td.collection_bggrating")
        game["geek_rating"] = rtds[0].get_text(strip=True) if len(rtds) > 0 else ""
        game["avg_rating"]  = rtds[1].get_text(strip=True) if len(rtds) > 1 else ""
        game["num_voters"]  = rtds[2].get_text(strip=True) if len(rtds) > 2 else ""

        # Preço
        price_span = row.select_one("td.collection_shop span.positive")
        if price_span:
            pt = price_span.get_text(strip=True)
            game["price"] = pt if pt.startswith("$") else ""
        else:
            game["price"] = ""

        games.append(game)

    return games


def append_to_csv(games: list[dict], path: str) -> None:
    """Adiciona os jogos ao CSV. Cria o cabeçalho se o arquivo não existir."""
    fields = ["rank", "title", "year", "description",
              "geek_rating", "avg_rating", "num_voters", "price"]
    
    # Verifica se o arquivo já existe para saber se deve escrever o cabeçalho
    file_exists = os.path.isfile(path)
    
    # "a" significa append (adicionar ao final)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        writer.writerows(games)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"BGG Scraper — páginas {START_PAGE} a {END_PAGE}")
    print("=" * 50)

    driver = build_driver()
    total_games_collected = 0

    try:
        for page in range(START_PAGE, END_PAGE + 1):
            print(f"  Coletando página {page}/{END_PAGE}…")
            html = get_page_html(driver, page)
            
            if html is None:
                print(f"  [AVISO] Pulando página {page}.")
                continue
                
            games = parse_page(html)
            
            if games:
                # Salva os dados no exato momento em que a página é lida
                append_to_csv(games, OUTPUT_CSV)
                total_games_collected += len(games)
                print(f"    → {len(games)} jogos salvos no CSV. (Total acumulado: {total_games_collected})")
            else:
                print(f"    → Nenhum jogo encontrado na página {page}.")

            # Espera um tempo aleatório antes de ir para a próxima página
            if page < END_PAGE:
                sleep_time = random.uniform(MIN_DELAY, MAX_DELAY)
                print(f"    ⏳ Aguardando {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                
    finally:
        driver.quit()

    print("=" * 50)
    print(f"✅ Execução finalizada! Total de {total_games_collected} jogos salvos em: {os.path.abspath(OUTPUT_CSV)}")