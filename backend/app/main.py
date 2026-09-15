from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ingestion, mastery, quiz, retrieval, topics, tutor

app = FastAPI(title="EduPilot AI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topics.router)
app.include_router(ingestion.router)
app.include_router(mastery.router)
app.include_router(quiz.router)
app.include_router(tutor.router)
app.include_router(retrieval.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "EduPilot AI backend"}


@app.get("/health")
def health():
    return {"status": "healthy"}
