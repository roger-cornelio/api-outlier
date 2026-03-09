from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
import re
import unicodedata

app = FastAPI(title="API Outlier MVP - Sniper Mode v6")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

def slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = text.lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    return re.sub(r'[\s-]+', '-', text)

@app.get("/diagnostico")
def gerar_diagnostico(request: Request):
    params = request.query_params
    
    hyrox_url = params.get('hyrox_url') or params.get('url') or params.get('resultado_url')
    athlete_name = params.get('athlete_name') or params.get('nome_do_atleta') or params.get('nome') or params.get('athleteName')
    event_name = params.get('event_name') or params.get('evento') or params.get('nome_do_evento') or params.get('eventName')
    division = params.get('division') or params.get('divisao')
    
    if not all([hyrox_url, athlete_name, event_name, division]):
        raise HTTPException(status_code=400, detail=f"Faltam parâmetros! Recebidos: {dict(params)}")

    print(f"Iniciando busca para: {athlete_name} | Evento: {event_name}")
    try:
        # 1. Extrair Season
        season_match = re.search(r'season-(\d+)', hyrox_url)
        season = season_match.group(1) if season_match else "8"
        
        # 2. Acessar a página do Evento
        event_slug = slugify(event_name)
        race_url = f"https://www.rox-coach.com/seasons/{season}/races/{event_slug}"
        
        race_resp = requests.get(race_url, impersonate="chrome", timeout=30)
        
        # PLANO B PARA O EVENTO: Tenta sem o ano no início
        if race_resp.status_code != 200:
            event_slug_no_year = re.sub(r'^\d{4}-', '', event_slug)
            race_url_2 = f"https://www.rox-coach.com/seasons/{season}/races/{event_slug_no_year}"
            print(f"Tentando URL de Evento alternativa: {race_url_2}")
            race_resp = requests.get(race_url_2, impersonate="chrome", timeout=30)
            if race_resp.status_code == 200:
                race_url = race_url_2
                
        if race_resp.status_code != 200:
            raise ValueError(f"Evento não encontrado no RoxCoach. Tentamos: {race_url}")
            
        base_race_url = race_url 
        
        # 3. MODO SNIPER (Brute-force inteligente de URL)
        # O RoxCoach removeu as /divisions/ da URL e adicionou sufixos como -1, -2
        athlete_slug = slugify(athlete_name)
        slugs_to_try = [athlete_slug]
        
        nome_partes = athlete_name.split()
        if len(nome_partes) > 2:
            nome_curto = f"{nome_partes[0]} {nome_partes[-1]}"
            slugs_to_try.append(slugify(nome_curto))

        # Tenta a URL sem sufixo, e depois de -1 até -10
        suffixes = [""] + [f"-{i}" for i in range(1, 11)]
        
        target_url = None
        response = None
        
        print("Iniciando Modo Sniper (Testando sufixos)...")
        for slug in slugs_to_try:
            for suffix in suffixes:
                test_url = f"{base_race_url}/results/{slug}{suffix}"
                # Timeout super rápido de 10s: se não tiver o atleta ele ignora o 404 e pula pro próximo na hora
                resp = requests.get(test_url, impersonate="chrome", timeout=10) 
                
                if resp.status_code == 200 and "<table" in resp.text.lower():
                    print(f"✅ ATLETA ENCONTRADO! URL: {test_url}")
                    target_url = test_url
                    response = resp
                    break
            if response:
                break
                
        if not response:
            raise ValueError(f"Atleta '{athlete_name}' não encontrado. O RoxCoach pode ainda não ter processado este resultado ou o nome está diferente.")

        # ==========================================
        # PARTE 2: A LÓGICA DE EXTRAÇÃO DE DADOS
        # ==========================================
        tabelas = pd.read_html(StringIO(response.text))
        soup_final = BeautifulSoup(response.text, 'html.parser')
        
        # 1. DIAGNÓSTICO DE MELHORIA
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
                    "movement": movement,
                    "your_score": your_score,
                    "top_1": top_1,
                    "improvement_value": improvement_value,
                    "percentage": percentage
                })
                
        # 2. TEMPOS E SPLITS
        df_splits = tabelas[1] if len(tabelas) > 1 else pd.DataFrame()
        lista_splits = []
        finish_time = "N/A"
        
        if not df_splits.empty:
            for index, row in df_splits.iterrows():
                nome_estacao = str(row[0]).strip()
                if pd.isna(row[0]) or nome_estacao in ["None", "nan", "", "Splits"]:
                    continue
                lista_splits.append({
                    "split_name": nome_estacao,
                    "time": str(row[1])
                })
                if nome_estacao.lower() == "roxzone":
                    if len(row) > 2:
                        finish_time = str(row[2])
                    else:
                        finish_time = str(row[1])

        # 3. RESUMO DE PERFORMANCE
        texto_completo = soup_final.get_text(separator=" ", strip=True)
        
        resumo = {
            "nome_atleta": athlete_name,
            "temporada": season,
            "evento": event_name,
            "divisao": division,
            "finish_time": finish_time,
            "posicao_categoria": "N/A",
            "posicao_geral": "N/A",
            "run_total": "N/A",
            "avg_lap": "N/A",
            "best_lap": "N/A",
            "workout_total": "N/A",
            "avg_workout": "N/A",
            "roxzone": "N/A"
        }
        
        match_ranks = re.search(r'(\d{2}:\d{2}:\d{2})\s+(\d+(?:st|nd|rd|th)\s+in\s+AG\s+\|\s+Top\s+[\d.]+%)\s+(\d+(?:st|nd|rd|th)\s+\|\s+Top\s+[\d.]+%)', texto_completo)
        if match_ranks:
            if resumo["finish_time"] == "N/A":
                resumo["finish_time"] = match_ranks.group(1)
            resumo["posicao_categoria"] = match_ranks.group(2)
            resumo["posicao_geral"] = match_ranks.group(3)
        
        textos_limpos = [t.strip() for t in soup_final.stripped_strings if t.strip()]
        for i, texto in enumerate(textos_limpos):
            if i > 0:
                if texto == "Run Total" and resumo["run_total"] == "N/A":
                    resumo["run_total"] = textos_limpos[i-1]
                elif texto == "Avg. Lap" and resumo["avg_lap"] == "N/A":
                    resumo["avg_lap"] = textos_limpos[i-1]
                elif texto == "Best Lap" and resumo["best_lap"] == "N/A":
                    resumo["best_lap"] = textos_limpos[i-1]
                elif texto == "Workout Total" and resumo["workout_total"] == "N/A":
                    resumo["workout_total"] = textos_limpos[i-1]
                elif texto == "Avg. Workout" and resumo["avg_workout"] == "N/A":
                    resumo["avg_workout"] = textos_limpos[i-1]
                elif texto == "Roxzone" and resumo["roxzone"] == "N/A":
                    resumo["roxzone"] = textos_limpos[i-1]

        # 4. TEXTO DO TREINADOR IA
        diagnostico_partes = []
        capturando = False
        for t in soup_final.stripped_strings:
            if 'A word from RoxCoach' in t or 'Overall Performance:' in t:
                capturando = True
            if 'Similar Athletes' in t or 'Other Results' in t or 'Pace Calculator' in t:
                capturando = False
            if capturando:
                texto_limpo_ia = t.strip()
                if len(texto_limpo_ia) > 10: 
                    diagnostico_partes.append(texto_limpo_ia)
                    
        texto_ia_final = "\n\n".join(diagnostico_partes)
        if not texto_ia_final:
            texto_ia_final = "Diagnóstico não encontrado."

        # EMPACOTANDO TUDO
        dados_atleta = {
            'resumo_performance': resumo,
            'diagnostico_melhoria': lista_improvement,
            'tempos_splits': lista_splits,
            'texto_ia': texto_ia_final
        }
        
        return dados_atleta

    except Exception as e:
        print(f"Erro na API: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")
