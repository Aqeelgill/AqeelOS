import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['AQEELOS_DISABLE_WORKER'] = '1'
from app import create_app
from aqeelos.auth import hash_password, set_setting
from aqeelos.db import init_db

class SecurityTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config.update(TESTING=True, CSRF_ENABLED=True)
        self.c = self.app.test_client(); init_db()
        set_setting('owner_password', hash_password('AQEEL2026'))
    def test_csrf_blocks_state_change_without_token(self):
        self.c.post('/api/auth/owner', json={'password':'AQEEL2026'})
        tok = self.c.get('/api/csrf').get_json()['csrf_token']
        r = self.c.post('/api/tasks', json={'agent_id':'frontend','task':'x'})
        self.assertEqual(r.status_code, 403)
        r = self.c.post('/api/tasks', json={'agent_id':'frontend','task':'x'}, headers={'X-CSRF-Token': tok})
        self.assertEqual(r.status_code, 201)
    def test_input_validation(self):
        r = self.c.post('/api/auth/register', json={'name':'','email':'bad','password':'1'})
        self.assertEqual(r.status_code, 400)

if __name__ == '__main__':
    unittest.main()
