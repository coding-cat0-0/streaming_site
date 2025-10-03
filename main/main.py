from fastapi import FastAPI
from routers import admin, creator, login, user
from sqlmodel import SQLModel
from database.structure import engine
import uvicorn

app = FastAPI()

app.include_router(login.router)
app.include_router(user.router)
app.include_router(creator.router)
app.include_router(admin.router)

@app.on_event("startup") 
def on_startup() -> None:
    SQLModel.metadata.create_all(engine) 