#!/usr/bin/env python3
"""Book Downloader — Gutenberg + LibGen unified CLI + email delivery.
2026-06-07: Added LibGen session download, email with correct EPUB MIME, unified verify.
"""
import json, os, sys, re, time, socket, zipfile, argparse, smtplib
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote, urlencode
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from email.header import Header

# ── Config ──────────────────────────────────────────
GUTENBERG_SEARCH = "https://www.gutenberg.org/ebooks/search/"
GUTENBERG_DOWNLOAD = "https://www.gutenberg.org/ebooks/{id}.epub.noimages"
LIBGEN_SEARCH = "https://libgen.li/index.php"
LIBGEN_ADS = "https://libgen.li/ads.php"

# ── Configuration loader ─────────────────────────────
def _find_config():
    """Find config.yaml: script dir's parent, then cwd, then ~/.book-toolchain/."""
    candidates = [
        Path(__file__).resolve().parent.parent / "config.yaml",
        Path.cwd() / "config.yaml",
        Path.home() / ".book-toolchain" / "config.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

def load_config():
    """Load config.yaml. Returns dict, or None + prints first-run guidance."""
    config_path = _find_config()
    if not config_path:
        print("⚠️  未找到 config.yaml")
        print()
        print("   这是首次运行吗？请执行：")
        print("   1. cp config.example.yaml config.yaml")
        print("   2. 编辑 config.yaml，至少填写 llm.api_key 和 paths.books_dir")
        print("   3. 重新运行")
        print()
        print("   也可放 config.yaml 到 ~/.book-toolchain/ 作为全局默认。")
        return None
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        print("⚠️  需要 PyYAML：pip install pyyaml")
        return None
    except Exception as e:
        print(f"⚠️  读取 config.yaml 失败: {e}")
        return None

def _get_books_dir(config=None):
    """Resolve books_dir from config, env, or default ~/TaskOS/books."""
    if config:
        d = config.get("paths", {}).get("books_dir", "")
        if d:
            return os.path.expanduser(d)
    env_dir = os.environ.get("BOOK_TOOLCHAIN_BOOKS_DIR", "")
    if env_dir:
        return os.path.expanduser(env_dir)
    return os.path.expanduser("~/TaskOS/books")

# Lazy-loaded config cache
_CONFIG = None
def _config():
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_config()
    return _CONFIG

# ── HTTP helpers ─────────────────────────────────────
def _http_get(url, timeout=15):
    """HTTP GET with retry (2 retries, exponential backoff: 1s → 2s)."""
    last_error = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "book-downloader/2.0"})
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (URLError, HTTPError, socket.timeout) as e:
            last_error = e
            if attempt < 2:
                time.sleep(1 * (2 ** attempt))  # 1s, 2s
    raise last_error

def _requests_session():
    """Lazy-import requests (only needed for libgen)."""
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    return s

# ── EPUB validation ──────────────────────────────────
def _validate_epub(filepath):
    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            files = zf.namelist()
            return 'mimetype' in files and 'META-INF/container.xml' in files and any('.opf' in f for f in files)
    except (zipfile.BadZipFile, OSError):
        return False

def verify_epub(filepath):
    """Detailed EPUB quality report with metadata extraction."""
    try:
        size_kb = os.path.getsize(filepath) / 1024
        with zipfile.ZipFile(filepath, 'r') as zf:
            files = zf.namelist()
            text_files = [f for f in files if f.endswith(('.html', '.xhtml'))]
            img_files = [f for f in files if any(f.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg'])]

            opf_file = next((f for f in files if f.endswith('.opf')), None)
            title = creator = publisher = "N/A"
            if opf_file:
                opf = zf.read(opf_file).decode('utf-8', errors='replace')
                m = re.search(r'<dc:title[^>]*>(.*?)</dc:title>', opf)
                if m: title = m.group(1).strip()
                m = re.search(r'<dc:creator[^>]*>(.*?)</dc:creator>', opf)
                if m: creator = m.group(1).strip()
                m = re.search(r'<dc:publisher[^>]*>(.*?)</dc:publisher>', opf)
                if m: publisher = m.group(1).strip()

            # Content sample
            samples = []
            for f in sorted(text_files, key=lambda x: -zf.getinfo(x).file_size)[:3]:
                content = zf.read(f).decode('utf-8', errors='replace')
                text = re.sub(r'<[^>]+>', '', content)
                text = re.sub(r'\s+', ' ', text).strip()
                samples.append({"file": f, "chars": len(text), "preview": text[:120]})

            return {
                "valid": True, "size_kb": round(size_kb, 1),
                "files": len(files), "chapters": len(text_files), "images": len(img_files),
                "title": title[:100], "author": creator[:60], "publisher": publisher[:60],
                "samples": samples
            }
    except Exception as e:
        return {"valid": False, "error": str(e)[:200]}

# ── Gutenberg ────────────────────────────────────────
def search_gutenberg(query, limit=10):
    params = urlencode({"query": query, "format": "json"})
    url = f"{GUTENBERG_SEARCH}?{params}"
    try:
        data = json.loads(_http_get(url))
    except Exception:
        return []
    if not isinstance(data, list) or len(data) < 4:
        return []

    results = []
    titles = data[1][1:1+limit]
    authors = data[2][1:1+limit] if len(data) > 2 else [None]*len(titles)
    paths = data[3][1:1+limit] if len(data) > 3 else [None]*len(titles)

    for i, title in enumerate(titles):
        if not title: continue
        ebook_id = paths[i].split("/")[-1].replace(".json", "") if paths and paths[i] else None
        results.append({"id": ebook_id, "title": title, "author": authors[i] if authors and authors[i] else "Unknown", "source": "gutenberg"})
    return results

def download_gutenberg(ebook_id, outdir=None, show_progress=True):
    if outdir is None:
        outdir = _get_books_dir(_config())
    url = GUTENBERG_DOWNLOAD.format(id=ebook_id)
    os.makedirs(outdir, exist_ok=True)
    filepath = os.path.join(outdir, f"{ebook_id}.epub")
    if show_progress: print(f"  Downloading: {url}")
    try:
        data = _http_get(url, timeout=60)
    except Exception as e:
        if show_progress: print(f"  ❌ Download failed: {e}")
        return None, 0, False
    with open(filepath, "wb") as f: f.write(data)
    valid = _validate_epub(filepath)
    if show_progress: print(f"  Saved: {filepath} ({len(data)/1024:.0f}KB) {'✅' if valid else '⚠️'}")
    return filepath, len(data), valid

# ── LibGen ───────────────────────────────────────────
def search_libgen(query, limit=10):
    """Search libgen.li. Returns [{title, author, publisher, year, ext, size, md5, source}]."""
    s = _requests_session()
    try:
        resp = s.get(LIBGEN_SEARCH, params={"req": query, "res": min(limit, 25), "view": "detailed"}, timeout=15)
    except Exception:
        return []
    if resp.status_code != 200:
        return []

    results = []
    # Parse the HTML table
    rows = re.findall(r'<tr[^>]*>.*?</tr>', resp.text, re.DOTALL)
    for row in rows:
        if 'columnheader' in row: continue
        # Match the cells — libgen.li uses a specific table structure
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
        if len(cells) < 8: continue
        # cells[0]: ID+title, cells[2]: publisher, cells[3]: year, cells[4]: lang, cells[5]: pages, cells[6]: size, cells[7]: ext
        # Extract md5 from the first cell
        md5_match = re.search(r'md5=([a-f0-9]{32})', row)
        if not md5_match: continue
        md5 = md5_match.group(1)
        title_match = re.search(r'<a[^>]*>([^<]+)</a>', cells[0])
        title = title_match.group(1).strip() if title_match else "N/A"
        # Clean HTML tags from other cells
        publisher = re.sub(r'<[^>]+>', '', cells[2]).strip() if len(cells) > 2 else ""
        year = re.sub(r'<[^>]+>', '', cells[3]).strip() if len(cells) > 3 else ""
        ext = re.sub(r'<[^>]+>', '', cells[7]).strip() if len(cells) > 7 else ""
        size_str = re.sub(r'<[^>]+>', '', cells[6]).strip() if len(cells) > 6 else ""

        results.append({
            "md5": md5, "title": title, "publisher": publisher,
            "year": year, "ext": ext, "size": size_str, "source": "libgen"
        })
    return results[:limit]

def download_libgen(md5, outdir=None, show_progress=True):
    """Download from libgen.li using requests session (required for cookie/key exchange)."""
    if outdir is None:
        outdir = _get_books_dir(_config())
    s = _requests_session()
    os.makedirs(outdir, exist_ok=True)

    # Step 1: Get ads.php to obtain session and download key
    if show_progress: print(f"  Fetching libgen.li session (md5={md5[:8]}...)")
    try:
        r1 = s.get(f"{LIBGEN_ADS}?md5={md5}", timeout=15)
    except Exception as e:
        if show_progress: print(f"  ❌ LibGen session fetch failed: {e}")
        return None, 0, False
    key_match = re.search(r'get\.php\?md5=' + md5 + r'&key=([A-Z0-9]+)', r1.text)
    if not key_match:
        return None, 0, False
    key = key_match.group(1)

    # Step 2: Download actual file
    get_url = f"https://libgen.li/get.php?md5={md5}&key={key}"
    if show_progress: print(f"  Downloading: libgen.li/get.php?...")
    try:
        r2 = s.get(get_url, timeout=60)
    except Exception as e:
        if show_progress: print(f"  ❌ LibGen download failed: {e}")
        return None, 0, False

    if 'text/html' in r2.headers.get('Content-Type', ''):
        if show_progress: print(f"  ❌ libgen returned HTML (likely anti-bot), size={len(r2.content)}")
        return None, 0, False

    # Determine extension
    content_type = r2.headers.get('Content-Type', '')
    if 'epub' in content_type:
        ext = 'epub'
    elif 'pdf' in content_type:
        ext = 'pdf'
    else:
        # Check magic bytes
        if r2.content[:4] == b'PK\x03\x04':
            ext = 'epub'
        elif r2.content[:4] == b'%PDF':
            ext = 'pdf'
        elif r2.content[:4] == b'RIFF':
            ext = 'mobi'
        else:
            ext = 'bin'

    filepath = os.path.join(outdir, f"{md5}.{ext}")
    with open(filepath, "wb") as f: f.write(r2.content)

    valid = _validate_epub(filepath) if ext == 'epub' else (ext == 'pdf')
    if show_progress: print(f"  Saved: {filepath} ({len(r2.content)/1024:.0f}KB) {'✅' if valid else '⚠️'}")
    return filepath, len(r2.content), valid

# ── Email ────────────────────────────────────────────
_SENTINEL = object()

def send_epub_email(filepath, recipient, smtp_password, sender=None,
                    subject=None, body_extra="", smtp_host=None, smtp_port=None, smtp_ssl=_SENTINEL):
    """Send EPUB as email attachment with correct MIME type (application/epub+zip)."""
    cfg = _config()
    if not smtp_password:
        smtp_password = cfg.get("email", {}).get("smtp_password", "") if cfg else ""
        if not smtp_password:
            smtp_password = os.environ.get("SMTP_PASSWORD", os.environ.get("HORIZON_EMAIL_PASSWORD", ""))
    if not sender:
        sender = cfg.get("email", {}).get("smtp_sender", "") if cfg else ""
    if not smtp_host:
        smtp_host = (cfg.get("email", {}).get("smtp_host", "smtp.qq.com") if cfg else "smtp.qq.com")
    if not smtp_port:
        smtp_port = (cfg.get("email", {}).get("smtp_port", 465) if cfg else 465)
    if smtp_ssl is _SENTINEL:
        smtp_ssl = (cfg.get("email", {}).get("smtp_ssl", True) if cfg else True)

    if not smtp_password:
        return {"error": "No SMTP password provided (set SMTP_PASSWORD env var or config.yaml → email.smtp_password)"}
    if not sender:
        return {"error": "No SMTP sender configured (set config.yaml → email.smtp_sender)"}

    fpath = Path(filepath)
    if not fpath.exists():
        return {"error": f"File not found: {filepath}"}

    book_name = fpath.stem
    if not subject:
        subject = Header(f"{book_name} (EPUB)", "utf-8")

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject

    body = f"书籍附件：{book_name}\n格式：EPUB\n{body_extra}\n"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with open(fpath, "rb") as f:
        part = MIMEBase("application", "epub+zip")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        # RFC 2231 encoding for Chinese filenames — prevents .bin rename
        safe_name = f"{book_name}.epub"
        part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", safe_name))
        part.replace_header("Content-Type", "application/epub+zip")
        msg.attach(part)

    try:
        if smtp_ssl:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(sender, smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.starttls()
                server.login(sender, smtp_password)
                server.send_message(msg)
        return {"success": True, "file": str(fpath), "size_kb": round(fpath.stat().st_size/1024, 1)}
    except Exception as e:
        return {"error": str(e)[:200]}

# ── Unified search+download ──────────────────────────
def search_and_download(query, source="gutenberg", outdir=None, limit=5):
    if outdir is None:
        outdir = _get_books_dir(_config())
    results = []
    if source == "gutenberg":
        results = search_gutenberg(query, limit=limit)
        downloads = []
        for r in results:
            if r.get("id"):
                fp, size, valid = download_gutenberg(r["id"], outdir, show_progress=True)
                quality = verify_epub(fp) if valid else {"valid": False}
                downloads.append({**r, "filepath": fp, "size_kb": round(size/1024, 1), "quality": quality})
        return {"query": query, "source": source, "results": results, "downloads": downloads}
    elif source == "libgen":
        results = search_libgen(query, limit=limit)
        downloads = []
        for r in results:
            if r.get("md5"):
                fp, size, valid = download_libgen(r["md5"], outdir, show_progress=True)
                quality = verify_epub(fp) if valid else {"valid": False}
                downloads.append({**r, "filepath": fp, "size_kb": round(size/1024, 1) if fp else 0, "quality": quality})
        return {"query": query, "source": source, "results": results, "downloads": downloads}
    return {"error": f"Unknown source: {source}"}

# ── CLI ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Book Downloader — Gutenberg + LibGen + email")
    sub = parser.add_subparsers(dest="action")

    p_search = sub.add_parser("search", help="Search books")
    p_search.add_argument("query")
    p_search.add_argument("-s", "--source", default="gutenberg", choices=["gutenberg", "libgen"])
    p_search.add_argument("-n", "--limit", type=int, default=5)
    p_search.add_argument("-j", "--json", action="store_true")

    p_get = sub.add_parser("get", help="Search and download first result")
    p_get.add_argument("query")
    p_get.add_argument("-s", "--source", default="gutenberg", choices=["gutenberg", "libgen"])
    p_get.add_argument("-o", "--outdir", default=None)
    p_get.add_argument("-n", "--limit", type=int, default=3)
    p_get.add_argument("-j", "--json", action="store_true")

    p_dl = sub.add_parser("download", help="Download by Gutenberg ID or LibGen MD5")
    p_dl.add_argument("id_or_md5", help="Gutenberg ebook ID or LibGen MD5 hash")
    p_dl.add_argument("-s", "--source", default="gutenberg", choices=["gutenberg", "libgen"])
    p_dl.add_argument("-o", "--outdir", default=None)
    p_dl.add_argument("-j", "--json", action="store_true")

    p_verify = sub.add_parser("verify", help="Verify EPUB file")
    p_verify.add_argument("filepath")

    p_email = sub.add_parser("email", help="Send EPUB via email (SMTP)")
    p_email.add_argument("filepath")
    p_email.add_argument("recipient")
    p_email.add_argument("-p", "--password", default=os.environ.get("SMTP_PASSWORD", os.environ.get("HORIZON_EMAIL_PASSWORD", "")))
    p_email.add_argument("-s", "--subject", default=None)
    p_email.add_argument("-b", "--body", default="")

    args = parser.parse_args()

    if args.action == "search":
        if args.source == "gutenberg":
            results = search_gutenberg(args.query, args.limit)
        else:
            results = search_libgen(args.query, args.limit)

        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for i, r in enumerate(results, 1):
                if r["source"] == "gutenberg":
                    print(f"{i}. [{r['id']}] {r['title']} — {r['author']}")
                else:
                    print(f"{i}. [{r['md5'][:8]}...] {r['title']} | {r['publisher']} | {r['year']} | {r['ext']} | {r['size']}")

    elif args.action == "get":
        result = search_and_download(args.query, args.source, args.outdir, args.limit)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif "error" in result:
            print(f"❌ {result['error']}")

    elif args.action == "download":
        if args.source == "gutenberg":
            fp, size, valid = download_gutenberg(args.id_or_md5, args.outdir)
            if args.json:
                print(json.dumps({"filepath": fp, "size_kb": round(size/1024,1), "valid": valid}))
        else:
            fp, size, valid = download_libgen(args.id_or_md5, args.outdir)
            if args.json and fp:
                print(json.dumps({"filepath": fp, "size_kb": round(size/1024,1), "valid": valid}))

    elif args.action == "verify":
        report = verify_epub(args.filepath)
        print(json.dumps(report, ensure_ascii=False, indent=2))

    elif args.action == "email":
        result = send_epub_email(args.filepath, args.recipient, args.password, subject=args.subject, body_extra=args.body)
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        elif result.get("success"):
            print(f"✅ 已发送: {result['file']} ({result['size_kb']}KB) → {args.recipient}")
        else:
            print(f"❌ {result.get('error', 'Unknown error')}")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
