from __future__ import annotations

import html
import json
import os
from pathlib import Path
from string import Template

from fastapi import FastAPI, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth
import storage
import export as export_mod
import chat as chat_mod

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="Skriveapp")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Eksport-mottakere er låst til en liste du selv setter (komma-separert), slik at en
# som får tak i innloggingen ikke kan sende dokumenter til en vilkårlig adresse.
#   export SKRIVEAPP_EXPORT_EMAILS="meg@example.org,meg@arbeid.example"
ALLOWED_EXPORT_EMAILS = {e.strip() for e in os.environ.get("SKRIVEAPP_EXPORT_EMAILS", "").split(",") if e.strip()}
DEFAULT_EXPORT_EMAIL = next(iter(sorted(ALLOWED_EXPORT_EMAILS)), "")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# Satt til f.eks. "/txt" når appen kjøres bak en reverse-proxy-sti
# (Tailscale Serve --set-path) i stedet for på domenets rot.
BASE_PATH = os.environ.get("SKRIVEAPP_BASE_PATH", "").rstrip("/")


def render(name: str, **kwargs) -> str:
    tpl = Template((TEMPLATES_DIR / name).read_text())
    kwargs.setdefault("BASE", BASE_PATH)
    kwargs.setdefault("BASE_JSON", json.dumps(BASE_PATH))
    return tpl.safe_substitute(**kwargs)


def require_auth(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if not auth.verify_session_token(token):
        raise HTTPException(status_code=401, detail="Ikke innlogget")


@app.get("/manifest.webmanifest")
def manifest():
    data = {
        "name": "Skriveapp",
        "short_name": "Skriveapp",
        "start_url": f"{BASE_PATH}/",
        "scope": f"{BASE_PATH}/",
        "display": "standalone",
        "background_color": "#f4f4f5",
        "theme_color": "#2563eb",
        "icons": [
            {"src": f"{BASE_PATH}/static/favicon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": f"{BASE_PATH}/static/favicon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    return JSONResponse(content=data, media_type="application/manifest+json")


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return render("login.html", ERROR_HTML="")


@app.post("/login")
def login_submit(request: Request, password: str = Form(...)):
    ip = _client_ip(request)
    locked_seconds = auth.is_locked_out(ip)
    if locked_seconds:
        minutes = locked_seconds // 60 + 1
        body = render(
            "login.html",
            ERROR_HTML=f'<div class="error">For mange feilforsøk. Prøv igjen om ca. {minutes} min.</div>',
        )
        return HTMLResponse(content=body, status_code=429)
    if not auth.check_password(password):
        auth.record_failed_attempt(ip)
        body = render("login.html", ERROR_HTML='<div class="error">Feil passord</div>')
        return HTMLResponse(content=body, status_code=401)
    auth.record_success(ip)
    token = auth.make_session_token()
    resp = RedirectResponse(url=f"{BASE_PATH}/", status_code=303)
    resp.set_cookie(
        auth.SESSION_COOKIE, token, max_age=auth.SESSION_MAX_AGE,
        httponly=True, samesite="lax", secure=True,
    )
    return resp


@app.get("/logout")
def logout():
    resp = RedirectResponse(url=f"{BASE_PATH}/login", status_code=303)
    resp.delete_cookie(auth.SESSION_COOKIE)
    return resp


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if not auth.verify_session_token(token):
        return RedirectResponse(url=f"{BASE_PATH}/login")
    docs = storage.list_docs()
    items = _render_doc_items(docs)
    return HTMLResponse(content=render("index.html", DOC_ITEMS=items))


def _render_doc_items(docs: list[dict]) -> str:
    if not docs:
        return '<li style="color:#9ca3af;">Ingen dokumenter funnet.</li>'
    return "\n".join(
        f'<li data-slug="{html.escape(d["slug"])}">'
        f'<a href="{BASE_PATH}/d/{html.escape(d["slug"])}">{html.escape(d["title"])}</a>'
        f'<span class="meta"><span class="updated">{html.escape(d["updated"])}</span>'
        f"<button class=\"delete\" onclick='deleteDoc({json.dumps(d['slug'])}, this)' title=\"Slett dokument\">Slett</button></span>"
        f"</li>"
        for d in docs
    )


@app.get("/d/{slug}", response_class=HTMLResponse)
def doc_page(request: Request, slug: str):
    token = request.cookies.get(auth.SESSION_COOKIE)
    if not auth.verify_session_token(token):
        return RedirectResponse(url=f"{BASE_PATH}/login")
    doc = storage.get_doc(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    title = doc["meta"]["title"]
    return HTMLResponse(content=render(
        "editor.html",
        TITLE=html.escape(title),
        SLUG_JSON=json.dumps(slug),
    ))


# ---- JSON API ----

class CreateDocBody(BaseModel):
    title: str


class SaveContentBody(BaseModel):
    html: str


class CommentBody(BaseModel):
    quote: str
    text: str


class ReplyBody(BaseModel):
    text: str
    author: str = "user"


class ResolveBody(BaseModel):
    resolved: bool = True


class ChatBody(BaseModel):
    message: str


class ExportBody(BaseModel):
    to_email: str | None = None


@app.post("/api/docs", dependencies=[Depends(require_auth)])
def api_create_doc(body: CreateDocBody):
    meta = storage.create_doc(body.title)
    return meta


@app.get("/api/docs", dependencies=[Depends(require_auth)])
def api_list_docs(q: str | None = None):
    return storage.search_docs(q) if q else storage.list_docs()


@app.delete("/api/docs/{slug}", dependencies=[Depends(require_auth)])
def api_delete_doc(slug: str):
    if not storage.delete_doc(slug):
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    return {"ok": True}


@app.get("/api/docs/{slug}", dependencies=[Depends(require_auth)])
def api_get_doc(slug: str):
    doc = storage.get_doc(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    return doc


@app.put("/api/docs/{slug}/content", dependencies=[Depends(require_auth)])
def api_save_content(slug: str, body: SaveContentBody):
    try:
        storage.save_content(slug, body.html)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    return {"ok": True}


@app.post("/api/docs/{slug}/comments", dependencies=[Depends(require_auth)])
def api_add_comment(slug: str, body: CommentBody):
    return storage.add_comment(slug, body.quote, body.text)


@app.post("/api/docs/{slug}/comments/{comment_id}/reply", dependencies=[Depends(require_auth)])
def api_reply_comment(slug: str, comment_id: str, body: ReplyBody):
    c = storage.reply_comment(slug, comment_id, body.author, body.text)
    if c is None:
        raise HTTPException(status_code=404, detail="Fant ikke kommentaren")
    return c


@app.post("/api/docs/{slug}/comments/{comment_id}/resolve", dependencies=[Depends(require_auth)])
def api_resolve_comment(slug: str, comment_id: str, body: ResolveBody):
    c = storage.resolve_comment(slug, comment_id, body.resolved)
    if c is None:
        raise HTTPException(status_code=404, detail="Fant ikke kommentaren")
    return c


@app.post("/api/docs/{slug}/chat", dependencies=[Depends(require_auth)])
def api_chat(slug: str, body: ChatBody):
    doc = storage.get_doc(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    storage.append_chat(slug, "user", body.message)
    open_comments = [c for c in doc["comments"] if not c["resolved"]]
    try:
        reply = chat_mod.send_to_otto(slug, doc["meta"]["title"], doc["content"], open_comments, body.message)
    except chat_mod.ChatError as e:
        reply = f"(Feil ved kontakt med Otto: {e})"
    msg = storage.append_chat(slug, "otto", reply)
    return msg


@app.post("/api/docs/{slug}/export", dependencies=[Depends(require_auth)])
def api_export(slug: str, body: ExportBody):
    doc = storage.get_doc(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    to_email = (body.to_email or DEFAULT_EXPORT_EMAIL).strip().lower()
    if to_email not in ALLOWED_EXPORT_EMAILS:
        raise HTTPException(status_code=400, detail="E-postadresse ikke tillatt")
    try:
        path = export_mod.export_and_send(slug, doc["meta"]["title"], doc["content"], to_email)
    except export_mod.ExportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, "path": path, "sent_to": to_email}


@app.get("/api/docs/{slug}/download.docx", dependencies=[Depends(require_auth)])
def api_download_docx(slug: str):
    doc = storage.get_doc(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    title = doc["meta"]["title"]
    try:
        path = export_mod.html_to_docx(doc["content"], title, export_mod.EXPORT_DIR)
    except export_mod.ExportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.get("/api/docs/{slug}/download.pdf", dependencies=[Depends(require_auth)])
def api_download_pdf(slug: str):
    doc = storage.get_doc(slug)
    if doc is None:
        raise HTTPException(status_code=404, detail="Fant ikke dokumentet")
    title = doc["meta"]["title"]
    try:
        path = export_mod.html_to_pdf(doc["content"], title, export_mod.EXPORT_DIR)
    except export_mod.ExportError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@app.exception_handler(HTTPException)
def auth_redirect_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse(url=f"{BASE_PATH}/login")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
