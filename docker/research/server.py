# Adapted from surfsense_local/backend/api/server.py, SurfSense 2.3.1 (Apache-2.0).
# Adds the WorkspaceAI index route to the complete upstream API.
import uvicorn

from api.config import get_settings
from api.main import create_app
from api.workspaceai_index import router


def serve() -> None:
    settings = get_settings()
    app = create_app()
    app.include_router(router)
    uvicorn.run(app, host=settings.host, port=settings.port)
