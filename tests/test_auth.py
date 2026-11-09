import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import app

class AuthTest(unittest.TestCase):
    def test_owner_invalid_password(self):
        r = app.test_client().post('/api/auth/owner', json={'password':'definitely-wrong'})
        self.assertEqual(r.status_code, 401)
    def test_health(self):
        self.assertEqual(app.test_client().get('/api/health').status_code, 200)

if __name__ == '__main__':
    unittest.main()
