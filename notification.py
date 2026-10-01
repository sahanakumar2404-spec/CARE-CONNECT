from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from database import db
from models.user import User
from models.notification import Notification
from services.auth_service import login_required, get_current_user
from services.notification_service import (
    get_user_notifications,
    get_unread_count,
    mark_as_read,
    mark_all_as_read,
    check_and_generate_reminders_for_user
)

notification_bp = Blueprint('notification', __name__, url_prefix='/notifications')


@notification_bp.route('', methods=['GET'], strict_slashes=False)
@notification_bp.route('/', methods=['GET'], strict_slashes=False)
@login_required
def notifications_list():
    """
    Notification Center:
    Displays chronological in-app notifications for the authenticated user.
    Triggers automatic due reminder generation.
    Supports filtering by 'all' or 'unread'.
    """
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('auth.login'))

    # Generate any due upcoming appointment reminders for this user
    try:
        check_and_generate_reminders_for_user(current_user)
    except Exception:
        pass

    filter_type = request.args.get('filter', 'all').strip().lower()
    unread_only = (filter_type == 'unread')

    notifications = get_user_notifications(current_user.id, limit=100, unread_only=unread_only)
    total_unread = get_unread_count(current_user.id)
    total_count = Notification.query.filter_by(recipient_user_id=current_user.id).count()

    return render_template(
        'dashboards/notifications.html',
        notifications=notifications,
        filter_type=filter_type,
        total_unread=total_unread,
        total_count=total_count,
        user=current_user
    )


@notification_bp.route('/unread-count', methods=['GET'])
@login_required
def unread_count():
    """Returns JSON unread count for dynamic navbar badge updates."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({'unread_count': 0})
    return jsonify({'unread_count': get_unread_count(current_user.id)})


@notification_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """
    Marks a single notification as read.
    Enforces strict ownership check (IDOR protection returns HTTP 403).
    """
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('auth.login'))

    notif = db.session.get(Notification, notification_id)
    if not notif:
        abort(404)

    if notif.recipient_user_id != current_user.id:
        abort(403)

    success, msg = mark_as_read(notification_id, current_user.id)

    # Check for AJAX/JSON request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': success,
            'message': msg,
            'unread_count': get_unread_count(current_user.id)
        })

    next_url = request.referrer or url_for('notification.notifications_list')
    return redirect(next_url)


@notification_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Marks all unread notifications as read for the authenticated user."""
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('auth.login'))

    count = mark_all_as_read(current_user.id)
    if count > 0:
        flash(f"Marked {count} notification{'s' if count != 1 else ''} as read.", 'success')
    else:
        flash("No unread notifications to mark as read.", 'info')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': True,
            'marked_count': count,
            'unread_count': 0
        })

    next_url = request.referrer or url_for('notification.notifications_list')
    return redirect(next_url)
