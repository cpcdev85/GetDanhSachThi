"""Một lượt kiểm tra KMA Schedule trên GitHub Actions. Không lưu dữ liệu sinh viên vào git."""
import base64
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import kma_core as core


def fingerprint(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class AuthenticationFailure(ValueError):
    pass


class GitHubState:
    """Chỉ lưu mã băm, trạng thái và thời gian; ghi bền TRƯỚC POST tới admin."""
    def __init__(self):
        self.repo = os.environ.get("GITHUB_REPOSITORY", "")
        self.token = os.environ.get("GH_STATE_TOKEN", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repo) or not self.token:
            raise ValueError("Thiếu GITHUB_REPOSITORY hoặc quyền GITHUB_TOKEN.")
        meta = self.api("GET", "")
        self.branch = meta["default_branch"]
        self.path = "/contents/json/github_state.json"
        self.sha = None
        try:
            item = self.api("GET", self.path + "?" + urllib.parse.urlencode({"ref": self.branch}))
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            self.data = {"version": 1, "pdfs": {}, "uploads": {}}
        else:
            self.sha = item["sha"]
            self.data = json.loads(base64.b64decode(item["content"]))
            if (not isinstance(self.data, dict) or self.data.get("version") != 1
                    or not isinstance(self.data.get("pdfs"), dict)
                    or not isinstance(self.data.get("uploads"), dict)):
                raise ValueError("File ghi nhớ không hợp lệ; dừng để tránh nhập trùng.")

    def api(self, method, suffix, payload=None):
        headers = {"Authorization": "Bearer " + self.token,
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "KMASchedule-Actions"}
        body = None if payload is None else json_bytes(payload)
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request("https://api.github.com/repos/" + self.repo + suffix,
                                         data=body, method=method, headers=headers)
        # GitHub API chỉ nhận URL cố định; token không được gửi tới website trường/admin.
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)

    def save(self):
        payload = {"message": "Update KMA processing state [skip ci]", "branch": self.branch,
                   "content": base64.b64encode(json_bytes(self.data)).decode("ascii")}
        if self.sha:
            payload["sha"] = self.sha
        # Không tự retry PUT: kết quả không rõ phải dừng, không gửi dữ liệu lên admin.
        result = self.api("PUT", self.path, payload)
        self.sha = result["content"]["sha"]


def upload_records(records, batch, request, token):
    raw = json_bytes(records)
    if not records or len(records) > 50000 or len(raw) > 10 * 1024 * 1024:
        raise ValueError("JSON rỗng hoặc vượt giới hạn 50.000 dòng / 10MB.")
    boundary = "----KMA" + secrets.token_hex(24)
    fields = {"action": "dsthi_upload", "csrf_token": token, "mode": "append", "dot_thi": batch[:150]}
    parts = [(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n').encode()
             for key, value in fields.items()]
    parts.extend([(f'--{boundary}\r\nContent-Disposition: form-data; name="json_file"; filename="danhsachthi.json"\r\nContent-Type: application/json\r\n\r\n').encode(),
                  raw, f"\r\n--{boundary}--\r\n".encode()])
    return request(core.ADMIN_LIST_URL, b"".join(parts), "multipart/form-data; boundary=" + boundary)


def publish(records, batch, pdf_hash, store):
    digest = fingerprint(json_bytes(records))
    entry = store.data["uploads"].get(digest, {})
    status = entry.get("status")
    if status == "success":
        store.data["pdfs"][pdf_hash] = digest
        store.save()
        print("JSON đã được nhập trước đó: bỏ qua.", flush=True)
        return
    if status == "sending":
        raise ValueError("Lần tải trước chưa rõ kết quả. Kiểm tra web và xử lý trạng thái theo README. Mã JSON: " + digest)
    # Bắt buộc xác thực xong trước khi đánh dấu sending.
    try:
        request, token = core._admin_session({
            "admin_username": os.environ.get("KMA_ADMIN_USERNAME", ""),
            "admin_password": os.environ.get("KMA_ADMIN_PASSWORD", "")})
    except Exception:
        raise AuthenticationFailure("Không đăng nhập được admin. Kiểm tra Secrets, mạng hoặc giới hạn đăng nhập; dừng lượt để tránh thử sai liên tục.") from None
    store.data["uploads"][digest] = {"status": "sending", "time": datetime.now(timezone.utc).isoformat()}
    store.save()  # Nếu không ghi được lên GitHub thì KHÔNG gửi POST tới website.
    try:
        page = upload_records(records, batch, request, token)
    except Exception:
        raise ValueError("Chưa rõ kết quả tải lên. Không tự gửi lại; kiểm tra web. Mã JSON: " + digest) from None
    if page.login:
        store.data["uploads"][digest]["status"] = "failed"
        store.save()
        raise ValueError("Phiên admin không hợp lệ; kiểm tra Secrets.")
    if page.message("msg-err"):
        # Không in HTML/thông tin sinh viên hoặc toàn bộ thông báo server vào log công khai.
        # Giữ sending vì một thông báo lỗi khác trên trang có thể xuất hiện sau khi đã nhập.
        raise ValueError("Website báo lỗi; kiểm tra trang admin trước khi thử lại. Mã JSON: " + digest)
    match = re.search(r"Đã nhập thành công (\d+) dòng vào danh sách thi", page.message("msg-ok"))
    if not match:
        raise ValueError("Không thấy xác nhận nhập thành công; kiểm tra web. Mã JSON: " + digest)
    store.data["uploads"][digest]["status"] = "success"
    store.data["pdfs"][pdf_hash] = digest
    store.save()
    print(f"Đã nhập {int(match.group(1))} dòng. Đợt thi lấy theo tên PDF/JSON, không có đuôi file.", flush=True)
    if page.message("msg-warn"):
        print("Website có cảnh báo bỏ qua dòng. Vào admin kiểm tra dữ liệu; không tự tải lại cả file.", flush=True)


def run(upload=False, store=None):
    store = store or GitHubState()
    article = core.find_latest_article_url(core._fetch_text(core.AUTO_LIST_URL))
    urls = core.find_pdf_urls(core._fetch_text(article), article)
    if not urls:
        raise ValueError("Bài mới nhất chưa có liên kết PDF.")
    print(f"Tìm thấy {len(urls)} PDF trong bài mới nhất. Chế độ: {'TẢI LÊN' if upload else 'XEM THỬ'}.", flush=True)
    errors = 0
    for index, url in enumerate(urls, 1):
        try:
            with core._http_request(url, timeout=90) as response:
                content = response.read(30 * 1024 * 1024 + 1)
            if len(content) > 30 * 1024 * 1024 or b"%PDF-" not in content[:1024]:
                raise ValueError("File không phải PDF hoặc lớn hơn 30MB.")
            pdf_hash = fingerprint(content)
            if pdf_hash in store.data["pdfs"]:
                print(f"PDF {index}: đã xử lý; bỏ qua.", flush=True)
                continue
            with tempfile.TemporaryDirectory(prefix="kma-") as temp:
                path = Path(temp) / "source.pdf"
                path.write_bytes(content)
                records = core.extract_students(str(path))
            # Tên JSON = tên PDF; nhãn đợt thi = tên này bỏ đuôi.
            batch = core._pdf_file_stem(url)
            print(f"PDF {index}: {len(records)} dòng; mã JSON {fingerprint(json_bytes(records))}.", flush=True)
            if upload:
                publish(records, batch, pdf_hash, store)
            else:
                print("Xem thử: không đăng nhập, không tải lên, không đánh dấu đã xử lý.", flush=True)
        except AuthenticationFailure:
            raise
        except Exception as exc:
            errors += 1
            # Tránh đưa URL hoặc dữ liệu từ thư viện PDF vào log công khai.
            if isinstance(exc, urllib.error.HTTPError):
                reason = f"HTTP {exc.code}; kiểm tra mạng/quyền truy cập."
            elif isinstance(exc, ValueError):
                reason = str(exc)
            else:
                reason = type(exc).__name__ + "; kiểm tra kết nối hoặc cấu trúc PDF."
            print(f"PDF {index}: LỖI: {reason}", flush=True)
    if errors:
        raise ValueError(f"Có {errors} PDF chưa hoàn tất. Xem log phía trên.")
    print("Hoàn tất lượt kiểm tra.", flush=True)


if __name__ == "__main__":
    try:
        mode = os.environ.get("KMA_MODE", "preview")
        enabled = os.environ.get("KMA_ENABLE_UPLOAD", "false").lower() == "true"
        if mode not in ("preview", "upload", "auto"):
            raise ValueError("Chế độ không hợp lệ.")
        run(upload=(mode == "upload" or mode == "auto" and enabled))
    except Exception as exc:
        # Không in traceback có chứa request/secret.
        if isinstance(exc, urllib.error.HTTPError):
            print(f"LỖI HTTP {exc.code}: kiểm tra quyền Actions và kết nối.", flush=True)
        elif isinstance(exc, ValueError):
            print("LỖI: " + str(exc), flush=True)
        else:
            print("LỖI: " + type(exc).__name__ + ". Kiểm tra mạng và file ghi nhớ.", flush=True)
        sys.exit(1)
