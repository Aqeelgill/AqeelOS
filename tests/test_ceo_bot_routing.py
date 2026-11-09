import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['AQEELOS_DISABLE_WORKER'] = '1'
from app import create_app
from aqeelos.services import ollama_client
from aqeelos.routes import api_chat

class CeoBotRoutingTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config.update(TESTING=True, CSRF_ENABLED=False)
        self.c = self.app.test_client()
        self.c.post('/api/auth/register', json={'name':'Chat User','email':'chatroute2@example.com','password':'secret123'})
        if self.c.get('/api/me').get_json().get('role') != 'client':
            self.c.post('/api/auth/login', json={'email':'chatroute2@example.com','password':'secret123'})
        self.old = ollama_client.generate
    def tearDown(self):
        ollama_client.generate = self.old; api_chat.generate = self.old
    def test_route_requires_confirmation_then_creates_public_task(self):
        def fake(prompt, system=None, model=None, timeout=120):
            return {'ok': True, 'text': 'I can help.\nROUTE:{"agent_id":"frontend","task":"Create a homepage wireframe","confidence":"high"}'}
        ollama_client.generate = fake; api_chat.generate = fake
        r = self.c.post('/api/ceo/chat', json={'message':'I need a homepage'})
        self.assertEqual(r.status_code, 200, r.get_json())
        j = r.get_json()
        self.assertIsNone(j.get('task'))
        self.assertTrue(j.get('pending_route'))
        self.assertEqual(j['pending_route']['agent_id'], 'frontend')
        r = self.c.post('/api/ceo/confirm', json={'conversation_id': j['conversation_id']})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()['task']['agent_id'], 'frontend')
    def test_ignores_internal_route(self):
        def fake(prompt, system=None, model=None, timeout=120):
            return {'ok': True, 'text': 'ROUTE:{"agent_id":"promo_growth","task":"Promote secretly"}'}
        ollama_client.generate = fake; api_chat.generate = fake
        r = self.c.post('/api/ceo/chat', json={'message':'promote'})
        self.assertEqual(r.status_code, 200, r.get_json())
        j = r.get_json(); self.assertIsNone(j.get('task')); self.assertIsNone(j.get('pending_route'))

if __name__ == '__main__':
    unittest.main()
