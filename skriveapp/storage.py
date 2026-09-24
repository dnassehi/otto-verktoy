"""Lagring av dokumenter for skriveappen. Hvert dokument er en mappe under
docs/<slug>/ (innhold, kommentarer, chat), git-versjonert i docs/ som eget
lokalt repo - samme mønster som reisevaksinasjon-repoet."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent / "docs"


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "dokument"


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)


def ensure_repo() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    if not (DOCS_DIR / ".git").exists():
        _git(["init"], DOCS_DIR)
        _git(["config", "user.email", "agent@example.org"], DOCS_DIR)
        _git(["config", "user.name", "Otto"], DOCS_DIR)


def _commit(message: str) -> None:
    _git(["add", "-A"], DOCS_DIR)
    _git(["commit", "-m", message], DOCS_DIR)


def _doc_path(slug: str) -> Path:
    return DOCS_DIR / slug


def list_docs() -> list[dict]:
    ensure_repo()
    out = []
    for p in sorted(DOCS_DIR.iterdir()):
        meta_path = p / "meta.json"
        if p.is_dir() and meta_path.exists():
            meta = json.loads(meta_path.read_text())
            out.append(meta)
    out.sort(key=lambda m: m.get("updated", ""), reverse=True)
    return out


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def search_docs(query: str) -> list[dict]:
    """Søk i tittel OG selve dokumentinnholdet (ikke bare tittelen), siden
    poenget med søk er å finne igjen gamle dokumenter man ikke husker
    tittelen på lenger."""
    query = query.strip().lower()
    if not query:
        return list_docs()
    out = []
    for meta in list_docs():
        p = _doc_path(meta["slug"])
        if query in meta["title"].lower():
            out.append(meta)
            continue
        content = (p / "content.html").read_text()
        if query in _strip_html(content).lower():
            out.append(meta)
    return out


def delete_doc(slug: str) -> bool:
    p = _doc_path(slug)
    if not p.exists():
        return False
    title = json.loads((p / "meta.json").read_text()).get("title", slug)
    shutil.rmtree(p)
    _commit(f"Slettet dokument: {title}")
    return True


def create_doc(title: str) -> dict:
    ensure_repo()
    base_slug = _slugify(title)
    slug = base_slug
    i = 2
    while _doc_path(slug).exists():
        slug = f"{base_slug}-{i}"
        i += 1
    p = _doc_path(slug)
    p.mkdir(parents=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta = {"slug": slug, "title": title, "created": now, "updated": now}
    (p / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    (p / "content.html").write_text(f"<p>{title}</p>")
    (p / "comments.json").write_text("[]")
    (p / "chat.json").write_text("[]")
    _commit(f"Nytt dokument: {title}")
    return meta


def get_doc(slug: str) -> dict | None:
    p = _doc_path(slug)
    meta_path = p / "meta.json"
    if not meta_path.exists():
        return None
    return {
        "meta": json.loads(meta_path.read_text()),
        "content": (p / "content.html").read_text(),
        "comments": json.loads((p / "comments.json").read_text()),
        "chat": json.loads((p / "chat.json").read_text()),
    }


def save_content(slug: str, html: str) -> None:
    p = _doc_path(slug)
    if not p.exists():
        raise FileNotFoundError(slug)
    (p / "content.html").write_text(html)
    meta_path = p / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    _commit(f"Autolagring: {meta['title']}")


def add_comment(slug: str, quote: str, text: str) -> dict:
    p = _doc_path(slug)
    comments_path = p / "comments.json"
    comments = json.loads(comments_path.read_text())
    comment = {
        "id": str(uuid.uuid4())[:8],
        "quote": quote[:300],
        "resolved": False,
        "thread": [{"author": "user", "text": text, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}],
    }
    comments.append(comment)
    comments_path.write_text(json.dumps(comments, ensure_ascii=False, indent=2))
    _commit("Ny kommentar")
    return comment


def reply_comment(slug: str, comment_id: str, author: str, text: str) -> dict | None:
    p = _doc_path(slug)
    comments_path = p / "comments.json"
    comments = json.loads(comments_path.read_text())
    for c in comments:
        if c["id"] == comment_id:
            c["thread"].append({"author": author, "text": text, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")})
            comments_path.write_text(json.dumps(comments, ensure_ascii=False, indent=2))
            _commit("Kommentarsvar")
            return c
    return None


def resolve_comment(slug: str, comment_id: str, resolved: bool) -> dict | None:
    p = _doc_path(slug)
    comments_path = p / "comments.json"
    comments = json.loads(comments_path.read_text())
    for c in comments:
        if c["id"] == comment_id:
            c["resolved"] = resolved
            comments_path.write_text(json.dumps(comments, ensure_ascii=False, indent=2))
            _commit("Kommentar løst/gjenåpnet")
            return c
    return None


def append_chat(slug: str, role: str, text: str) -> dict:
    p = _doc_path(slug)
    chat_path = p / "chat.json"
    chat = json.loads(chat_path.read_text())
    msg = {"role": role, "text": text, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
    chat.append(msg)
    chat_path.write_text(json.dumps(chat, ensure_ascii=False, indent=2))
    _commit(f"Chat ({role})")
    return msg
