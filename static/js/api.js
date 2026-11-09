const API = {
  _csrf: null,
  async csrf() {
    if (this._csrf) return this._csrf;
    try { const d = await fetch('/api/csrf', {credentials:'same-origin'}).then(r=>r.json()); this._csrf = d.csrf_token; } catch(e) {}
    return this._csrf;
  },
  async req(path, opts={}) {
    const method = (opts.method || 'GET').toUpperCase();
    const headers = {'Content-Type':'application/json', ...(opts.headers||{})};
    if (!['GET','HEAD','OPTIONS'].includes(method)) {
      const tok = opts.csrf === false ? null : await this.csrf();
      if (tok) headers['X-CSRF-Token'] = tok;
    }
    const res = await fetch(path, {credentials:'same-origin', headers, ...opts});
    const hdrTok = res.headers.get('X-CSRF-Token'); if (hdrTok) this._csrf = hdrTok;
    const data = await res.json().catch(()=>({}));
    if (!res.ok) throw Object.assign(new Error(data.error || 'Request failed'), {status:res.status, data});
    return data;
  },
  get:(p,opts={})=>API.req(p,opts), post:(p,b,opts={})=>API.req(p,{method:'POST',body:JSON.stringify(b||{}),...opts}),
};
const UI = {
  esc(s){return String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');},
  fmt(iso){if(!iso)return '—';const d=new Date(iso);return isNaN(d)?String(iso).replace('T',' ').slice(0,19):d.toLocaleString();},
  themeInit(){const t=localStorage.getItem('aqeelos_theme')||'dark';document.documentElement.dataset.theme=t;return t;},
  toggleTheme(){const n=(document.documentElement.dataset.theme==='dark')?'light':'dark';document.documentElement.dataset.theme=n;localStorage.setItem('aqeelos_theme',n);return n;},
  qs:(s,r=document)=>r.querySelector(s), qsa:(s,r=document)=>[...r.querySelectorAll(s)],
};
UI.themeInit();
