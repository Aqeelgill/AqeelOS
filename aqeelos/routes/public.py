from flask import Blueprint, g, redirect, send_from_directory
from config import PAGES_DIR

bp = Blueprint("public", __name__)

PAGES = {
    "/": ("index.html", None),
    "/login": ("login.html", None),
    "/register": ("register.html", None),
    "/dashboard": ("ceo.html", ("owner", "ceo")),
    "/ceo": ("ceo.html", ("owner", "ceo")),
    "/departments": ("ceo.html", ("owner", "ceo")),
    "/analytics": ("ceo.html", ("owner", "ceo")),
    "/activity": ("ceo.html", ("owner", "ceo")),
    "/quick-assign": ("ceo.html", ("owner", "ceo")),
    "/owner": ("owner.html", ("owner",)),
    "/settings": ("owner.html", ("owner",)),
    "/client": ("client.html", ("client",)),
    "/privacy": ("privacy.html", None),
    "/terms": ("terms.html", None),
    "/support": ("support.html", None),
}


def _serve(page, roles):
    role = getattr(g, "auth", {}).get("role", "guest")
    if roles and role not in roles:
        # CEO/owner can access client? no; owner can use owner console.
        if "client" in roles:
            return redirect("/login")
        if role == "guest":
            return redirect("/")
        return redirect("/")
    return send_from_directory(PAGES_DIR, page)


@bp.get("/healthz")
def healthz():
    return {"ok": True}


@bp.get("/workspace/<agent_id>")
def workspace(agent_id):
    return send_from_directory(PAGES_DIR, "workspace.html")


for route, (page, roles) in PAGES.items():
    def _make(p, r):
        def view():
            return _serve(p, r)
        view.__name__ = f"page_{route.strip('/').replace('/','_').replace('-','_') or 'root'}"
        return view
    bp.add_url_rule(route, endpoint=f"p_{route.replace('/','_') or 'root'}", view_func=_make(page, roles), methods=["GET"])
