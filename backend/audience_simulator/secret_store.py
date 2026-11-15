"""Cifratura a riposo dei segreti (chiavi API).

Le chiavi non vengono mai scritte in chiaro su disco: il file delle credenziali contiene solo un token
Fernet (AES-128-CBC + HMAC-SHA256, autenticato). La chiave di cifratura sta in un file separato con
permessi 0600 in una cartella 0700 dell'utente (di default ``~/.audience-simulator``), fuori dal progetto:
non finisce in git, nei backup della cartella di lavoro, nei report né nello storage S3.

Limite dichiarato: chi ha accesso completo al tuo account macOS/Linux può leggere anche la chiave di
cifratura. La cifratura protegge da copie, backup e condivisioni accidentali del file, non da un malware
che gira con i tuoi permessi.
"""

import os
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken

KEY_FILE_ENV = "AUDIENCE_CREDENTIALS_KEY_FILE"


class SecretStoreError(ValueError):
    pass


def key_file_path():
    configured = os.environ.get(KEY_FILE_ENV)
    return Path(configured).expanduser() if configured else Path.home() / ".audience-simulator" / "credentials.key"


def _master_key():
    path = key_file_path()
    if path.exists():
        if path.stat().st_mode & 0o077:
            path.chmod(0o600)
        return path.read_bytes().strip()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = Fernet.generate_key()
    temporary = path.parent / f".key.{uuid4().hex}.tmp"
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(key)
        try:
            os.link(temporary, path)  # atomico: se un altro processo ha creato la chiave prima, vince lui
        except FileExistsError:
            return path.read_bytes().strip()
    finally:
        temporary.unlink(missing_ok=True)
    return key


def encrypt_secret(plaintext):
    if not plaintext:
        return ""
    return Fernet(_master_key()).encrypt(plaintext.encode()).decode()


def decrypt_secret(token):
    if not token:
        return ""
    try:
        return Fernet(_master_key()).decrypt(token.encode()).decode()
    except InvalidToken:
        raise SecretStoreError(
            "Impossibile decifrare la chiave salvata (file di cifratura cambiato o credenziali danneggiate). "
            "Reinserisci la chiave in Impostazioni → Motore AI."
        ) from None
