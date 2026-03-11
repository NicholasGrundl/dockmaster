from dockmaster.config import Settings
s = Settings()
print(f'ISSUER: {s.issuer}')
if s.issuer:
    import json
    from pathlib import Path
    key = json.loads(Path(s.issuer).read_text())
    print(f'Service account email: {key["client_email"]}')
    print(f'Project ID: {key["project_id"]}')
    print(f'Key ID: {key["private_key_id"][:12]}...')
    print('Key file is valid.')
else:
    print('ISSUER not set - key file not configured yet.')