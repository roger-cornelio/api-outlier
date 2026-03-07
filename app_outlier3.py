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
            
        # 1. PEGAR AS TABELAS
        tabelas = pd.read_html(StringIO(response.text))
        df_improvement = tabelas[0] if len(tabelas) > 0 else pd.DataFrame()
        df_splits = tabelas[1] if len(tabelas) > 1 else pd.DataFrame()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. PEGAR O TEXTO DO DIAGNÓSTICO
        diagnostico_partes = []
        capturando = False
        
        for t in soup.stripped_strings:
            if 'A word from RoxCoach' in t or 'Overall Performance:' in t:
                capturando = True
            if 'Similar Athletes' in t or 'Other Results' in t or 'Pace Calculator' in t:
                capturando = False
            if capturando:
                texto = t.strip()
                if len(texto) > 10: 
                    diagnostico_partes.append(texto)
                    
        texto_ia_final = "\n\n".join(diagnostico_partes)
        if not texto_ia_final:
            texto_ia_final = "Diagnóstico não encontrado."

        # 3. PEGAR O RESUMO DE PERFORMANCE (A MINA DE OURO DO TOPO)
        resumo = {
            "posicao_categoria": "",
            "posicao_geral": "",
            "run_total": "",
            "workout_total": ""
        }
        
        textos_pagina = list(soup.stripped_strings)
        for i, texto in enumerate(textos_pagina):
            if texto == "Run Total":
                resumo["run_total"] = textos_pagina[i-1]
            elif texto == "Workout Total":
                resumo["workout_total"] = textos_pagina[i-1]
            elif "in AG" in texto:
                resumo["posicao_categoria"] = texto
            elif "Top" in texto and "|" in texto and "AG" not in texto:
                resumo["posicao_geral"] = texto

        # 4. EMPACOTAR TUDO
        dados_atleta = {
            'resumo_performance': resumo, # NOVA CHAVE COM OS DESTAQUES!
            'diagnostico_melhoria': json.loads(df_improvement.to_json(orient='records')) if not df_improvement.empty else [],
            'tempos_splits': json.loads(df_splits.to_json(orient='records')) if not df_splits.empty else [],
            'texto_ia': texto_ia_final
        }
        
        return dados_atleta

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")


