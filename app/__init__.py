from flask import Flask, render_template, redirect, url_for, session
from app.config import config_by_name
from app.database import close_db, get_db

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    # Teardown database connections
    app.teardown_appcontext(close_db)

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.examiner import examiner_bp
    from app.routes.student import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(examiner_bp)
    app.register_blueprint(student_bp)

    @app.route('/')
    def index():
        if 'user_id' in session:
            role = session.get('role')
            if role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif role == 'examiner':
                return redirect(url_for('examiner.dashboard'))
            elif role == 'student':
                return redirect(url_for('student.dashboard'))
        return redirect(url_for('auth.login'))

    # Context processors and filters
    @app.context_processor
    def inject_user():
        user_info = None
        if 'user_id' in session:
            user_info = {
                'id': session.get('user_id'),
                'username': session.get('username'),
                'role': session.get('role')
            }
        return dict(current_user=user_info)

    @app.template_filter('status_badge')
    def status_badge_filter(status):
        badges = {
            'confirmed': 'bg-success',
            'available': 'bg-success',
            'approved': 'bg-success',
            'submitted': 'bg-success',
            'completed': 'bg-primary',
            'booking_open': 'bg-primary',
            'slot_creation': 'bg-info text-dark',
            'pending': 'bg-warning text-dark',
            'draft': 'bg-secondary',
            'cancelled': 'bg-danger',
            'full': 'bg-danger',
            'rejected': 'bg-danger',
            'closed': 'bg-dark',
            'rescheduled': 'bg-info text-dark'
        }
        css_class = badges.get(str(status).lower(), 'bg-secondary')
        label = str(status).replace('_', ' ').title()
        return f'<span class="badge {css_class}">{label}</span>'

    @app.template_filter('datetime_format')
    def datetime_format_filter(value):
        if not value:
            return '-'
        val_str = str(value).replace('T', ' ')
        return val_str[:16]

    @app.after_request
    def add_no_cache_headers(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.errorhandler(403)
    def forbidden_error(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_error(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        return render_template('errors/500.html'), 500

    return app
