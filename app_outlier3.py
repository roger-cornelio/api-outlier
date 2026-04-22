import os
import uvicorn
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="RoxCoach Diagnóstico API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*'],
)

@app.get("/diagnostico")
async def get_diagnostico(
    athlete_id: str = Query(..., description="ID do atleta"),
    event_id: str = Query(..., description="ID do evento")
):
    url = f"https://roxcoach.com.br/api/athletes/{athlete_id}/events/{event_id}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return {
            "resumo_performance": {
                "finishTime": "",
                "ranking": "",
                "genderRanking": "",
                "worldRanking": ""
            },
            "diagnostico_melhoria": [],
            "tempos_splits": [],
            "texto_ia": ""
        }

    resumo_performance = {
        "finishTime": data.get("finishTime") or "",
        "ranking": str(data.get("ranking") or ""),
        "genderRanking": str(data.get("genderRanking") or ""),
        "worldRanking": str(data.get("worldRanking") or "")
    }

    diagnostico_melhoria = data.get("performanceTable", [])
    tempos_splits = data.get("splits", [])
    texto_ia = str(data.get("insights") or "")

    return {
        "resumo_performance": resumo_performance,
        "diagnostico_melhoria": diagnostico_melhoria,
        "tempos_splits": tempos_splits,
        "texto_ia": texto_ia
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
