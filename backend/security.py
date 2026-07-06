import re
import os
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet

# Static salt for local key derivation (in production this should be stored securely)
SALT = b'\x1c\x9b\xe4\xaf\x8f\x87\xde\xbd\xec\xa9\xad\x8a\x17\xe0\xab\x12'

def derive_key(password: str) -> bytes:
    """Derive an AES-256 key from a user password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_data(data: str, password: str) -> str:
    """Encrypt plain text data using the user password."""
    key = derive_key(password)
    f = Fernet(key)
    return f.encrypt(data.encode()).decode()

def decrypt_data(encrypted_data: str, password: str) -> str:
    """Decrypt cipher text using the user password."""
    key = derive_key(password)
    f = Fernet(key)
    return f.decrypt(encrypted_data.encode()).decode()

def redact_pii(text: str) -> str:
    """
    Redact academic and personal PII from text before passing it to any LLM.
    Filters emails, phone numbers, common student ID patterns, and school-specific IDs.
    """
    # Redact Emails
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[REDACTED_EMAIL]', text)
    
    # Redact Phone Numbers (various formats)
    text = re.sub(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[REDACTED_PHONE]', text)
    
    # Redact Student IDs (e.g. 1234567, ST12345, 987-654-321)
    text = re.sub(r'\b\d{7,10}\b', '[REDACTED_STUDENT_ID]', text)
    text = re.sub(r'\b[A-Za-z]{2}\d{5,8}\b', '[REDACTED_STUDENT_ID]', text)
    
    # Redact typical academic grades block if it contains direct name links
    # e.g., "Student Name: John Doe (GPA: 3.8)"
    text = re.sub(r'(?i)student\s+name:\s*[A-Z][a-z]+\s+[A-Z][a-z]+', 'Student Name: [REDACTED_NAME]', text)
    
    return text
