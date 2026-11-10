"""Authorize a personal Gmail sender and save credentials only to ignored .env."""
import argparse
import os
from pathlib import Path
import subprocess

from dotenv import set_key
from google_auth_oauthlib.flow import InstalledAppFlow


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-file', type=Path, required=True)
    parser.add_argument('--sender', required=True)
    parser.add_argument('--recipient', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = root / '.env'
    if subprocess.run(['git', 'check-ignore', '-q', '.env'], cwd=root).returncode:
        parser.error('.env must be ignored by Git')
    if any('@' not in a or any(c in a for c in '\r\n,;') for a in (args.sender, args.recipient)):
        parser.error('Provide single sender and recipient addresses')
    flow = InstalledAppFlow.from_client_secrets_file(
        str(args.client_file), scopes=['https://www.googleapis.com/auth/gmail.send'])
    creds = flow.run_local_server(host='localhost', port=0, open_browser=True,
                                  authorization_prompt_message='Complete Gmail authorization in your browser.',
                                  success_message='Gmail connected. You may close this window.',
                                  access_type='offline', prompt='consent', timeout_seconds=180)
    if not creds.refresh_token:
        raise SystemExit('No refresh token returned; local settings unchanged')
    old_umask = os.umask(0o077)
    try:
        destination.touch(mode=0o600, exist_ok=True)
        destination.chmod(0o600)
        for key, value in dict(GMAIL_CLIENT_ID=creds.client_id, GMAIL_CLIENT_SECRET=creds.client_secret,
                               GMAIL_REFRESH_TOKEN=creds.refresh_token, GMAIL_SENDER=args.sender,
                               DIGEST_RECIPIENT=args.recipient).items():
            set_key(str(destination), key, value)
        destination.chmod(0o600)
    finally:
        os.umask(old_umask)
    print('Gmail configuration saved locally. No email sent.')


if __name__ == '__main__':
    main()
