import os
from flask import Flask, jsonify
from flask_cors import CORS

from config import SECRET_KEY, SESSION_COOKIE_NAME, STATIC_DIR
from aqeelos.db import init_db
from aqeelos.auth import load_session
from aqeelos.security import check_payload_size, csrf_token, require_csrf
from aqeelos.routes.public import bp as public_bp
from aqeelos.routes.api import bp as api_bp
from aqeelos.routes.api_support import bp as support_bp
from aqeelos.routes.api_chat import bp as chat_bp
from aqeelos.routes.api_control import bp as control_bp
from aqeelos.services.task_queue import start as start_worker


def create_app():
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.secret_key = SECRET_KEY
    app.config["SESSION_COOKIE_NAME"] = SESSION_COOKIE_NAME
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
    app.config["CSRF_ENABLED"] = True
    CORS(app, supports_credentials=True)
    init_db()

    @app.before_request
    def _session():
        load_session()
        err = check_payload_size(app.config["MAX_CONTENT_LENGTH"])
        if err:
            return err
        err = require_csrf()
        if err:
            return err

    @app.after_request
    def _csrf_header(resp):
        try:
            resp.headers['X-CSRF-Token'] = csrf_token()
        except Exception:
            pass
        return resp

    @app.get('/api/csrf')
    def get_csrf():
        return jsonify({'csrf_token': csrf_token()})

    app.register_blueprint(public_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(support_bp, url_prefix="/api")
    app.register_blueprint(chat_bp, url_prefix="/api")
    app.register_blueprint(control_bp, url_prefix="/api")
    if os.environ.get("AQEELOS_DISABLE_WORKER") != "1":
        start_worker()
    return app


app = create_app()

if __name__ == "__main__":
    print("AqeelOS: http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)

