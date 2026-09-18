from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, ingestion, mastery, quiz, retrieval, topics, tutor

app = FastAPI(title="Nucera", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # 3002 covers local dev when 3000 is already taken by another project
    # on the same machine (Next.js auto-picks the next free port).
    allow_origins=["http://localhost:3000", "http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(topics.router)
app.include_router(ingestion.router)
app.include_router(mastery.router)
app.include_router(quiz.router)
app.include_router(tutor.router)
app.include_router(retrieval.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "Nucera backend"}


@app.get("/health")
def health():
    return {"status": "healthy"}
