import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['AQEELOS_DISABLE_WORKER'] = '1'
from app import create_app
from aqeelos.auth import hash_password, set_setting
from aqeelos.db import init_db

class OwnerControlTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config.update(TESTING=True, CSRF_ENABLED=False)
        init_db(); set_setting('owner_password', hash_password('AQEEL2026')); set_setting('execution_state','paused'); set_setting('task_pickup_enabled','0')
        self.owner = self.app.test_client(); self.owner.post('/api/auth/owner', json={'password':'AQEEL2026'})
        self.client = self.app.test_client(); self.client.post('/api/auth/register', json={'name':'OC','email':'oc@example.com','password':'secret123'})
        if self.client.get('/api/me').get_json().get('role')!='client':
            self.client.post('/api/auth/login', json={'email':'oc@example.com','password':'secret123'})

    def test_owner_control_requires_owner_role(self):
        self.assertEqual(self.client.get('/api/owner/control').status_code, 401)
        self.assertEqual(self.owner.get('/api/owner/control').status_code, 200)
        j = self.owner.get('/api/owner/control').get_json()
        for k in ('status','agents','queue','users','tickets','audit_log','artifacts','history','errors','ceo_conversations'):
            self.assertIn(k, j)

    def test_pause_resume_and_task_cancel(self):
        r = self.owner.post('/api/owner/control/resume', json={}); self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()['status']['paused'])
        r = self.owner.post('/api/tasks', json={'agent_id':'frontend','task':'control test task'})
        self.assertEqual(r.status_code, 201)
        tid = r.get_json()['task']['id']
        r = self.owner.post('/api/owner/control/tasks/'+str(tid)+'/cancel', json={})
        self.assertEqual(r.status_code, 200)
        t = self.owner.get('/api/tasks/'+str(tid)).get_json()['task']
        self.assertEqual(t['status'], 'cancelled')
        r = self.owner.post('/api/owner/control/pause', json={'reason':'test'})
        self.assertTrue(r.get_json()['status']['paused'])

if __name__ == '__main__':
    unittest.main()
