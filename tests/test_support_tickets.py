import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['AQEELOS_DISABLE_WORKER'] = '1'
from app import create_app
from aqeelos.auth import hash_password, set_setting
from aqeelos.db import init_db

class SupportTicketTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config.update(TESTING=True, CSRF_ENABLED=False); init_db()
        set_setting('owner_password', hash_password('AQEEL2026'))
        self.client = self.app.test_client()
        self.client.post('/api/auth/register', json={'name':'Esc','email':'esc@example.com','password':'secret123'})
        if self.client.get('/api/me').get_json().get('role')!='client':
            self.client.post('/api/auth/login', json={'email':'esc@example.com','password':'secret123'})
        self.owner = self.app.test_client()
        self.owner.post('/api/auth/owner', json={'password':'AQEEL2026'})
    def test_owner_can_view_thread_and_respond(self):
        r = self.client.post('/api/support/escalate', json={'subject':'Need human','message':'Please help'})
        self.assertEqual(r.status_code, 200, r.get_json())
        tid = r.get_json()['ticket_id']
        r = self.owner.get(f'/api/support/tickets/{tid}')
        self.assertEqual(r.status_code, 200)
        j = r.get_json(); self.assertTrue(j['messages']); self.assertEqual(j['ticket']['id'], tid)
        r = self.owner.post(f'/api/support/tickets/{tid}/respond', json={'message':'Owner here'})
        self.assertEqual(r.status_code, 200)
        j = self.owner.get(f'/api/support/tickets/{tid}').get_json()
        self.assertTrue(any(m['sender_role']=='owner' and 'Owner here' in m['body'] for m in j['messages']))
        self.assertEqual(j['ticket']['status'], 'answered')
    def test_client_cannot_list_owner_tickets(self):
        self.assertEqual(self.client.get('/api/support/tickets').status_code, 401)

if __name__ == '__main__':
    unittest.main()
