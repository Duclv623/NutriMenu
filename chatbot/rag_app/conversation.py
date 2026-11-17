"""Resolve conversational scope and follow-ups from user turns."""
import re

from rag_app.retrieval import fold
from rag_app.safety import is_elliptical_intake_followup


def is_rephrase_request(message):
    q = fold(message)
    return bool(re.fullmatch(r'(?:(?:ban|hay)\s+)?(?:giai thich (?:lai|de hieu hon)|'
                             r'noi (?:lai|de hieu hon)|tom tat (?:lai|giup)|rut gon|cho vi du)'
                             r'(?:\s+(?:don gian hon|ngan gon hon|giup toi|nhe))?[.!? ]*', q)
                or re.match(r'^(?:(?:ban|hay) )?(?:tom lai|viet (?:gon|lai)|chot|gom lai|sap xep lai) '
                            r'(?:(?:giup|cho) (?:minh|toi|em)|cac buoc|theo thu tu)\b', q))


def starts_new_topic(message):
    return bool(re.search(r'\b(?:doi|chuyen|sang) (?:sang )?(?:chu de|cau hoi|chuyen) khac\b|'
                          r'\b(?:doi|chuyen) chu de\b|\bhoi (?:chuyen khac|cau khac|ngoai thuc don)\b',
                          fold(message)))


def is_contextual_followup(message, history=None):
    if starts_new_topic(message):
        return False
    if is_rephrase_request(message):
        return True
    if (history and history[-1].get('response', {}).get('clarification_question')
            and re.search(r'\b(?:ca|lam|ngu|thuc|tu|den)\b', fold(message))
            and re.search(r'\b\d{1,2}\s*(?:h\b|gio\b|:\d{2}\b)', fold(message))):
        return True
    q = fold(message)
    return is_elliptical_intake_followup(message) or is_portion_description(message) or bool(re.search(
        r'^(?:(?:a|u|the thi)[, ]+)?(?:(?:the|vay|no|nhung)\b|'
        r'con\b.*\b(?:thi sao|bao nhieu|duoc khong|the nao)\b)'
        r'|\b(?:cai|mon|loai|lo|hop|phan|bua|thu|nao|cach|viec|ly|to|bat) (?:do|nay|ay|kia|vua noi)\b'
        r'|\b(?:van lam chung|van dung cach|them vao luc nao|cho vao luc nao|cho vao buoc nao)\b'
        r'|\b(?:co them|con san|khong an|khong co)\b.*\b(?:thi sao|thi lam sao|van lam|vao luc nao|nen xep)\b'
        r'|\b(?:nha con san|nha da co|minh da co)\b.*\b(?:chi mua them|mua mot loai|mua them)\b'
        r'|^tu lanh (?:chat|het cho|khong du cho)\b.*\b(?:uu tien|cat|bao quan)\b'
        r'|^(?:quan bao|gia quan bao|hop [a-z] \d+)\b', q))


def is_portion_description(message):
    return bool(re.fullmatch(
        r'(?:(?:toi|minh|em)\s+)?(?:(?:thuong|hay)\s+)?(?:(?:an|uong)\s+)?'
        r'(?:(?:mot|hai|nua|\d+(?:[.,]\d+)?)\s+)?(?:to|bat|coc|ly|hop|lon|chai)'
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


def active_topic_history(history):
    """Keep only the contiguous turns belonging to the current user topic."""
    active = []
    active_topic = None
    for turn in reversed(history):
        topic = turn.get('topic') or turn.get('response', {}).get('context_topic')
        if active_topic and topic and topic != active_topic:
            break
        active_topic = active_topic or topic
        active.append(turn)
        if not topic and not is_contextual_followup(turn['question']):
            break
    return active[::-1]
