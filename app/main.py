from fastapi import FastAPI

app = FastAPI(title="Carpool Queue")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Carpool queue service is running"}
