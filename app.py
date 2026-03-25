from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def read_display(request: Request):
    # This is where your data fetching logic will eventually live
    context = {
        "time": datetime.now(tz=UTC).astimezone().strftime("%H:%M"),
        "date": datetime.now(tz=UTC).astimezone().strftime("%A, %b %d"),
        "status": "System Online",
    }
    return templates.TemplateResponse(request, "display.html", context)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
