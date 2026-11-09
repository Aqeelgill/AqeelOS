import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['AQEELOS_DISABLE_WORKER'] = '1'
from app import create_app
from aqeelos.auth import hash_password, set_setting
from aqeelos.db import init_db

class TaskFlowTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config.update(TESTING=True, CSRF_ENABLED=False)
        self.c = self.app.test_client(); init_db()
        set_setting('owner_password', hash_password('AQEEL2026'))
    def test_owner_can_queue_task_and_client_cannot_use_internal_agent(self):
        r = self.c.post('/api/auth/owner', json={'password':'AQEEL2026'})
        self.assertEqual(r.status_code, 200)
        r = self.c.post('/api/tasks', json={'agent_id':'frontend','task':'Build a landing page hero section'})
        self.assertEqual(r.status_code, 201)
        tid = r.get_json()['task']['id']
        r = self.c.get(f'/api/tasks/{tid}')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()['task']['status'], 'queued')
        c2 = self.app.test_client()
        c2.post('/api/auth/register', json={'name':'Task User','email':'taskuser@example.com','password':'secret123'})
        r = c2.post('/api/tasks', json={'agent_id':'promo_growth','task':'secret'})
        self.assertEqual(r.status_code, 400)

if __name__ == '__main__':
    unittest.main()
