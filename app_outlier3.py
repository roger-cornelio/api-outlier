from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests
import pandas as pd
import json
from io import StringIO
from bs4 import BeautifulSoup
import re

app = FastAPI(title="API Outlier MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

@app.get("/diagnostico")
def gerar_diagnostico(url: str):
    print(f"Buscando dados de: {url}")
    try:
        response = requests.get(url, impersonate="chrome")
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao acessar o site.")
            
        tabelas = pd.read_html(StringIO(response.text))
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # --- EXTRAÇÃO DE NOME, TEMPORADA E EVENTO (NOVO) ---
        nome_atleta = "N/A"
        evento = "N/A"
        divisao = "N/A"
        temporada = "N/A"
        
        # O titulo da pagina é sempre: "Roger Cornélio Hyrox result for 2025 Rio de Janeiro - Hyrox Pro Men S8"
        title_text = soup.title.string if soup.title else ""
        if " Hyrox result for " in title_text:
            partes = title_text.split(" Hyrox result for ")
            nome_atleta = partes[0].strip()
            infos_evento = partes[1].split(" - ")
            if len(infos_evento) > 0:
                evento = infos_evento[0].strip()
            if len(infos_evento) > 1:
                div_temp = infos_evento[1].strip()
                match_temp = re.search(r'(S\d+|Season \d+)$', div_temp)
                if match_temp:
                    temporada = match_temp.group(1)
                    divisao = div_temp.replace(temporada, "").strip()
                else:
                    divisao = div_temp
        
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
                
        # 2. TEMPOS E SPLITS (Capturando o Finish Time)
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
                    # Coluna 2 é o tempo acumulado exato final
                    finish_time = str(row[2])

        # 3. RESUMO DE PERFORMANCE (Capturando métricas ocultas)
        texto_completo = soup.get_text(separator=" ", strip=True)
        
        resumo = {
            "nome_atleta": nome_atleta,
            "temporada": temporada,
            "evento": evento,
            "divisao": divisao,
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
        
        # Regex caçador para achar os ranks (Ex: "01:19:57 21st in AG | Top 40.4% 78th | Top 41.5%")
        match_ranks = re.search(r'(\d{2}:\d{2}:\d{2})\s+(\d+(?:st|nd|rd|th)\s+in\s+AG\s+\|\s+Top\s+[\d.]+%)\s+(\d+(?:st|nd|rd|th)\s+\|\s+Top\s+[\d.]+%)', texto_completo)
        if match_ranks:
            if resumo["finish_time"] == "N/A":
                resumo["finish_time"] = match_ranks.group(1)
            resumo["posicao_categoria"] = match_ranks.group(2)
            resumo["posicao_geral"] = match_ranks.group(3)
        
        textos_limpos = [t.strip() for t in soup.stripped_strings if t.strip()]
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
        for t in soup.stripped_strings:
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
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")
# Forçando o Render a atualizar

