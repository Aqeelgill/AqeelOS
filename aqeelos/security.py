import secrets
from flask import current_app, jsonify, request, session

SAFE = {'GET', 'HEAD', 'OPTIONS'}
CSRF_EXEMPT = {
    '/api/csrf',
    '/api/auth/login', '/api/auth/register', '/api/auth/logout',
    '/api/auth/owner', '/api/auth/ceo', '/api/auth/agent-view',
    '/api/support/chat', '/api/support/escalate', '/api/ceo/chat',
}


def csrf_token():
    tok = session.get('_csrf')
    if not tok:
        tok = secrets.token_urlsafe(32)
        session['_csrf'] = tok
    return tok


def require_csrf():
    if not current_app.config.get('CSRF_ENABLED', True):
        return None
    if request.method in SAFE:
        return None
    if request.path in CSRF_EXEMPT:
        return None
    sent = request.headers.get('X-CSRF-Token') or (request.get_json(silent=True) or {}).get('_csrf') or request.form.get('_csrf')
    if not sent or not session.get('_csrf') or sent != session.get('_csrf'):
        return jsonify({'error': 'Invalid or missing CSRF token'}), 403
    return None


def check_payload_size(max_bytes=64 * 1024):
    if request.content_length and request.content_length > max_bytes:
        return jsonify({'error': 'Request too large'}), 413
    return None
