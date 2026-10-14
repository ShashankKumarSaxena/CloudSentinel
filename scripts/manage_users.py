"""Local bootstrap/password recovery. Passwords are never accepted as arguments."""
import argparse
import getpass
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.auth import AuthService, AuthError
from backend.app.models import UserCreate
from backend.app.store import Store
from pydantic import ValidationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create-admin', 'reset-password'])
    parser.add_argument('--username', default=None)
    args = parser.parse_args()
    username = args.username or input('Username: ').strip()
    password = getpass.getpass('Password (at least 12 characters): ')
    confirmation = getpass.getpass('Confirm password: ')
    if password != confirmation:
        raise SystemExit('Passwords did not match; nothing changed.')
    auth = AuthService(Store(Path(os.environ.get('CLOUDSENTINEL_DB', ROOT / '.runtime/cloudsentinel.db'))))
    try:
        if args.action == 'create-admin':
            auth.create_user(UserCreate(username=username, display_name=username, password=password, role='admin'), bootstrap=True)
            print('Administrator created. Sign in using your chosen credentials.')
        else:
            user = next((u for u in auth.list_users() if u['username'] == username.lower()), None)
            if user is None:
                raise SystemExit('Account not found; nothing changed.')
            auth.change_password(user['id'], '', password, 'local-cli', require_current=False)
            print('Password updated. Existing sessions were revoked.')
    except (AuthError, ValidationError):
        raise SystemExit('Could not update the account. Use a valid username, a 12–256 character password, and create only the first administrator through this command.') from None


if __name__ == '__main__':
    main()
