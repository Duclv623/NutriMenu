"""Resolve short follow-ups using user topics, never generated answer prose."""
import re

from rag_app.retrieval import fold
from rag_app.safety import is_elliptical_intake_followup


def is_contextual_followup(message, history=None):
    if re.fullmatch(r'(?:(?:ban|hay)\s+)?(?:giai thich (?:lai|de hieu hon)|'
                    r'noi (?:lai|de hieu hon)|tom tat (?:lai|giup)|rut gon|cho vi du)'
                    r'(?:\s+(?:don gian hon|ngan gon hon|giup toi|nhe))?[.!? ]*', fold(message)):
        return True
    if (history and history[-1].get('response', {}).get('clarification_question')
            and re.search(r'\b(?:ca|lam|ngu|thuc|tu|den)\b', fold(message))
            and re.search(r'\b\d{1,2}\s*(?:h\b|gio\b|:\d{2}\b)', fold(message))):
        return True
    return is_elliptical_intake_followup(message) or is_portion_description(message) or bool(re.search(
        r'\b(?:do|nay|ay|vay|no)\b|^nhung\b|^(?:con|the)\b.*\b(?:thi sao|bao nhieu|duoc khong)\b', fold(message)))


def is_portion_description(message):
    return bool(re.fullmatch(
        r'(?:(?:toi|minh|em)\s+)?(?:(?:thuong|hay)\s+)?(?:(?:an|uong)\s+)?'
        r'(?:(?:mot|hai|nua|\d+(?:[.,]\d+)?)\s+)?(?:to|bat|coc|ly|hop)'
        r'(?:\s+(?:nho|lon|vua))?(?:[, ]+(?:an\s+)?(?:het|mot nua|nua|chi mot phan))?',
        fold(message).strip(' ?!.,')))


def topic_for_turn(message, history):
    if is_contextual_followup(message, history):
        for turn in reversed(history):
            stored = turn.get('topic') or turn.get('response', {}).get('context_topic')
            if stored:
                return stored[:1000]
            if not is_contextual_followup(turn['question']):
                return turn['question'][:1000]
    return message[:1000]
