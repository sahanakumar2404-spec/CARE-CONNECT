import os
import secrets
from datetime import datetime
from flask import Flask, render_template, request, session, abort
from config import config_by_name
from database import init_db
from routes import register_blueprints
from services.auth_service import get_current_user

def create_app(config_name=None):
    """Application factory for Care Connect."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__, template_folder='templates', static_folder='static')
    
    # Load configuration
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))

    # Initialize Database and Seed Data
    init_db(app)

    # Register Blueprints
    register_blueprints(app)

    def generate_csrf_token():
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(32)
        return session['_csrf_token']

    # Global Context Processors for Jinja Templates
    @app.context_processor
    def inject_globals():
        return {
            'current_user': get_current_user(),
            'current_year': datetime.now().year,
            'app_name': 'Care Connect',
            'csrf_token': generate_csrf_token
        }

    # Lightweight CSRF Protection
    @app.before_request
    def validate_csrf():
        # Validate CSRF when WTF_CSRF_ENABLED is explicitly enabled
        if not app.config.get('WTF_CSRF_ENABLED', False):
            return
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            expected = session.get('_csrf_token')
            if not expected or not token or not secrets.compare_digest(str(token), str(expected)):
                abort(400, description="Invalid or missing CSRF token")

    # Security Headers
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    # Error Handlers
    @app.errorhandler(403)
    def access_forbidden(e):
        return render_template('403.html'), 403

    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    return app

# Application entry point
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting Care Connect on http://127.0.0.1:{port}")
    app.run(host='127.0.0.1', port=port, debug=True)
