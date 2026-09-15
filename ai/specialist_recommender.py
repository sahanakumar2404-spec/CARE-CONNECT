"""
Care Connect - AI Specialist Recommendation Engine
Module: ai/specialist_recommender.py

Provides explainable, rule-based medical specialization recommendations to assist patients
in navigating appointment booking based on self-reported health concerns.

SAFETY BOUNDARY:
- This module is NOT a diagnostic system.
- It never diagnoses diseases or clinical conditions.
- It never recommends treatments, prescriptions, medications, or dosages.
- It provides appointment guidance only.
"""

import re
from typing import Dict, Any, List, Optional

# Standard safety disclaimers
DISCLAIMER_TEXT = (
    "This recommendation is for appointment guidance only and is not a medical diagnosis. "
    "AI-generated appointment guidance only. This does not diagnose or treat medical conditions."
)

UNCLEAR_RESPONSE_TEXT = (
    "Unable to confidently recommend a specialty. "
    "Please consult a general physician or contact the hospital."
)

# Knowledge mapping for specialty recommendation
# Organized as tuples: (specialty_name, list_of_keywords_and_phrases)
SPECIALTY_MAPPINGS: Dict[str, List[str]] = {
    'Neurology': [
        'headache', 'headaches', 'migraine', 'migraines', 'dizziness', 'dizzy',
        'seizure', 'seizures', 'vertigo', 'numbness', 'tingling', 'tremor',
        'tremors', 'difficulty concentrating', 'concentration', 'memory loss',
        'frequent headaches', 'confusion', 'head pain', 'fainting'
    ],
    'Cardiology': [
        'chest pain', 'heart', 'palpitations', 'heart flutter', 'irregular heartbeat',
        'high blood pressure', 'hypertension', 'angina', 'shortness of breath',
        'cardiac', 'cardiovascular', 'heart racing', 'tightness in chest'
    ],
    'Dermatology': [
        'skin rash', 'skin rashes', 'rash', 'rashes', 'acne', 'skin irritation',
        'eczema', 'psoriasis', 'hives', 'itching', 'itchy skin',
        'dry patches', 'skin lesion', 'blister', 'blisters', 'mole change',
        'skin allergy', 'skin redness'
    ],
    'Gastroenterology': [
        'stomach pain', 'digestion', 'digestive', 'acid reflux', 'heartburn',
        'nausea', 'vomiting', 'bowel', 'diarrhea', 'constipation', 'abdomen',
        'abdominal pain', 'bloating', 'stomach ache', 'indigestion', 'cramps'
    ],
    'Orthopedics': [
        'joint pain', 'bone injury', 'bone fracture', 'fracture', 'knee',
        'knee swelling', 'back pain', 'shoulder pain', 'sprain', 'sprained',
        'arthritis', 'limited mobility', 'stiffness', 'bone', 'joints',
        'swollen knee', 'spine', 'hip pain', 'ligament'
    ],
    'Ophthalmology': [
        'eye', 'eyes', 'vision', 'blurry vision', 'blurred vision', 'cornea',
        'cataract', 'glaucoma', 'eye irritation', 'dry eyes', 'double vision',
        'eye pain', 'impaired vision', 'red eyes', 'stye', 'eye-related concern'
    ],
    'ENT': [
        'ear', 'ears', 'nose', 'throat', 'sore throat', 'sinus', 'sinuses',
        'hearing', 'hearing loss', 'tonsils', 'earache', 'nasal congestion',
        'tinnitus', 'ear infection', 'runny nose', 'hoarse voice', 'throat pain'
    ],
    'Dentistry': [
        'tooth', 'teeth', 'toothache', 'dental', 'gums', 'bleeding gums',
        'cavity', 'cavities', 'jaw pain', 'tooth sensitivity', 'oral pain',
        'dental concern'
    ],
    'Gynecology': [
        'pregnancy', 'pregnant', 'reproductive health', 'reproductive',
        'menstrual', 'menstruation', 'period pain', 'pelvic pain', 'ovarian',
        'fertility', 'postpartum', 'cramps menstrual', 'irregular periods'
    ],
    'Pediatrics': [
        'child', 'children', 'infant', 'baby', 'toddler', 'pediatric',
        'pediatrics', 'newborn', 'kid', 'child development', 'child-related concern'
    ],
    'General Medicine': [
        'fever', 'cold', 'flu', 'general weakness', 'fatigue', 'body ache',
        'chills', 'malaise', 'mild fever', 'feeling unwell', 'exhaustion'
    ]
}

# Explicit clinical explanation texts tailored to non-diagnostic appointment navigation
SPECIALTY_EXPLANATIONS: Dict[str, str] = {
    'Neurology': "Your description contains concerns commonly associated with neurological care.",
    'Cardiology': "Your description contains concerns commonly associated with cardiovascular care.",
    'Dermatology': "Your description contains concerns commonly associated with dermatological care.",
    'Gastroenterology': "Your description contains concerns commonly associated with gastroenterology and digestive care.",
    'Orthopedics': "Your description contains concerns commonly associated with orthopedic and musculoskeletal care.",
    'Ophthalmology': "Your description contains concerns commonly associated with ophthalmology and eye care.",
    'ENT': "Your description contains concerns commonly associated with ear, nose, and throat (ENT) care.",
    'Dentistry': "Your description contains concerns commonly associated with dental care.",
    'Gynecology': "Your description contains concerns commonly associated with gynecological and reproductive health.",
    'Pediatrics': "Your description contains concerns commonly associated with pediatric child care.",
    'General Medicine': "Your description contains general systemic concerns commonly evaluated by a primary care or general medicine physician."
}

MAX_CONCERN_LENGTH = 1000
MIN_CONCERN_LENGTH = 3

def sanitize_and_validate_input(concern_text: Optional[str]) -> Dict[str, Any]:
    """
    Validates and cleans input health concern text.
    Returns validation status, error message (if invalid), and normalized text.
    """
    if concern_text is None or not concern_text.strip():
        return {
            'is_valid': False,
            'reason': "Please enter a brief description of your health concern.",
            'cleaned_text': ""
        }

    raw = concern_text.strip()

    if len(raw) < MIN_CONCERN_LENGTH:
        return {
            'is_valid': False,
            'reason': UNCLEAR_RESPONSE_TEXT,
            'cleaned_text': raw
        }

    if len(raw) > MAX_CONCERN_LENGTH:
        return {
            'is_valid': False,
            'reason': f"Health concern description exceeds the maximum limit of {MAX_CONCERN_LENGTH} characters. Please provide a more concise description.",
            'cleaned_text': raw[:MAX_CONCERN_LENGTH]
        }

    # Detect gibberish: no alphanumeric characters, or pure repeating characters
    alphanumeric_chars = [c for c in raw if c.isalnum()]
    if not alphanumeric_chars:
        return {
            'is_valid': False,
            'reason': UNCLEAR_RESPONSE_TEXT,
            'cleaned_text': raw
        }

    # Repeated single character sequences (e.g. 'aaaaaaa' or '???????')
    if len(set(alphanumeric_chars)) <= 1 and len(alphanumeric_chars) > 4:
        return {
            'is_valid': False,
            'reason': UNCLEAR_RESPONSE_TEXT,
            'cleaned_text': raw
        }

    return {
        'is_valid': True,
        'reason': "",
        'cleaned_text': raw
    }

def recommend_specialist(concern_text: Optional[str]) -> Dict[str, Any]:
    """
    Analyzes patient concern and returns recommended medical specialty,
    appointment navigation reason, safe confidence level, and disclaimer.

    Guarantees:
    - Zero disease diagnosis.
    - Zero medication or treatment advice.
    - Safe confidence wording.
    """
    validation = sanitize_and_validate_input(concern_text)
    if not validation['is_valid']:
        return {
            'status': 'unclear',
            'recommended_specialty': None,
            'confidence': 'Low',
            'confidence_display': 'Recommendation confidence: Low',
            'reason': validation['reason'],
            'matched_keywords': [],
            'disclaimer': DISCLAIMER_TEXT
        }

    text = validation['cleaned_text'].lower()
    scores: Dict[str, int] = {}
    matched_by_specialty: Dict[str, List[str]] = {}

    for specialty, keywords in SPECIALTY_MAPPINGS.items():
        matches = []
        specialty_score = 0
        for kw in keywords:
            # Word boundary matching for short single words, substring for multi-word phrases
            if ' ' in kw or '-' in kw:
                if kw in text:
                    specialty_score += 2  # Higher weight for multi-word specific phrases
                    matches.append(kw)
            else:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, text):
                    specialty_score += 1
                    matches.append(kw)

        if specialty_score > 0:
            scores[specialty] = specialty_score
            matched_by_specialty[specialty] = matches

    if not scores:
        return {
            'status': 'unclear',
            'recommended_specialty': None,
            'confidence': 'Low',
            'confidence_display': 'Recommendation confidence: Low',
            'reason': UNCLEAR_RESPONSE_TEXT,
            'matched_keywords': [],
            'disclaimer': DISCLAIMER_TEXT
        }

    # Sort specialties by highest score
    sorted_specialties = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_specialty, best_score = sorted_specialties[0]
    matched_kws = matched_by_specialty.get(best_specialty, [])

    # Assign safe non-medical confidence
    if best_score >= 2 or len(matched_kws) >= 2:
        confidence = "High"
    elif best_score == 1:
        confidence = "Medium"
    else:
        confidence = "Low"

    explanation = SPECIALTY_EXPLANATIONS.get(
        best_specialty,
        f"Your description contains concerns commonly associated with {best_specialty.lower()} care."
    )

    return {
        'status': 'success',
        'recommended_specialty': best_specialty,
        'confidence': confidence,
        'confidence_display': f"Recommendation confidence: {confidence}",
        'reason': explanation,
        'matched_keywords': matched_kws,
        'disclaimer': DISCLAIMER_TEXT
    }
