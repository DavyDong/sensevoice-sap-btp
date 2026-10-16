import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    model_root: Path = field(default_factory=lambda: Path(os.getenv('MODEL_ROOT', 'models')))
    auth_mode: str = field(default_factory=lambda: os.getenv('AUTH_MODE', 'none'))
    access_token: str = field(default_factory=lambda: os.getenv('ACCESS_TOKEN', ''), repr=False)
    host: str = field(default_factory=lambda: os.getenv('HOST', '127.0.0.1'))
    port: int = field(default_factory=lambda: int(os.getenv('PORT', '8000')))
    threads: int = field(default_factory=lambda: int(os.getenv('TORCH_THREADS', '4')))
    max_bytes: int = 20 * 1024 * 1024
    max_audio_seconds: int = 120
    max_session_seconds: int = 600
    max_segment_ms: int = 10000
    allowed_origins: tuple = field(default_factory=lambda: tuple(filter(None, os.getenv('ALLOWED_ORIGINS', '').split(','))))

    def validate(self):
        cloud = bool(os.getenv('VCAP_APPLICATION'))
        if self.auth_mode not in ('none', 'xsuaa'):
            raise ValueError('AUTH_MODE must be none or xsuaa')
        if self.auth_mode == 'none' and (cloud or self.host not in ('127.0.0.1', 'localhost', '::1')):
            raise ValueError('Unauthenticated mode requires loopback and cannot run on Cloud Foundry')
        if not 1 <= self.threads <= 32:
            raise ValueError('TORCH_THREADS must be between 1 and 32')
        if self.access_token and not re.fullmatch(r'[A-Za-z0-9._~+/=\-]{32,256}', self.access_token):
            raise ValueError('ACCESS_TOKEN must be empty or 32-256 characters using letters, digits, or . _ ~ + / = -')

    def xsuaa_credentials(self):
        bindings = json.loads(os.getenv('VCAP_SERVICES', '{}')).get('xsuaa', [])
        name = os.getenv('XSUAA_SERVICE_NAME', 'sensevoice-xsuaa')
        matches = [b['credentials'] for b in bindings if b.get('name') == name]
        if len(matches) != 1:
            raise ValueError('Exactly one named XSUAA service binding is required')
        return matches[0]
