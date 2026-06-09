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
import random

# ---------------------------------------------------------------------------
# CONFIGURAÇÕES — edite aqui
# ---------------------------------------------------------------------------
START_PAGE          = 1
END_PAGE            = 3
OUTPUT_CSV          = "bgg_ranking.csv"
MIN_DELAY           = 4.0    # Tempo mínimo de espera entre páginas de listagem
MAX_DELAY           = 7.5    # Tempo máximo de espera entre páginas de listagem
DETAIL_MIN_DELAY    = 2.0    # Tempo mínimo entre requisições de detalhe (/credits)
DETAIL_MAX_DELAY    = 4.5    # Tempo máximo entre requisições de detalhe (/credits)
# ---------------------------------------------------------------------------

BASE_URL    = "https://boardgamegeek.com/browse/boardgame"
BGG_ROOT    = "https://boardgamegeek.com"


def build_driver() -> webdriver.Chrome:
    """Cria o Chrome com configurações mínimas para estabilidade."""
    print("Iniciando o navegador...")
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)
    return driver


def get_page_html(driver: webdriver.Chrome, page_num: int) -> str | None:
    """Navega até a página de listagem e retorna o HTML após o carregamento da tabela."""
    url = BASE_URL if page_num == 1 else f"{BASE_URL}/page/{page_num}"
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "collectionitems"))
        )
        return driver.page_source
    except Exception as e:
        print(f"  [ERRO] Página {page_num}: {e}", file=sys.stderr)
        return None


def get_credits_details(driver: webdriver.Chrome, game_path: str) -> dict:
    """
    Acessa a página /credits de um jogo e extrai:
    - num_players   (ex: "2–4")
    - play_time     (ex: "60–120")
    - suggested_age (ex: "14+")
    - complexity    (ex: "3.86 / 5")

    O HTML da página /credits é gerado por AngularJS, por isso usamos Selenium
    para aguardar o conteúdo renderizado antes de parsear.
    """
    details = {
        "num_players":   "",
        "play_time":     "",
        "suggested_age": "",
        "complexity":    "",
    }

    url = f"{BGG_ROOT}{game_path}/credits"
    try:
        driver.get(url)

        # Aguarda o painel de gameplay aparecer (renderizado pelo AngularJS)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gameplay"))
        )

        soup = BeautifulSoup(driver.page_source, "lxml")
        gameplay = soup.select_one("ul.gameplay")
        if not gameplay:
            return details

        items = gameplay.select("li.gameplay-item")

        # ------------------------------------------------------------------ #
        # Item 0 — Number of Players
        # ------------------------------------------------------------------ #
        if len(items) > 0:
            item = items[0]
            primary = item.select_one("p.gameplay-item-primary")
            if primary:
                # Os spans ng-binding dentro do primary trazem os números (min e max)
                spans = primary.find_all("span", class_="ng-binding")
                # O span que contém itemprop="minValue" / "maxValue" fica dentro
                # de um <meta>; o texto visível vem de spans ng-binding
                numbers = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
                # Filtra o "–" (separador) e une: ["2", "–", "4"] → "2–4"
                details["num_players"] = "".join(numbers)

        # ------------------------------------------------------------------ #
        # Item 1 — Play Time
        # ------------------------------------------------------------------ #
        if len(items) > 1:
            item = items[1]
            primary = item.select_one("p.gameplay-item-primary")
            if primary:
                spans = primary.find_all("span", class_="ng-binding")
                numbers = [s.get_text(strip=True) for s in spans if s.get_text(strip=True)]
                details["play_time"] = "".join(numbers)   # ex: "60–120"

        # ------------------------------------------------------------------ #
        # Item 2 — Suggested Age
        # ------------------------------------------------------------------ #
        if len(items) > 2:
            item = items[2]
            primary = item.select_one("p.gameplay-item-primary")
            if primary:
                age_span = primary.select_one("span[itemprop='suggestedMinAge']")
                if age_span:
                    details["suggested_age"] = age_span.get_text(strip=True) + "+"

        # ------------------------------------------------------------------ #
        # Item 3 — Complexity (Weight)
        # ------------------------------------------------------------------ #
        if len(items) > 3:
            item = items[3]
            primary = item.select_one("p.gameplay-item-primary")
            if primary:
                weight_span = primary.select_one(
                    "span.ng-binding[class*='gameplay-weight']"
                )
                if weight_span:
                    details["complexity"] = weight_span.get_text(strip=True) + " / 5"

    except Exception as e:
        print(f"    [AVISO] Falha ao obter detalhes de {game_path}: {e}", file=sys.stderr)

    return details


def parse_page(html: str) -> list[dict]:
    """Extrai os dados básicos dos jogos do HTML da página de listagem."""
    soup = BeautifulSoup(html, "lxml")
    games = []

    for row in soup.select("tr[id='row_']"):
        game = {}

        # Rank
        rank_td = row.select_one("td.collection_rank")
        if not rank_td:
            continue
        game["rank"] = rank_td.get_text(strip=True)

        # Título, ano e link
        name_div = row.select_one("div[id^='results_objectname']")
        if name_div:
            title_a = name_div.select_one("a.primary")
            game["title"]      = title_a.get_text(strip=True) if title_a else ""
            game["game_path"]  = title_a["href"] if title_a else ""   # ex: /boardgame/224517/brass-birmingham
            year_span = name_div.select_one("span.smallerfont.dull")
            game["year"] = year_span.get_text(strip=True).strip("()") if year_span else ""
        else:
            game["title"] = game["year"] = game["game_path"] = ""

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

        # Campos de detalhe (serão preenchidos depois)
        game["num_players"]   = ""
        game["play_time"]     = ""
        game["suggested_age"] = ""
        game["complexity"]    = ""

        games.append(game)

    return games


def append_to_csv(games: list[dict], path: str) -> None:
    """Adiciona os jogos ao CSV. Cria o cabeçalho se o arquivo não existir."""
    fields = [
        "rank", "title", "year", "description",
        "geek_rating", "avg_rating", "num_voters", "price",
        "num_players", "play_time", "suggested_age", "complexity",
    ]
    file_exists = os.path.isfile(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
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

            if not games:
                print(f"    → Nenhum jogo encontrado na página {page}.")
            else:
                # Enriquece cada jogo com os detalhes da página /credits
                for i, game in enumerate(games, start=1):
                    if game["game_path"]:
                        print(f"    [{i}/{len(games)}] Detalhes: {game['title']}…")
                        details = get_credits_details(driver, game["game_path"])
                        game.update(details)

                        # Delay gentil entre cada chamada de detalhe
                        sleep_time = random.uniform(DETAIL_MIN_DELAY, DETAIL_MAX_DELAY)
                        time.sleep(sleep_time)

                append_to_csv(games, OUTPUT_CSV)
                total_games_collected += len(games)
                print(f"    → {len(games)} jogos salvos. (Total: {total_games_collected})")

            # Delay entre páginas de listagem
            if page < END_PAGE:
                sleep_time = random.uniform(MIN_DELAY, MAX_DELAY)
                print(f"    ⏳ Aguardando {sleep_time:.2f}s antes da próxima página…")
                time.sleep(sleep_time)

    finally:
        driver.quit()

    print("=" * 50)
    print(f"✅ Concluído! {total_games_collected} jogos salvos em: {os.path.abspath(OUTPUT_CSV)}")