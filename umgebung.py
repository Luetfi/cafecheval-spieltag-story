"""Zugangsdaten lesen: zuerst Umgebungsvariablen (GitHub Actions Secrets), sonst lokale .env-Dateien."""
import os
import pathlib

HIER = pathlib.Path(__file__).resolve().parent
_DATEIEN = (HIER / '.env', HIER.parent.parent / '.env')


def wert(name, pflicht=True):
    if os.environ.get(name):
        return os.environ[name].strip()
    for env in _DATEIEN:
        if env.exists():
            for line in env.read_text(encoding='utf-8-sig').splitlines():
                if line.startswith(f'{name}='):
                    return line.split('=', 1)[1].strip().strip('"\'')
    if pflicht:
        raise RuntimeError(f'{name} fehlt (Umgebungsvariable oder .env)')
    return None
