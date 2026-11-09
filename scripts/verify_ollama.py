import json, sys, urllib.request
URL='http://localhost:11434/api/tags'
MODEL='qwen2.5-coder:3b'
try:
    with urllib.request.urlopen(URL, timeout=5) as r:
        data=json.load(r)
except Exception as e:
    print(f'FAIL Ollama unreachable: {e}')
    sys.exit(1)
models=[m.get('name') for m in data.get('models',[])]
print('OK Ollama reachable')
print('Models:', ', '.join(models) or '(none)')
print(f'Model {MODEL}:', 'present' if MODEL in models else 'MISSING')
sys.exit(0 if MODEL in models else 2)
