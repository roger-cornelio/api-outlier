from fastapi import FastAPI, Query, HTTPException
from typing import Dict, Any, List
import httpx
import os
import uvicorn

app = FastAPI(title="Diagnostico Auto RoxCoach")

ROXCOACH_BASE_URL = os.getenv("ROXCOACH_BASE_URL", "https://app.roxcoach.com.br/api")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://roxcoach.com.br/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

async def fetch_json(client: httpx.AsyncClient, url: str, params: Dict[str, Any] | None = None) -> Dict[str, Any] | List[Dict[str, Any]]:
    response = await client.get(url, params=params)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=f"Erro na API RoxCoach: {response.text[:200]}")
    return response.json()

@app.get("/diagnostico_auto")
async def diagnostico_auto(
    nome: str = Query(..., description="Nome do atleta"),
    evento: str = Query(..., description="Nome ou termo de busca do evento"),
    divisao: str = Query(..., description="Nome ou termo da divisão"),
):
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0),
        headers=HEADERS,
        limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
    ) as client:
        # 2. Resolve race_id via API RoxCoach
        races_url = f"{ROXCOACH_BASE_URL}/races/search"
        params = {"q": evento}
        races_data = await fetch_json(client, races_url, params)
        races = races_data if isinstance(races_data, list) else races_data.get("races", races_data.get("data", []))
        if not races:
            raise HTTPException(404, "Evento não encontrado")
        race_id = races[0]["id"]

        # 3. Resolve division_id
        divs_url = f"{ROXCOACH_BASE_URL}/races/{race_id}/divisions"
        divs_data = await fetch_json(client, divs_url)
        divs = divs_data if isinstance(divs_data, list) else divs_data.get("divisions", divs_data.get("data", []))
        division_id = None
        divisao_lower = divisao.lower()
        for div in divs:
            if divisao_lower in div.get("name", "").lower():
                division_id = div["id"]
                break
        if not division_id:
            raise HTTPException(404, "Divisão não encontrada")

        # 4. Resolve athlete_id via paginação
        athlete_id = None
        page = 1
        limit = 100
        max_pages = 20
        nome_lower = nome.lower()
        while page <= max_pages:
            athletes_url = f"{ROXCOACH_BASE_URL}/races/{race_id}/divisions/{division_id}/athletes"
            params = {"page": page, "limit": limit}
            athletes_data = await fetch_json(client, athletes_url, params)
            athletes = athletes_data if isinstance(athletes_data, list) else athletes_data.get("athletes", athletes_data.get("data", []))
            for athlete in athletes:
                if nome_lower in athlete.get("name", "").lower():
                    athlete_id = athlete["id"]
                    break
            if athlete_id:
                break
            if len(athletes) < limit:
                break
            page += 1
        if not athlete_id:
            raise HTTPException(404, "Atleta não encontrado")

        # 5. Chama endpoint final de resultados
        results_url = f"{ROXCOACH_BASE_URL}/races/{race_id}/divisions/{division_id}/athletes/{athlete_id}/results"
        results_data = await fetch_json(client, results_url)

        # 6. Retorna performanceTable bruta
        performance_table = results_data.get("performanceTable")
        if performance_table is None:
            raise HTTPException(404, "performanceTable não encontrada nos resultados")

        return performance_table

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
