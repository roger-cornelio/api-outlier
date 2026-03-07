from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests
import pandas as pd
import json
from io import StringIO
from bs4 import BeautifulSoup

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
        
        # 1. DIAGNÓSTICO DE MELHORIA (Desmembrando as colunas)
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
        if not df_splits.empty:
            for index, row in df_splits.iterrows():
                if pd.isna(row[0]) or str(row[0]).strip() in ["None", "nan", "", "Splits"]:
                    continue
                lista_splits.append({
                    "split_name": str(row[0]),
                    "time": str(row[1])
                })

        # 3. RESUMO DE PERFORMANCE (A mina de ouro do topo da página)
        soup = BeautifulSoup(response.text, 'html.parser')
        resumo = {
            "finish_time": "N/A",
            "posicao_categoria": "N/A",
            "posicao_geral": "N/A",
            "run_total": "N/A",
            "avg_lap": "N/A",
            "best_lap": "N/A",
            "workout_total": "N/A",
            "avg_workout": "N/A",
            "roxzone": "N/A"
        }
        
        textos_pagina = list(soup.stripped_strings)
        for i, texto in enumerate(textos_pagina):
            texto_limpo = texto.strip()
            
            if texto_limpo == "Run Total" and resumo["run_total"] == "N/A":
                resumo["run_total"] = textos_pagina[i-1]
            elif texto_limpo == "Avg. Lap" and resumo["avg_lap"] == "N/A":
                resumo["avg_lap"] = textos_pagina[i-1]
            elif texto_limpo == "Best Lap" and resumo["best_lap"] == "N/A":
                resumo["best_lap"] = textos_pagina[i-1]
            elif texto_limpo == "Workout Total" and resumo["workout_total"] == "N/A":
                resumo["workout_total"] = textos_pagina[i-1]
            elif texto_limpo == "Avg. Workout" and resumo["avg_workout"] == "N/A":
                resumo["avg_workout"] = textos_pagina[i-1]
            elif texto_limpo == "Roxzone" and resumo["roxzone"] == "N/A":
                resumo["roxzone"] = textos_pagina[i-1]
            elif "in AG" in texto_limpo and resumo["posicao_categoria"] == "N/A":
                resumo["posicao_categoria"] = texto_limpo
                resumo["finish_time"] = textos_pagina[i-1]
            elif "Top" in texto_limpo and "|" in texto_limpo and "AG" not in texto_limpo and resumo["posicao_geral"] == "N/A":
                resumo["posicao_geral"] = texto_limpo

        # 4. TEXTO DO TREINADOR IA
        diagnostico_partes = []
        capturando = False
        for t in soup.stripped_strings:
            if 'A word from RoxCoach' in t or 'Overall Performance:' in t:
                capturando = True
            if 'Similar Athletes' in t or 'Other Results' in t or 'Pace Calculator' in t:
                capturando = False
            if capturando:
                texto_limpo = t.strip()
                if len(texto_limpo) > 10: 
                    diagnostico_partes.append(texto_limpo)
                    
        texto_ia_final = "\n\n".join(diagnostico_partes)
        if not texto_ia_final:
            texto_ia_final = "Diagnóstico não encontrado."

        # EMPACOTANDO O JSON FINAL
        dados_atleta = {
            'resumo_performance': resumo,
            'diagnostico_melhoria': lista_improvement,
            'tempos_splits': lista_splits,
            'texto_ia': texto_ia_final
        }
        
        return dados_atleta

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")
