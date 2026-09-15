from functools import wraps
from flask import session, redirect, url_for, flash, request
from database import db
from models.user import User

def login_user(user: User):
    """Sets session variables for an authenticated user."""
    session.clear()
    session['user_id'] = user.id
    session['user_role'] = user.role
    session['user_name'] = user.full_name
    session['user_email'] = user.email
    session.permanent = True

def logout_user():
    """Clears user session."""
    session.clear()

def get_current_user():
    """Fetches current User instance from database using session user_id."""
    user_id = session.get('user_id')
    if not user_id:
        return None
    return db.session.get(User, user_id)

def login_required(f):
    """Decorator to require user authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    """Decorator to enforce specific user roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login', next=request.url))
            
            user_role = session.get('user_role')
            if user_role not in allowed_roles:
                flash('You are not authorized to access this section.', 'danger')
                if user_role == User.ROLE_HOSPITAL:
                    return redirect(url_for('hospital.dashboard'))
                elif user_role == User.ROLE_DOCTOR:
                    return redirect(url_for('doctor.dashboard'))
                elif user_role == User.ROLE_PATIENT:
                    return redirect(url_for('patient.dashboard'))
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
