from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from curl_cffi import requests
import pandas as pd
import json
from io import StringIO
from bs4 import BeautifulSoup  # NOVA FERRAMENTA IMPORTADA AQUI

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
            
        # 1. PEGAR AS TABELAS (O que já funcionava)
        tabelas = pd.read_html(StringIO(response.text))
        df_improvement = tabelas[0] 
        df_splits = tabelas[1]      
        
        # 2. PEGAR O TEXTO DO DIAGNÓSTICO DA IA (A Mágica Nova)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        diagnostico_partes = []
        capturando = False
        
        # O BeautifulSoup vai ler todos os textos da página de cima a baixo
        for t in soup.stripped_strings:
            # Começa a "gravar" quando achar o título do RoxCoach
            if 'A word from RoxCoach' in t or 'Overall Performance:' in t:
                capturando = True
                
            # Para de "gravar" quando chegar na parte de atletas similares (final da página)
            if 'Similar Athletes' in t or 'Other Results' in t or 'Pace Calculator' in t:
                capturando = False
                
            if capturando:
                texto = t.strip()
                # Salva os parágrafos e títulos ignorando lixos curtos
                if len(texto) > 10: 
                    diagnostico_partes.append(texto)
                    
        # Junta todos os parágrafos capturados com uma quebra de linha dupla
        texto_ia_final = "\n\n".join(diagnostico_partes)
        
        if not texto_ia_final:
            texto_ia_final = "Diagnóstico não encontrado para este atleta."

        # 3. EMPACOTAR E DEVOLVER TUDO
        dados_atleta = {
            'diagnostico_melhoria': json.loads(df_improvement.to_json(orient='records')),
            'tempos_splits': json.loads(df_splits.to_json(orient='records')),
            'texto_ia': texto_ia_final  # NOVA CHAVE ADICIONADA AO JSON
        }
        
        return dados_atleta

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao extrair: {str(e)}")
