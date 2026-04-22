from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import re
import unicodedata

app = FastAPI(title="Diagnóstico Auto RoxCoach")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def slugify(text: str) -> str:
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^a-z0-9\\s-]', '', text.lower().strip())
    text = re.sub(r'[\\s-]+', '-', text)
    return text.strip('-')

async def find_race_id(client: httpx.AsyncClient, event_slug: str, season: int = 8) -> int | None:
    url = f"https://api.rox-coach.com/api/v1/races?season={season}"
    resp = await client.get(url)
    if resp.status_code != 200:
        return None
    data = resp.json()
    races = data.get('races', [])
    for race in races:
        if slugify(race.get('name', '')) == event_slug:
            return race['id']
    return None

async def find_division_id(client: httpx.AsyncClient, race_id: int, division_slug: str) -> int | None:
    url = f"https://api.rox-coach.com/api/v1/races/{race_id}/divisions"
    resp = await client.get(url)
    if resp.status_code != 200:
        return None
    data = resp.json()
    divisions = data if isinstance(data, list) else data.get('divisions', [])
    for div in divisions:
        if slugify(div.get('name', '')) == division_slug:
            return div['id']
    return None

async def find_athlete_id(client: httpx.AsyncClient, race_id: int, division_id: int, athlete_slug: str) -> int | None:
    page = 1
    max_pages = 10
    while page <= max_pages:
        url = f"https://api.rox-coach.com/api/v1/races/{race_id}/division/{division_id}/results?page={page}"
        resp = await client.get(url)
        if resp.status_code != 200:
            break
        data = resp.json()
        results = data.get('results', []) if isinstance(data.get('results'), list) else data
        for result in results:
            athlete = result.get('athlete', {})
            if slugify(athlete.get('name', '')) == athlete_slug:
                return athlete.get('id')
        if len(results) == 0:
            break
        page += 1
    return None

@app.get("/diagnostico_auto")
async def diagnostico_auto(
    athlete_name: str = Query(..., description="Nome do atleta"),
    event_name: str = Query(..., description="Nome do evento"),
    division: str = Query(..., description="Divisão"),
    season: int = Query(8, description="Temporada (padrão 8)"),
):
    async with httpx.AsyncClient(timeout=60.0, limits=httpx.Limits(max_keepalive_connections=5)) as client:
        athlete_slug = slugify(athlete_name)
        event_slug = slugify(event_name)
        division_slug = slugify(division)

        race_id = await find_race_id(client, event_slug, season)
        if not race_id:
            raise HTTPException(status_code=404, detail="Evento não encontrado para o nome fornecido.")

        division_id = await find_division_id(client, race_id, division_slug)
        if not division_id:
            raise HTTPException(status_code=404, detail="Divisão não encontrada.")

        athlete_id = await find_athlete_id(client, race_id, division_id, athlete_slug)
        if not athlete_id:
            raise HTTPException(status_code=404, detail="Atleta não encontrado na divisão.")

        url = f"https://api.rox-coach.com/api/v1/results/athletes/{athlete_id}?event={race_id}&lang=EN_CAP"
        resp = await client.get(url)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Erro ao obter diagnóstico do RoxCoach.")

        data = resp.json()

        # Monta o diagnóstico estruturado (adapta chaves se necessário baseado na resposta real da API)
        return {
            "resumo_performance": data.get("performance_summary", data.get("resumo_performance", {})),
            "diagnostico_melhoria": data.get("improvements", data.get("diagnostico_melhoria", [])),
            "tempos_splits": data.get("splits", data.get("tempos_splits", [])),
            "texto_ia": data.get("analysis_text", data.get("texto_ia", data.get("ai_text", "Análise gerada pela IA do RoxCoach.")))
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
