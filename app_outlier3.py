from fastapi import FastAPI, HTTPException
from curl_cffi import requests
import pandas as pd
import json
from io import StringIO

# Cria a nossa API (esta é a palavra "app" que o servidor estava procurando!)
app = FastAPI(title="API Outlier MVP")

@app.get("/diagnostico")
def gerar_diagnostico(url: str):
    print(f"Buscando dados de: {url}")
    try:
        response = requests.get(url, impersonate="chrome")
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Erro ao acessar o site.")
            
        tabelas = pd.read_html(StringIO(response.text))
        
        df_improvement = tabelas[0] 
        df_splits = tabelas[1]      
        
        dados_atleta = {
            'diagnostico_melhoria': json.loads(df_improvement.to_json(orient='records')),
            'tempos_splits': json.loads(df_splits.to_json(orient='records'))
        }
        
        return dados_atleta

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")