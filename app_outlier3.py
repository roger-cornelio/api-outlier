from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests  # Mantido seu bypass anti-robô!
import pandas as pd
from io import StringIO
from bs4 import BeautifulSoup
import re

app = FastAPI(title="API Outlier MVP - Hunter Mode")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

def slugify(text: str) -> str:
    return text.lower().replace(' ', '-')

@app.get("/diagnostico")
def gerar_diagnostico(request: Request):
    params = request.query_params
    
    # ==========================================
    # 🛡️ BLINDAGEM DE PARÂMETROS (Resolve o Erro 400 do Lovable)
    # ==========================================
    hyrox_url = params.get('hyrox_url') or params.get('url') or params.get('resultado_url')
    athlete_name = params.get('athlete_name') or params.get('nome_do_atleta') or params.get('nome') or params.get('athleteName')
    event_name = params.get('event_name') or params.get('evento') or params.get('nome_do_evento') or params.get('eventName')
    division = params.get('division') or params.get('divisao')
    
    if not all([hyrox_url, athlete_name, event_name, division]):
        raise HTTPException(status_code=400, detail=f"Faltam parâmetros! Recebidos do Lovable: {dict(params)}")

    print(f"Iniciando busca para: {athlete_name} | Evento: {event_name}")
    try:
        # ==========================================
        # PARTE 1: MODO CAÇADOR (Encontrar a URL exata)
        # ==========================================
        
        # 1. Extrair Season e Sexo da URL original da Hyrox
        season_match = re.search(r'season-(\d+)', hyrox_url)
        season = season_match.group(1) if season_match else "8"
        
        sex_match = re.search(r'sex(?:%5D|\])=([MW])', hyrox_url)
        sex_char = sex_match.group(1) if sex_match else "M"
        sex_str = "men" if sex_char == "M" else "women"
        
        # 2. Acessar a página do Evento no RoxCoach
        event_slug = slugify(event_name)
        race_url = f"https://www.rox-coach.com/seasons/{season}/races/{event_slug}"
        
        race_resp = requests.get(race_url, impersonate="chrome")
        if race_resp.status_code != 200:
            raise ValueError(f"Evento não encontrado no RoxCoach: {race_url}")
            
        soup = BeautifulSoup(race_resp.text, 'html.parser')
        
        # 3. Encontrar a URL da Divisão (com o hash aleatório ex: b9h)
        div_norm = division.lower().replace('hyrox ', '').split()[0]
        division_href = None
        for a in soup.find_all('a', href=True):
            href = a['href']
            if '/divisions/' in href and div_norm in href.lower():
                division_href = href
                break
                
        if not division_href:
            raise ValueError(f"Divisão '{division}' não encontrada.")
            
        # 4. Acessar o Leaderboard e procurar o atleta
        leaderboard_url = f"https://www.rox-coach.com{division_href}"
        if "/results" not in leaderboard_url:
            leaderboard_url += "/results"
        leaderboard_url += f"?sex={sex_str}"
        
        lead_resp = requests.get(leaderboard_url, impersonate="chrome")
        lead_soup = BeautifulSoup(lead_resp.text, 'html.parser')
        
        search_parts = set(athlete_name.lower().split())
        athlete_href = None
        
        for a in lead_soup.find_all('a', href=True):
            if '/results/' in a['href']:
                name_parts = set(a.text.strip().lower().split())
                if len(search_parts.intersection(name_parts)) >= 2:
                    athlete_href = a['href']
                    break
                    
        if not athlete_href:
            raise ValueError(f"Atleta '{athlete_name}' não encontrado no ranking.")
            
        target_url = f"https://www.rox-coach.com{athlete_href}"
        print(f"🎯 URL Alvo Encontrada: {target_url}")

        # ==========================================
        # PARTE 2: A SUA LÓGICA DE EXTRAÇÃO E PARSING
        # ==========================================
        
        response = requests.get(target_url, impersonate="chrome")
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao acessar a página do atleta.")
            
        tabelas = pd.read_html(StringIO(response.text))
        soup_final = BeautifulSoup(response.text, 'html.parser')
        
        # 1. DIAGNÓSTICO DE MELHORIA (Sua lógica perfeita)
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
                
        # 2. TEMPOS E SPLITS (Sua correção do Roxzone)
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
        # Forçando o Render a atualizar
