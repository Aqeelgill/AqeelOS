import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app

class VisibilityTest(unittest.TestCase):
    def setUp(self):
        self.c = app.test_client()
    def test_guest_no_internal_agents(self):
        j = self.c.get('/api/status').get_json()
        self.assertTrue(all(a.get('visibility') != 'internal' for a in j.get('agents', {}).values()))
    def test_client_cannot_get_internal_agent(self):
        r = self.c.post('/api/auth/register', json={'name':'VT','email':'vt@example.com','password':'secret123'})
        if r.status_code not in (200,201,409):
            self.skipTest('register unavailable')
        c = app.test_client()
        c.post('/api/auth/login', json={'email':'vt@example.com','password':'secret123'})
        self.assertEqual(c.get('/api/agents/promo_growth').status_code, 404)

if __name__ == '__main__':
    unittest.main()
