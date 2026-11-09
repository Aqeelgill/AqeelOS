from pathlib import Path
from config import OUTPUTS_DIR


def _safe_name(name):
    return ''.join(c for c in (name or 'artifact') if c.isalnum() or c in ('-','_','.'))[:120] or 'artifact'


def render_text(task_id, text):
    out = OUTPUTS_DIR / str(task_id)
    out.mkdir(parents=True, exist_ok=True)
    p = out / 'output.txt'
    p.write_text(text or '', encoding='utf-8')
    return str(p), 'text/plain', p.name


def render_pdf(task_id, title, text):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except Exception as e:
        return None, None, None, str(e)
    out = OUTPUTS_DIR / str(task_id)
    out.mkdir(parents=True, exist_ok=True)
    name = _safe_name(f'task-{task_id}.pdf')
    p = out / name
    c = canvas.Canvas(str(p), pagesize=A4)
    w, h = A4
    y = h - 40
    c.setFont('Helvetica-Bold', 14); c.drawString(40, y, (title or f'Task {task_id}')[:90]); y -= 24
    c.setFont('Helvetica', 10)
    for raw in (text or '').splitlines() or ['']:
        line = raw.replace('\t', '  ')[:140]
        if y < 50:
            c.showPage(); c.setFont('Helvetica', 10); y = h - 40
        c.drawString(40, y, line); y -= 14
    c.save()
    return str(p), 'application/pdf', name, None


def render_thumbnail(task_id, text):
    try:
        from PIL import Image, ImageDraw
    except Exception as e:
        return None, None, None, str(e)
    out = OUTPUTS_DIR / str(task_id)
    out.mkdir(parents=True, exist_ok=True)
    name = _safe_name(f'task-{task_id}-preview.png')
    p = out / name
    img = Image.new('RGB', (1200, 630), (26, 26, 46))
    d = ImageDraw.Draw(img)
    y = 24
    for line in (text or 'AqeelOS Output').splitlines()[:18]:
        d.text((24, y), line[:110], fill=(248,250,252))
        y += 30
    img.save(p)
    return str(p), 'image/png', name, None
