"""
Care Connect - AI Specialist Recommendation & Triage Engine
Modular Python-based triage assistance module designed for specialist mapping and urgency scoring.
"""

from typing import Dict, List, Any

# Initial knowledge mapping for common medical symptom clusters to medical specializations
SPECIALTY_KNOWLEDGE_BASE = {
    'Cardiology': [
        'chest pain', 'palpitations', 'shortness of breath', 'heart flutter', 
        'irregular heartbeat', 'high blood pressure', 'angina', 'dizziness on exertion'
    ],
    'Neurology': [
        'headache', 'migraine', 'seizure', 'numbness', 'tingling', 'tremor', 
        'memory loss', 'vertigo', 'facial drooping', 'paralysis'
    ],
    'Orthopedics': [
        'joint pain', 'bone fracture', 'back pain', 'knee swelling', 'shoulder pain', 
        'sprain', 'arthritis', 'limited mobility', 'stiffness'
    ],
    'Dermatology': [
        'skin rash', 'itching', 'acne', 'mole change', 'eczema', 'psoriasis', 
        'hives', 'blister', 'dry patches', 'skin lesion'
    ],
    'Pediatrics': [
        'infant fever', 'childhood cough', 'growth concern', 'pediatric vaccination', 
        'colic', 'child development', 'measles', 'ear infection in child'
    ],
    'General Medicine': [
        'mild fever', 'cold', 'fatigue', 'general weakness', 'cough', 
        'sore throat', 'body ache', 'upset stomach', 'indigestion'
    ]
}

def analyze_symptoms(symptom_text: str) -> Dict[str, Any]:
    """
    Analyzes patient input symptoms text to predict the most suitable medical department
    and calculate a recommendation confidence score.
    """
    if not symptom_text or not symptom_text.strip():
        return {
            'recommended_specialty': 'General Medicine',
            'confidence': 0.0,
            'matched_keywords': [],
            'urgency_level': 'Normal',
            'summary': 'No specific symptoms entered. General physician consultation advised.'
        }

    text = symptom_text.lower()
    specialty_scores = {}
    matched_keywords_by_specialty = {}

    for specialty, keywords in SPECIALTY_KNOWLEDGE_BASE.items():
        matches = [kw for kw in keywords if kw in text]
        if matches:
            # Score calculated based on keyword matches
            specialty_scores[specialty] = len(matches)
            matched_keywords_by_specialty[specialty] = matches

    # Determine urgency indicators
    emergency_flags = ['severe chest pain', 'paralysis', 'unconscious', 'cannot breathe', 'massive bleeding']
    is_emergency = any(flag in text for flag in emergency_flags)

    if not specialty_scores:
        return {
            'recommended_specialty': 'General Medicine',
            'confidence': 0.5,
            'matched_keywords': [],
            'urgency_level': 'Emergency' if is_emergency else 'Standard',
            'summary': 'Symptoms suggest a preliminary consultation with a General Physician for thorough diagnosis.'
        }

    # Pick top scoring specialty
    best_specialty = max(specialty_scores.items(), key=lambda x: x[1])[0]
    best_matches = matched_keywords_by_specialty[best_specialty]
    confidence = min(0.95, 0.4 + (len(best_matches) * 0.2))

    return {
        'recommended_specialty': best_specialty,
        'confidence': round(confidence, 2),
        'matched_keywords': best_matches,
        'urgency_level': 'Emergency' if is_emergency else 'Standard',
        'summary': f"Identified matches ({', '.join(best_matches)}) pointing towards {best_specialty}."
    }
