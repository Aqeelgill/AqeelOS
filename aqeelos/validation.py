import re

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def clean_text(v, max_len=4000):
    if v is None:
        return ''
    s = str(v).strip()
    return s[:max_len]


def valid_email(v):
    s = clean_text(v, 254).lower()
    return s if EMAIL_RE.match(s) else None


def valid_password(v, min_len=6, max_len=256):
    s = str(v or '')
    return s if min_len <= len(s) <= max_len else None
