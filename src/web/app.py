import os
from pathlib import Path
from flask import Flask
from src.config.settings import get_settings
from src.web.routes import init_routes


def create_app(manager=None, detector=None, audio_player=None, recorder=None, db=None):
    settings = get_settings()
    base_dir = Path(__file__).resolve().parent.parent.parent

    templates_dir = base_dir / "templates"
    static_dir = base_dir / "static"

    app = Flask(
        __name__,
        template_folder=str(templates_dir),
        static_folder=str(static_dir)
    )
    app.config["SECRET_KEY"] = settings.secret_key

    init_routes(
        app=app,
        manager=manager,
        detector=detector,
        audio_player=audio_player,
        recorder=recorder,
        db=db
    )

    return app
