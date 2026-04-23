from fastapi import FastAPI
import httpx

app = FastAPI()

@app.get("/healthcheck")
async def healthcheck():
    return {"status": "ok"}

@app.get("/diagnostico_auto")
async def diagnostico_auto():
    base_url = "https://api.roxcoach.com"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    max_pages = 5
    async with httpx.AsyncClient() as client:
        # Resolve race_id via pagination
        race_id = None
        page = 1
        while race_id is None and page <= max_pages:
            resp = await client.get(
                f"{base_url}/races",
                params={"page": page, "limit": 10},
                headers=headers
            )
            if resp.status_code != 200:
                return {"error": "Failed to fetch races"}
            data = resp.json()
            races = data.get("races", data.get("data", []))
            if races:
                race_id = races[0]["id"]
            page += 1
        if race_id is None:
            return {"error": "No race found"}

        # Resolve division_id via pagination
        division_id = None
        page = 1
        while division_id is None and page <= max_pages:
            resp = await client.get(
                f"{base_url}/races/{race_id}/divisions",
                params={"page": page, "limit": 10},
                headers=headers
            )
            if resp.status_code != 200:
                return {"error": "Failed to fetch divisions"}
            data = resp.json()
            divisions = data.get("divisions", data.get("data", []))
            if divisions:
                division_id = divisions[0]["id"]
            page += 1
        if division_id is None:
            return {"error": "No division found"}

        # Resolve athlete_id via pagination
        athlete_id = None
        page = 1
        while athlete_id is None and page <= max_pages:
            resp = await client.get(
                f"{base_url}/divisions/{division_id}/athletes",
                params={"page": page, "limit": 10},
                headers=headers
            )
            if resp.status_code != 200:
                return {"error": "Failed to fetch athletes"}
            data = resp.json()
            athletes = data.get("athletes", data.get("data", []))
            if athletes:
                athlete_id = athletes[0]["id"]
            page += 1
        if athlete_id is None:
            return {"error": "No athlete found"}

        # Call final endpoint
        final_resp = await client.get(
            f"{base_url}/diagnostico_auto/{race_id}/{division_id}/{athlete_id}",
            headers=headers
        )
        if final_resp.status_code != 200:
            return {"error": f"Final endpoint failed: {final_resp.status_code}"}
        return final_resp.json()
