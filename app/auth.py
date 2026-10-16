import hmac
import time

from fastapi import HTTPException


class Auth:
    def __init__(self, settings):
        self.mode = settings.auth_mode
        self.credentials = settings.xsuaa_credentials() if self.mode == 'xsuaa' else None
        self._static_token = settings.access_token.encode('utf-8') if self.mode == 'xsuaa' else b''

    def verify(self, authorization: str):
        if self.mode == 'none':
            return float('inf')
        scheme, _, token = authorization.partition(' ')
        if scheme.lower() != 'bearer' or not token or len(token) > 16384:
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        # Optional shared token. Empty disables it; a mismatch still follows full XSUAA validation.
        if self._static_token and token.isascii() and hmac.compare_digest(token.encode('ascii'), self._static_token):
            return float('inf')
        try:
            from sap import xssec
            import jwt
            context = xssec.create_security_context(token, self.credentials)
            # Claims are inspected only AFTER signature / audience validation by SAP xssec.
            claims = jwt.decode(token, options={'verify_signature': False})
            expiry = float(claims['exp'])
            if expiry <= time.time() or claims.get('zid') != self.credentials['identityzoneid']:
                raise ValueError('Expired token or incorrect tenant')
            audiences = claims.get('aud', [])
            if isinstance(audiences, str):
                audiences = [audiences]
            if not {self.credentials['xsappname'], self.credentials['clientid']}.intersection(audiences):
                raise ValueError('Incorrect audience')
            if claims.get('iss') != self.credentials['url'].rstrip('/') + '/oauth/token':
                raise ValueError('Incorrect issuer')
        except Exception:
            raise HTTPException(401, 'Invalid or expired access token', headers={'WWW-Authenticate': 'Bearer'}) from None
        if not context.check_scope(self.credentials['xsappname'] + '.Transcribe'):
            raise HTTPException(403, 'Transcribe scope required')
        return expiry
