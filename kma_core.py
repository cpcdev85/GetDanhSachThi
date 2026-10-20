"""Đọc PDF và đăng nhập admin; giữ logic trích xuất của bản desktop."""
import http.cookiejar
import html as html_lib
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
import pdfplumber

AUTO_LIST_URL = "https://ktdbcl.actvn.edu.vn/khao-thi/to-chuc-thi/danh-sach-thi.html"
AUTO_USER_AGENT = "Mozilla/5.0 (KMASchedule GitHub Actions)"
# URL được nạp từ GitHub Secret khi cần đăng nhập; không ghi vào log/git.
ADMIN_ORIGIN = ""
ADMIN_LOGIN_URL = ""
ADMIN_LIST_URL = ""
ADMIN_REDIRECT_PATH = ""


def _configure_admin_urls():
    global ADMIN_ORIGIN, ADMIN_LOGIN_URL, ADMIN_LIST_URL, ADMIN_REDIRECT_PATH
    value = os.environ.get("KMA_ADMIN_BASE_URL", "").strip().rstrip("/")
    if not value:
        raise ValueError("Thiếu Secret KMA_ADMIN_BASE_URL (URL thư mục admin).")
    if len(value) > 2048 or re.search(r"[\x00-\x20\x7f\\]", value):
        raise ValueError("Secret URL admin không hợp lệ.")
    parsed = urllib.parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Secret URL admin không hợp lệ.") from None
    if (parsed.scheme != "https" or parsed.hostname != "kmaschedule.io.vn"
            or parsed.username or parsed.password or port not in (None, 443)
            or parsed.query or parsed.fragment
            or not re.fullmatch(r"/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", parsed.path)
            or any(part in (".", "..") for part in parsed.path.split("/"))):
        raise ValueError("URL admin cần là HTTPS trên website KMA Schedule, chỉ đến thư mục admin, không kèm login, query hoặc fragment.")
    if parsed.path.rsplit("/", 1)[-1].lower() in ("login", "login.php", "lichthi", "lichthi.php", "home", "home.php"):
        raise ValueError("Hãy nhập URL thư mục admin, bỏ phần trang login/lichthi/home phía sau.")
    ADMIN_ORIGIN = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    ADMIN_LOGIN_URL = ADMIN_ORIGIN + parsed.path + "/login"
    ADMIN_REDIRECT_PATH = parsed.path + "/lichthi?tab=dsthi"
    ADMIN_LIST_URL = ADMIN_ORIGIN + ADMIN_REDIRECT_PATH

STUDENT_FIELDS = ("Môn thi", "SBD", "MSV", "Họ và tên", "Lần thi", "Ngày thi", "Ca thi", "Phòng")
STUDENT_HEADERS = ("SBD", "Mã HVSV", "Họ đệm", "Tên", "Lần thi", "Ngày thi", "Ca thi", "Phòng")

class _AdminHTML(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.token = ""
        self.login = False
        self.messages = {"msg-ok": [], "msg-err": [], "msg-warn": [], "err": []}
        self.capture = None
        self.depth = 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input":
            if attrs.get("name") == "csrf_token":
                self.token = attrs.get("value", "")
            if attrs.get("name") == "admin_password":
                self.login = True
        if tag == "div":
            if self.capture:
                self.depth += 1
            else:
                for name in attrs.get("class", "").split():
                    if name in self.messages:
                        self.capture, self.depth = name, 1
                        break

    def handle_endtag(self, tag):
        if tag == "div" and self.capture:
            self.depth -= 1
            if self.depth == 0:
                self.capture = None

    def handle_data(self, data):
        if self.capture:
            self.messages[self.capture].append(data)

    def message(self, name):
        return " ".join(" ".join(self.messages[name]).split())[:2000]


class _AdminRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        origin = urllib.parse.urlsplit(ADMIN_ORIGIN)
        if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
            raise ValueError("Đã chặn chuyển hướng ra ngoài website KMA Schedule.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _admin_session(settings):
    _configure_admin_urls()
    username = settings.get("admin_username", "").strip()
    password = settings.get("admin_password", "")
    if not username or not password:
        raise ValueError("Thiếu Secrets KMA_ADMIN_USERNAME hoặc KMA_ADMIN_PASSWORD.")
    if len(username.encode("utf-8")) > 1024 or len(password.encode("utf-8")) > 1024:
        raise ValueError("Tài khoản hoặc mật khẩu vượt giới hạn của website.")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), _AdminRedirect())
    opener.addheaders = [("User-Agent", AUTO_USER_AGENT)]

    def request(url, data=None, content_type=None):
        headers = {"Referer": ADMIN_LIST_URL, "Origin": ADMIN_ORIGIN}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=data, headers=headers)
        with opener.open(req, timeout=60) as response:
            return _AdminHTML(response.read().decode("utf-8", errors="replace"))

    page = request(ADMIN_LOGIN_URL + "?" + urllib.parse.urlencode({"redirect": ADMIN_REDIRECT_PATH}))
    if not page.token:
        raise ValueError("Không tìm thấy CSRF trang đăng nhập; hãy kiểm tra website.")
    body = urllib.parse.urlencode({"admin_username": username, "admin_password": password,
                                  "csrf_token": page.token,
                                  "redirect": ADMIN_REDIRECT_PATH}).encode("utf-8")
    page = request(ADMIN_LOGIN_URL, body, "application/x-www-form-urlencoded")
    if page.login or page.message("err"):
        raise ValueError(page.message("err") or "Đăng nhập admin thất bại.")
    page = request(ADMIN_LIST_URL)
    if page.login or not page.token:
        raise ValueError("Chưa xác thực được quyền truy cập danh sách thi.")
    return request, page.token


def clean(value):
    return " ".join(str(value or "").split())


def extract_students(pdf_path):
    """Trang nối tiếp dùng tên môn gần nhất; cho phép ca thi để trống."""
    students = []
    subject = None
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            match = re.search(r"^\s*Môn thi\s*:\s*(.+)$", page.extract_text() or "",
                              re.MULTILINE | re.IGNORECASE)
            if match:
                subject = clean(match.group(1))
            elif subject is None:
                raise ValueError(f"Trang {page_number}: không tìm thấy tên môn thi ở trang này hoặc trang trước")

            for table in page.extract_tables():
                if not table:
                    continue
                header = [clean(cell) for cell in table[0]]
                if "STT" not in header or not all(name in header for name in STUDENT_HEADERS):
                    continue
                index = {name: header.index(name) for name in (*STUDENT_HEADERS, "STT")}
                for row in table[1:]:
                    if not row or index["STT"] >= len(row) or not clean(row[index["STT"]]).isdigit():
                        continue

                    def cell(name):
                        position = index[name]
                        return clean(row[position]) if position < len(row) else ""

                    if not cell("Mã HVSV") or any(
                        not cell(field) for field in ("SBD", "Ngày thi", "Phòng")
                    ):
                        continue
                    students.append({
                        "Môn thi": subject,
                        "SBD": cell("SBD"),
                        "MSV": cell("Mã HVSV"),
                        "Họ và tên": clean(f'{cell("Họ đệm")} {cell("Tên")}'),
                        "Lần thi": cell("Lần thi"),
                        "Ngày thi": cell("Ngày thi"),
                        "Ca thi": cell("Ca thi"),
                        "Phòng": cell("Phòng"),
                    })
    if not students:
        raise ValueError("Không tìm thấy thí sinh có đủ thông tin dự thi trong PDF")
    return students


def _http_request(url, method="GET", timeout=30):
    # Địa chỉ có ký tự Unicode/khoảng trắng cần được mã hóa trước khi gửi.
    parts = urllib.parse.urlsplit(url)
    safe_url = urllib.parse.urlunsplit((
        parts.scheme, parts.netloc,
        urllib.parse.quote(parts.path, safe="/%:@+,;=~"),
        parts.query, "",
    ))
    request = urllib.request.Request(safe_url, method=method, headers={"User-Agent": AUTO_USER_AGENT})
    return urllib.request.urlopen(request, timeout=timeout)


def _fetch_text(url):
    with _http_request(url) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def find_latest_article_url(list_html, base_url=AUTO_LIST_URL):
    """Lấy bài viết đầu tiên trong bảng danh sách (Joomla xếp mới nhất lên đầu)."""
    pattern = re.compile(
        r'href\s*=\s*["\']([^"\']*/danh-sach-thi/\d+-[^"\']*?\.html)["\']', re.IGNORECASE
    )
    match = pattern.search(list_html)
    if not match:
        raise ValueError("Không tìm thấy bài viết danh sách thi nào trên trang web")
    return urllib.parse.urljoin(base_url, html_lib.unescape(match.group(1)))


def find_pdf_urls(article_html, base_url):
    """Lấy mọi link .pdf trong bài viết, giữ thứ tự và bỏ trùng."""
    urls = []
    for href in re.findall(r'href\s*=\s*["\']([^"\']+?\.pdf)(?:\?[^"\']*)?["\']', article_html, re.IGNORECASE):
        full = urllib.parse.urljoin(base_url, html_lib.unescape(href))
        if full not in urls:
            urls.append(full)
    return urls


def _pdf_file_stem(pdf_url):
    name = urllib.parse.unquote(os.path.basename(urllib.parse.urlsplit(pdf_url).path))
    stem = os.path.splitext(name)[0]
    stem = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip(" .")
    return stem or "danh-sach-thi"
