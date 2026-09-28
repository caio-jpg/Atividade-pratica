from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.db.mongodb import mongo_conn
from backend.db.sqlite import sqlite_conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Iniciando aplicação...")
    if mongo_conn.connect():
        mongo_conn.create_geospatial_index("spatial_data", "geometry")
        mongo_conn.create_geospatial_index("restaurantes", "address.location")
    sqlite_conn.connect()
    yield
    # Shutdown
    print("🛑 Encerrando aplicação...")
    mongo_conn.close()


app = FastAPI(
    title="Smart City Dashboard API",
    description="API para dashboard geoespacial de cidade inteligente (MongoDB + SQLite)",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
def root():
    return {"message": "Smart City Dashboard API", "docs": "/docs", "status": "running"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
