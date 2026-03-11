from google.oauth2 import service_account
from googleapiclient.discovery import build

KEYFILE = 'secrets/service-account-dockmaster.json'
creds = service_account.Credentials.from_service_account_file(KEYFILE)
iam = build('iam', 'v1', credentials=creds)

# List keys for this service account
sa_email = creds.service_account_email
project_id = creds.project_id
name = f'projects/{project_id}/serviceAccounts/{sa_email}'
keys = iam.projects().serviceAccounts().keys().list(name=name).execute()
print(f'Found {len(keys.get("keys", []))} keys for {sa_email}')
for k in keys.get('keys', []):
    print(f'  - {k["name"].split("/")[-1][:12]}... ({k["keyType"]})')
print('IAM API access works.')