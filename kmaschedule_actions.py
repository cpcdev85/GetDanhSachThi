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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import kma_core as core

VN_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


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
            self.data = {"version": 1, "pdfs": {}, "uploads": {}, "push_notifications": {}}
        else:
            self.sha = item["sha"]
            self.data = json.loads(base64.b64decode(item["content"]))
            if (not isinstance(self.data, dict) or self.data.get("version") != 1
                    or not isinstance(self.data.get("pdfs"), dict)
                    or not isinstance(self.data.get("uploads"), dict)):
                raise ValueError("File ghi nhớ không hợp lệ; dừng để tránh nhập trùng.")
        notifications = self.data.setdefault("push_notifications", {})
        if not isinstance(notifications, dict) or any(
            not isinstance(entry, dict) or entry.get("status") not in ("pending", "sending", "scheduled")
            for entry in notifications.values()
        ):
            raise ValueError("Ghi nhớ thông báo push không hợp lệ; dừng để tránh tạo trùng.")

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


def exam_dates(records):
    """Lấy ngày từ dữ liệu PDF; tuyệt đối không dùng ngày chạy hoặc tên file thay thế."""
    result = set()
    for row in records:
        value = core.clean(row.get("Ngày thi", ""))
        match = re.fullmatch(r"(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})", value)
        try:
            if match:
                day, month, year = map(int, match.groups())
                parsed = date(year, month, day)
            else:
                parsed = date.fromisoformat(value)
        except ValueError:
            raise ValueError("Có ngày thi không hợp lệ trong PDF; chưa tự tạo push. Kiểm tra dữ liệu trên admin.") from None
        result.add(parsed)
    return sorted(result)


def push_content(exam_date):
    weekday = "CN" if exam_date.weekday() == 6 else f"T{exam_date.weekday() + 2}"
    return (f"Đã có SBD, Phòng thi {weekday} ngày {exam_date.strftime('%d/%m/%Y')}. "
            "Vào KMA Schedule kiểm tra nhé.")


def planned_send_time(now=None):
    """Form datetime-local chỉ nhận phút: làm tròn lên sau now + 1 phút."""
    current = now if now is not None else datetime.now(VN_TIMEZONE)
    if current.tzinfo is None:
        raise ValueError("Thời điểm hẹn push cần có múi giờ.")
    target = current.astimezone(VN_TIMEZONE) + timedelta(minutes=1)
    if target.second or target.microsecond:
        target = target.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return target.strftime("%Y-%m-%dT%H:%M")


def queue_push_notifications(records, upload_digest, imported_count, store):
    """Chỉ gọi cho JSON mới vừa có xác nhận nhập thành công."""
    if imported_count <= 0:
        return "Không có dòng mới được xác nhận nhập; chưa tạo push."
    try:
        dates = exam_dates(records)
    except ValueError:
        return "Có ngày thi không hợp lệ; dữ liệu đã nhập nhưng chưa tự tạo push. Kiểm tra admin."
    if imported_count != len(records) and len(dates) > 1:
        return "Website chỉ nhập một phần PDF có nhiều ngày; chưa xác định ngày nào đã nhập đủ để tự tạo push. Kiểm tra admin."
    pending = store.data.setdefault("push_notifications", {})
    for exam_date in dates:
        key = fingerprint((upload_digest + ":" + exam_date.isoformat()).encode("ascii"))
        pending.setdefault(key, {"status": "pending", "exam_date": exam_date.isoformat(),
                                 "upload_digest": upload_digest})
    return ""


def dispatch_pending_push_notifications(store):
    notifications = store.data.setdefault("push_notifications", {})
    uncertain = [key for key, item in notifications.items() if item.get("status") == "sending"]
    pending = [(key, item) for key, item in notifications.items() if item.get("status") == "pending"]
    if uncertain:
        raise ValueError("Thông báo push trước chưa rõ kết quả; kiểm tra mục Thông báo đẩy trên admin. "
                         "Không tự tạo lại. Mã push: " + uncertain[0])
    if not pending:
        return
    # Có thể thử tạo lại push pending ở lượt sau mà không nhập lại JSON thành công.
    try:
        request, _ = core._admin_session({
            "admin_username": os.environ.get("KMA_ADMIN_USERNAME", ""),
            "admin_password": os.environ.get("KMA_ADMIN_PASSWORD", "")})
    except Exception:
        raise AuthenticationFailure("Chưa đăng nhập được để hẹn push; giữ pending, không nhập lại dữ liệu thành công.") from None
    for key, entry in pending:
        try:
            exam_date = date.fromisoformat(entry["exam_date"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Ngày thi trong ghi nhớ push không hợp lệ; chưa tạo thông báo. Mã push: " + key) from None
        # Chỉ thông báo cho một lần nhập đã có xác nhận thành công.
        if store.data["uploads"].get(entry.get("upload_digest"), {}).get("status") != "success":
            raise ValueError("Push chưa gắn với dữ liệu nhập thành công; chưa tạo thông báo. Mã push: " + key)
        page = request(core.ADMIN_PUSH_URL)
        if page.login or not page.token:
            raise ValueError("Chưa xác thực được trang Thông báo đẩy; giữ pending để kiểm tra lại.")
        send_time = planned_send_time()
        body = urllib.parse.urlencode({"action": "save_push", "push_id": "",
                                       "csrf_token": page.token, "push_content": push_content(exam_date),
                                       "send_time": send_time}).encode("utf-8")
        entry.update(status="sending", send_time=send_time,
                     time=datetime.now(timezone.utc).isoformat())
        store.save()  # Nếu lưu thất bại thì không POST tạo thông báo.
        try:
            response = request(core.ADMIN_PUSH_URL, body, "application/x-www-form-urlencoded")
        except Exception:
            raise ValueError("Chưa rõ kết quả tạo push; không tự tạo lại. Kiểm tra admin. Mã push: " + key) from None
        if response.login:
            entry["status"] = "pending"
            store.save()
            raise ValueError("Phiên admin hết hạn trước khi tạo push; giữ pending cho lượt sau.")
        if (response.message("msg-err") or
                "Đã tạo thông báo đẩy thành công." not in response.message("msg-ok")):
            raise ValueError("Chưa có xác nhận tạo push; giữ sending. Kiểm tra admin trước khi thử lại. Mã push: " + key)
        entry.update(status="scheduled", time=datetime.now(timezone.utc).isoformat())
        store.save()
        print(f"Đã hẹn push cho ngày thi {exam_date.strftime('%d/%m/%Y')}, phát lúc {send_time.replace('T', ' ')} (giờ Việt Nam).", flush=True)


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
    push_warning = queue_push_notifications(records, digest, int(match.group(1)), store)
    if push_warning:
        store.data["uploads"][digest]["push_warning"] = push_warning
    store.save()
    print(f"Đã nhập {int(match.group(1))} dòng. Đợt thi lấy theo tên PDF/JSON, không có đuôi file.", flush=True)
    if page.message("msg-warn"):
        print("Website có cảnh báo bỏ qua dòng. Vào admin kiểm tra dữ liệu; không tự tải lại cả file.", flush=True)
    if push_warning:
        print("CẢNH BÁO PUSH: " + push_warning, flush=True)


def run(upload=False, store=None):
    store = store or GitHubState()
    errors = 0
    try:
        article = core.find_latest_article_url(core._fetch_text(core.AUTO_LIST_URL))
        urls = core.find_pdf_urls(core._fetch_text(article), article)
        if not urls:
            raise ValueError("Bài mới nhất chưa có liên kết PDF.")
        print(f"Tìm thấy {len(urls)} PDF trong bài mới nhất. Chế độ: {'TẢI LÊN' if upload else 'XEM THỬ'}.", flush=True)
    except Exception:
        # Dữ liệu đã nhập ở lượt trước vẫn được hẹn push khi trang trường tạm lỗi.
        if upload:
            dispatch_pending_push_notifications(store)
        raise
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
    if upload:
        dispatch_pending_push_notifications(store)
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
