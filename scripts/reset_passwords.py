"""Reset AqeelOS owner/CEO access passwords (local)."""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aqeelos.db import init_db
from aqeelos.auth import hash_password, set_setting, audit

p = argparse.ArgumentParser()
p.add_argument('--owner', help='New owner password')
p.add_argument('--ceo', help='New CEO/agent-view password')
args = p.parse_args()
if not args.owner and not args.ceo:
    p.error('Provide --owner and/or --ceo')
init_db()
if args.owner:
    set_setting('owner_password', hash_password(args.owner))
    print('Owner password reset.')
if args.ceo:
    set_setting('agent_view_password', hash_password(args.ceo))
    print('CEO/agent-view password reset.')
try:
    audit('password_reset_script', 'Passwords reset via scripts/reset_passwords.py', 'system', None)
except Exception:
    pass
