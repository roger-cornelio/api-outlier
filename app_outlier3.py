from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
import re
import unicodedata

app = FastAPI(title="API Outlier MVP - v9.4 Extended Timeout")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

def slugify(text: str) -> str:
    if not text: return ""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text)

@app.get("/diagnostico")
def gerar_diagnostico(request: Request):
    params = request.query_params
    
    hyrox_url = params.get('hyrox_url') or params.get('url') or params.get('resultado_url')
    athlete_name = params.get('athlete_name') or params.get('nome_do_atleta') or params.get('nome') or params.get('athleteName')
    event_name_raw = params.get('event_name') or params.get('evento') or params.get('nome_do_evento') or params.get('eventName')
    division = params.get('division') or params.get('divisao')
    
    if not all([hyrox_url, athlete_name, event_name_raw, division]):
        raise HTTPException(status_code=400, detail=f"Faltam parâmetros! Recebidos: {dict(params)}")

    # ==========================================
    # 🧹 SUPER CLEANER (Lidando com a sujeira do Lovable)
    # ==========================================
    # 1. Corta no bullet point (•) ou pipe (|)
    clean_event = re.split(r'[•|]', event_name_raw)[0].strip()
    # 2. Corta a palavra HYROX e o que vier depois
    clean_event = re.split(r'(?i)hyrox', clean_event)[0].strip()
    
    # 3. Quebra em palavras-chave fortes (Ex: "Mexico City" -> ['mexico', 'city'])
    event_words = [w for w in slugify(clean_event).split('-') if len(w) >= 3 and not w.isdigit()]

    print(f"Buscando Atleta: {athlete_name} | Evento: '{clean_event}' | Palavras-chave: {event_words}")

    # 🔥 SPEED BOOST: Usar Sessão para reaproveitar conexão
    session = requests.Session(impersonate="chrome")

    try:
        # Extrair Season e Sexo
        season_match = re.search(r'season-(\d+)', hyrox_url)
        season = season_match.group(1) if season_match else "8"
        
        sex_match = re.search(r'sex(?:%5D|\])=([MW])', hyrox_url)
        if sex_match:
            sex_str = "men" if sex_match.group(1) == "M" else "women"
        else:
            div_lower = division.lower()
            if "women" in div_lower or "fem" in div_lower: sex_str = "women"
            elif "mixed" in div_lower or "misto" in div_lower: sex_str = "mixed"
            else: sex_str = "men"
        
        # ==========================================
        # PASSO 1: ENCONTRAR O EVENTO
        # ==========================================
        races_list_url = f"https://www.rox-coach.com/seasons/{season}/races"
        # Aumentado para 30 segundos
        races_resp = session.get(races_list_url, timeout=30)
        
        soup_races = BeautifulSoup(races_resp.text, 'html.parser')
        race_href = None
        
        for a in soup_races.find_all('a', href=True):
            href = a['href']
            if '/races/' in href:
                # Match mais inteligente: se qualquer palavra-chave do evento bater na URL do site
                if event_words and any(w in href.lower() for w in event_words):
                    race_href = href
                    break
                
        if not race_href:
            raise ValueError(f"Evento contendo as palavras {event_words} não encontrado na Temporada {season}.")
            
        race_url = f"https://www.rox-coach.com{race_href}"
        
        # ==========================================
        # PASSO 2: ENCONTRAR A DIVISÃO EXATA
        # ==========================================
        # Aumentado para 30 segundos
        race_resp = session.get(race_url, timeout=30)
        soup_race = BeautifulSoup(race_resp.text, 'html.parser')

        # Limpa o nome da divisão para achar a slug exata (Ex: "HYROX DOUBLES PRO" -> "doubles-pro")
        div_norm = slugify(re.sub(r'(?i)hyrox|men|women|mixed|misto', '', division).strip())
        if not div_norm: div_norm = "open"

        division_href = None
        
        # Tentativa 1: Match Exato (Garante que "doubles" não seja confundido com "doubles-pro")
        for a in soup_race.find_all('a', href=True):
            href = a['href']
            if '/divisions/' in href:
                href_div = href.split('/')[-1].split('?')[0].lower()
                if href_div == div_norm or (div_norm == "open" and href_div in ["open", "individual"]):
                    division_href = href
                    break
                    
        # Tentativa 2: Fallback parcial se não achou exato
        if not division_href:
            for a in soup_race.find_all('a', href=True):
                href = a['href']
                if '/divisions/' in href and div_norm in href.lower():
                    division_href = href
                    break
                
        if not division_href:
            raise ValueError(f"Divisão '{division}' não encontrada no evento.")
            
        # ==========================================
        # PASSO 3: MODO RADAR OTIMIZADO
        # ==========================================
        leaderboard_url = f"https://www.rox-coach.com{division_href}"
        if "/results" not in leaderboard_url:
            leaderboard_url += "/results"
        leaderboard_url += f"?sex={sex_str}"
        
        search_parts = set([p for p in slugify(athlete_name).split('-') if len(p) > 2])
        athlete_href = None
        
        for page in range(1, 20): 
            page_url = f"{leaderboard_url}&page={page}"
            # Aumentado para 25 segundos por página
            lead_resp = session.get(page_url, timeout=25)
            
            # Auto-brake: Quebra o loop imediatamente se a página estiver vazia (evita Timeout)
            if "<tbody>" not in lead_resp.text and "<table" not in lead_resp.text:
                break
                
            lead_soup = BeautifulSoup(lead_resp.text, 'html.parser')
            
            for a in lead_soup.find_all('a', href=True):
                href = a['href']
                if '/results/' in href and '/divisions/' not in href:
                    link_text = a.get_text(strip=True)
                    link_parts = set([p for p in slugify(link_text).split('-') if len(p) > 2])
                    
                    intersection = search_parts.intersection(link_parts)
                    min_match = 2 if len(search_parts) >= 2 else 1
                    
                    if len(intersection) >= min_match:
                        athlete_href = href
                        break
            if athlete_href:
                break
                
        if not athlete_href:
            raise ValueError(f"Atleta '{athlete_name}' não encontrado na lista de classificação.")

        # ==========================================
        # PASSO 4: RASPAGEM DE DADOS DA PÁGINA FINAL
        # ==========================================
        target_url = f"https://www.rox-coach.com{athlete_href}"
        # Aumentado para 30 segundos
        response = session.get(target_url, timeout=30)

        tabelas = pd.read_html(StringIO(response.text))
        soup_final = BeautifulSoup(response.text, 'html.parser')
        
        # DIAGNÓSTICO DE MELHORIA
        df_improvement = tabelas[0] if len(tabelas) > 0 else pd.DataFrame()
        lista_improvement = []
        if not df_improvement.empty:
            cols = df_improvement.columns
            for index, row in df_improvement.iterrows():
                movement = str(row[cols[0]])
                imp_raw = str(row[cols[1]])
                if "(From " in imp_raw and " to " in imp_raw:
                    parts = imp_raw.split(" (From ")
                    improvement_value = parts[0].strip()
                    times = parts[1].replace(")", "").split(" to ")
                    your_score = times[0].strip() if len(times) > 0 else "0"
                    top_1 = times[1].strip() if len(times) > 1 else "0"
                else:
                    improvement_value = imp_raw
                    your_score = "0"
                    top_1 = "0"
                percentage = str(row[cols[2]]).replace("%", "").strip()
                lista_improvement.append({
                    "movement": movement, "your_score": your_score, "top_1": top_1,
                    "improvement_value": improvement_value, "percentage": percentage
                })
                
        # TEMPOS E SPLITS
        df_splits = tabelas[1] if len(tabelas) > 1 else pd.DataFrame()
        lista_splits = []
        finish_time = "N/A"
        if not df_splits.empty:
            for index, row in df_splits.iterrows():
                nome_estacao = str(row[0]).strip()
                if pd.isna(row[0]) or nome_estacao in ["None", "nan", "", "Splits"]: continue
                lista_splits.append({"split_name": nome_estacao, "time": str(row[1])})
                if nome_estacao.lower() == "roxzone":
                    finish_time = str(row[2]) if len(row) > 2 else str(row[1])

        # RESUMO DE PERFORMANCE
        texto_completo = soup_final.get_text(separator=" ", strip=True)
        resumo = {
            "nome_atleta": athlete_name, "temporada": season, "evento": event_name_raw, "divisao": division,
            "finish_time": finish_time, "posicao_categoria": "N/A", "posicao_geral": "N/A",
            "run_total": "N/A", "avg_lap": "N/A", "best_lap": "N/A", "workout_total": "N/A",
            "avg_workout": "N/A", "roxzone": "N/A"
        }
        
        match_ranks = re.search(r'(\d{2}:\d{2}:\d{2})\s+(.*?\s+in\s+AG\s+\|\s+Top\s+[\d.]+%)\s+(.*?\s+\|\s+Top\s+[\d.]+%)', texto_completo)
        if match_ranks:
            resumo["finish_time"] = match_ranks.group(1).strip() if resumo["finish_time"] == "N/A" else resumo["finish_time"]
            resumo["posicao_categoria"] = match_ranks.group(2).strip()
            resumo["posicao_geral"] = match_ranks.group(3).strip()
        
        textos_limpos = [t.strip() for t in soup_final.stripped_strings if t.strip()]
        for i, texto in enumerate(textos_limpos):
            if i > 0:
                if texto == "Run Total" and resumo["run_total"] == "N/A": resumo["run_total"] = textos_limpos[i-1]
                elif texto == "Avg. Lap" and resumo["avg_lap"] == "N/A": resumo["avg_lap"] = textos_limpos[i-1]
                elif texto == "Best Lap" and resumo["best_lap"] == "N/A": resumo["best_lap"] = textos_limpos[i-1]
                elif texto == "Workout Total" and resumo["workout_total"] == "N/A": resumo["workout_total"] = textos_limpos[i-1]
                elif texto == "Avg. Workout" and resumo["avg_workout"] == "N/A": resumo["avg_workout"] = textos_limpos[i-1]
                elif texto == "Roxzone" and resumo["roxzone"] == "N/A": resumo["roxzone"] = textos_limpos[i-1]

        # TEXTO DO TREINADOR IA
        diagnostico_partes = []
        capturando = False
        for t in soup_final.stripped_strings:
            if 'A word from RoxCoach' in t or 'Overall Performance:' in t: capturando = True
            if 'Similar Athletes' in t or 'Other Results' in t or 'Pace Calculator' in t: capturando = False
            if capturando:
                texto_limpo_ia = t.strip()
                if len(texto_limpo_ia) > 10: diagnostico_partes.append(texto_limpo_ia)
                    
        texto_ia_final = "\n\n".join(diagnostico_partes)
        if not texto_ia_final: texto_ia_final = "Diagnóstico não encontrado."

        return {
            'resumo_performance': resumo,
            'diagnostico_melhoria': lista_improvement,
            'tempos_splits': lista_splits,
            'texto_ia': texto_ia_final
        }

    except Exception as e:
        print(f"Erro na API: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")
