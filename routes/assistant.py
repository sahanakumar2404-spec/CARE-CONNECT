from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from services.auth_service import login_required, get_current_user
from ai.care_connect_assistant import process_assistant_message
from models.user import User

assistant_bp = Blueprint('assistant', __name__)

PATIENT_SUGGESTIONS = [
    "What is my next appointment?",
    "Show my upcoming appointments",
    "What appointments do I have today?",
    "Which hospitals are registered?",
    "Find available specialists",
    "How do I book an appointment?",
    "How do I cancel an appointment?",
    "What is my appointment number?"
]

DOCTOR_SUGGESTIONS = [
    "Show my appointments today",
    "Show my upcoming appointments",
    "What are my working hours?",
    "Show my affiliated hospital",
    "Show my patient consultation history",
    "Which hospitals are registered?"
]

HOSPITAL_SUGGESTIONS = [
    "Show today's appointment count",
    "Show available doctors",
    "Show hospital appointment information",
    "Show patient-load prediction",
    "Which hospitals are registered?"
]


@assistant_bp.route('/assistant', methods=['GET', 'POST'])
@login_required
def assistant():
    """
    Care Connect AI Assistant portal for authenticated users of any role.
    Handles both interactive UI view and form submissions.
    """
    current_user = get_current_user()
    if not current_user:
        return redirect(url_for('auth.login'))

    # Select role-appropriate suggested questions
    if current_user.is_patient():
        suggested_questions = PATIENT_SUGGESTIONS
    elif current_user.is_doctor():
        suggested_questions = DOCTOR_SUGGESTIONS
    elif current_user.is_hospital():
        suggested_questions = HOSPITAL_SUGGESTIONS
    else:
        suggested_questions = PATIENT_SUGGESTIONS

    if request.method == 'POST':
        # Check if request is JSON or form post
        if request.is_json:
            data = request.get_json() or {}
            message = data.get('message', '')
            res = process_assistant_message(current_user, message)
            res['timestamp'] = datetime.now().strftime("%I:%M %p")
            return jsonify(res)
        else:
            message = request.form.get('message', '')
            res = process_assistant_message(current_user, message)
            return render_template(
                'dashboards/assistant.html',
                user=current_user,
                suggested_questions=suggested_questions,
                initial_query=message,
                initial_response=res.get('response', '')
            )

    return render_template(
        'dashboards/assistant.html',
        user=current_user,
        suggested_questions=suggested_questions
    )


@assistant_bp.route('/assistant/chat', methods=['POST'])
@login_required
def chat_api():
    """AJAX endpoint for asynchronous AI Assistant conversation turns."""
    current_user = get_current_user()
    if not current_user:
        return jsonify({"status": "error", "response": "Authentication required."}), 401

    data = request.get_json() or {}
    message = data.get('message', '')
    res = process_assistant_message(current_user, message)
    res['timestamp'] = datetime.now().strftime("%I:%M %p")
    return jsonify(res)
