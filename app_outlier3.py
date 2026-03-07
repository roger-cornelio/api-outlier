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
            
        # 1. PEGAR TODAS AS TABELAS
        tabelas = pd.read_html(StringIO(response.text))
        
        # Agora estamos pegando as TRÊS tabelas com segurança
        df_improvement = tabelas[0] if len(tabelas) > 0 else pd.DataFrame()
        df_station_splits = tabelas[1] if len(tabelas) > 1 else pd.DataFrame()
        df_running_splits = tabelas[2] if len(tabelas) > 2 else pd.DataFrame() # A TABELA QUE FALTAVA!
        
        # 2. PEGAR O TEXTO DO DIAGNÓSTICO
        soup = BeautifulSoup(response.text, 'html.parser')
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
            texto_ia_final = "Diagnóstico não encontrado para este atleta."

        # 3. EMPACOTAR TUDO (Adicionamos a nova chave 'running_splits')
        dados_atleta = {
            'diagnostico_melhoria': json.loads(df_improvement.to_json(orient='records')) if not df_improvement.empty else [],
            'tempos_splits': json.loads(df_station_splits.to_json(orient='records')) if not df_station_splits.empty else [],
            'running_splits': json.loads(df_running_splits.to_json(orient='records')) if not df_running_splits.empty else [],
            'texto_ia': texto_ia_final
        }
        
        return dados_atleta

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")

