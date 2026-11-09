import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['AQEELOS_DISABLE_WORKER'] = '1'
from app import create_app
from aqeelos.auth import hash_password, set_setting
from aqeelos.db import init_db

class Phase4Test(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config.update(TESTING=True, CSRF_ENABLED=False); init_db()
        set_setting('owner_password', hash_password('AQEEL2026'))
        self.client = self.app.test_client()
        self.client.post('/api/auth/register', json={'name':'P4','email':'phase4@example.com','password':'secret123'})
        if self.client.get('/api/me').get_json().get('role')!='client':
            self.client.post('/api/auth/login', json={'email':'phase4@example.com','password':'secret123'})
        self.owner = self.app.test_client(); self.owner.post('/api/auth/owner', json={'password':'AQEEL2026'})
    def test_client_can_view_own_ticket_thread_and_reply(self):
        r = self.client.post('/api/support/escalate', json={'subject':'Help','message':'Need assistance'})
        tid = r.get_json()['ticket_id']
        r = self.client.get('/api/support/my-tickets')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(t['id']==tid for t in r.get_json()['tickets']))
        r = self.client.get(f'/api/support/my-tickets/{tid}')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()['messages'])
        r = self.client.post(f'/api/support/my-tickets/{tid}/reply', json={'message':'More details'})
        self.assertEqual(r.status_code, 200)
        j = self.owner.get(f'/api/support/tickets/{tid}').get_json()
        self.assertTrue(any('More details' in m['body'] for m in j['messages']))
    def test_client_cannot_view_other_ticket(self):
        c2 = self.app.test_client(); c2.post('/api/auth/register', json={'name':'O','email':'otherp4@example.com','password':'secret123'})
        r = c2.post('/api/support/escalate', json={'subject':'Other','message':'x'})
        tid = r.get_json()['ticket_id']
        self.assertEqual(self.client.get(f'/api/support/my-tickets/{tid}').status_code, 404)

if __name__ == '__main__':
    unittest.main()
