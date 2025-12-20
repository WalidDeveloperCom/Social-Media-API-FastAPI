# File: app/main.py
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, posts, comments, likes, follow, websocket
from app.db.session import engine, Base

# create DB metadata (for dev only; use alembic in prod)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Social Media API - FastAPI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(posts.router, prefix="/api/posts", tags=["posts"])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"])
app.include_router(likes.router, prefix="/api/likes", tags=["likes"])
app.include_router(follow.router, prefix="/api/follow", tags=["follow"])
app.include_router(websocket.router, prefix="/ws", tags=["websocket"])


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
