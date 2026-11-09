import os, sys, unittest
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['AQEELOS_DISABLE_WORKER'] = '1'
from app import create_app
from aqeelos.auth import hash_password, set_setting
from aqeelos.db import db_exec, init_db, now_iso
from aqeelos.services.output_renderer import render_pdf, render_text, render_thumbnail

class OutputTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app(); self.app.config.update(TESTING=True, CSRF_ENABLED=False)
        self.c = self.app.test_client(); init_db()
        set_setting('owner_password', hash_password('AQEEL2026'))
    def _login(self, client, name, email, pw='secret123'):
        r = client.post('/api/auth/register', json={'name':name,'email':email,'password':pw})
        if r.status_code == 409:
            client.post('/api/auth/login', json={'email':email,'password':pw})
    def test_renderers_create_files(self):
        p,m,n = render_text(888001,'hello')
        self.assertTrue(Path(p).exists())
        p,m,n,e = render_pdf(888001,'T','body'); self.assertTrue(p and Path(p).exists(), e)
        p,m,n,e = render_thumbnail(888001,'thumb'); self.assertTrue(p and Path(p).exists(), e)
    def test_client_cannot_download_other_artifact(self):
        c1 = self.app.test_client(); self._login(c1,'A','a-out@example.com')
        c2 = self.app.test_client(); self._login(c2,'B','b-out@example.com')
        u1 = db_exec("SELECT id FROM users WHERE email='a-out@example.com'", fetch=True, one=True)['id']
        tid = db_exec("INSERT INTO tasks(agent_id,department_id,task,status,created_at,client_id,source,updated_at) VALUES (?,?,?,?,?,?,?,?)",
                      ('frontend','development','x','completed',now_iso(),u1,'test',now_iso()), commit=True)
        p,m,n = render_text(tid,'private output')
        aid = db_exec("INSERT INTO artifacts(task_id,client_id,kind,filename,path,mime_type,created_at) VALUES (?,?,?,?,?,?,?)",
                      (tid,u1,'text',n,p,m,now_iso()), commit=True)
        self.assertEqual(c2.get(f'/api/artifacts/{aid}/download').status_code, 404)

if __name__ == '__main__':
    unittest.main()
