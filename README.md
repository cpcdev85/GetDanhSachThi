# KMA Schedule — GitHub Actions

Dự án KMA Schedule được phát triển bởi cPcDev.

Bản chạy nền: mỗi 5 phút kiểm tra bài danh sách thi mới nhất của trường, đọc PDF, chuyển nội dung thành JSON và nhập vào trang admin. Không cần bật máy tính cá nhân. Không có giao diện, không cần Tesseract; bản này chỉ đọc PDF có chữ/bảng, chưa OCR PDF scan.

## 1. Tải bộ mã lên repository

Giải nén bộ ZIP. Đưa các file/thư mục bên trong lên thư mục gốc repository, không đưa cả thư mục bao ngoài và không chỉ tải file ZIP lên GitHub:

| Đường dẫn | Công dụng |
|---|---|
| `kmaschedule_actions.py` | Một lượt kiểm tra và tải danh sách lên |
| `kma_core.py` | Đọc PDF, đăng nhập và xử lý CSRF |
| `requirements.txt` | Thư viện Python |
| `.github/workflows/check.yml` | Lịch chạy và nút chạy thủ công |
| `.gitignore` | Loại file tạm khỏi git |
| `README.md` | Hướng dẫn này |

Trên GitHub: **Code → Add file → Upload files**, kéo các file và thư mục vào rồi **Commit changes** trên nhánh mặc định (thường là main).

Nếu thư mục `.github` không tải lên được: dùng **Add file → Create new file**, nhập chính xác `.github/workflows/check.yml`, mở file check.yml trong ZIP, sao chép toàn bộ nội dung, rồi Commit changes.

Không cần tải file desktop `.pyw`, hai file PHP hoặc các file cài đặt có mật khẩu lên GitHub.

## 2. Secrets (thêm URL admin)

**Settings → Secrets and variables → Actions → Secrets**:

- `KMA_ADMIN_BASE_URL`: URL thư mục admin hiện tại trên web của bạn. Chỉ nhập đến thư mục admin, bỏ `/login`, `/home`, `/lichthi` và mọi phần `?redirect=...` phía sau. Không ghi giá trị này vào mã nguồn hoặc README.
- `KMA_ADMIN_USERNAME`: tên đăng nhập admin.
- `KMA_ADMIN_PASSWORD`: mật khẩu admin.

Không cần tạo Personal Access Token. Workflow dùng GITHUB_TOKEN tự động của GitHub để lưu lịch sử.

## 3. Kiểm tra quyền lưu lịch sử

Workflow khai báo `permissions: contents: write` để ghi file `json/github_state.json`.

Nếu bước chạy báo HTTP 403 khi lưu trạng thái: vào **Settings → Actions → General → Workflow permissions**, cho phép **Read and write permissions**, rồi Save. Chính sách của organization hoặc bảo vệ nhánh có thể chặn thao tác này; khi đó phải cho phép bot ghi file trạng thái trên nhánh mặc định. Tool sẽ không tải lên admin nếu chưa lưu được trạng thái trước khi gửi.

## 4. Chạy thử trước

1. Mở **Actions** → **KMA Schedule Auto**.
2. Nếu GitHub hỏi bật Actions, chọn bật.
3. Nhấn **Run workflow**.
4. Chọn nhánh mặc định và `mode = preview`.
5. Nhấn nút Run workflow màu xanh.
6. Mở lượt chạy → job **check** → bước **Check PDFs and upload new JSON** để xem log.

Chế độ preview đọc PDF và đếm bản ghi, không đăng nhập admin, không tải lên, không đánh dấu đã xử lý. Log không in danh sách sinh viên.

Nếu không thấy workflow: kiểm tra đường dẫn `.github/workflows/check.yml` và chắc chắn file nằm trên nhánh mặc định.

## 5. Tải lên một lần thủ công

Sau khi preview đúng, chạy lại **Run workflow**, chọn `mode = upload`.

Tool dùng hai Secrets để đăng nhập, lấy cookie/CSRF, gửi form `dsthi_upload` với `mode=append`. Chỉ thêm vào danh sách hiện có; không xóa dữ liệu cũ. Tên đợt thi lấy theo tên PDF/JSON, bỏ đuôi file.

**Lần đầu trên GitHub chưa biết lịch sử tải lên từ bản desktop.** Nếu danh sách của bài mới nhất đã được nhập lên web bằng desktop/thủ công thì không chọn upload ngay: có thể nhập trùng. Đối chiếu dữ liệu trên admin trước. Không chạy bản desktop tự tải lên song song với bản GitHub vì hai bản không dùng chung lịch sử.

Nếu PDF thay đổi, JSON mới có thể gồm cả dòng cũ; vì website nhập thêm nên vẫn có khả năng trùng các dòng cũ. Chống trùng của bản này áp dụng cho cả file, không phải cập nhật từng sinh viên.

## 6. Bật tự động tải lên

Sau khi kiểm tra kết quả thủ công:

1. **Settings → Secrets and variables → Actions → Variables**.
2. Nhấn **New repository variable**.
3. Name: `KMA_ENABLE_UPLOAD`.
4. Value: `true` (viết thường).
5. Lưu.

Từ các lượt chạy theo lịch tiếp theo, tool sẽ tự tải JSON mới lên admin. Không cần mở máy tính hoặc giữ trình duyệt.

Khi biến chưa có hoặc khác `true`, các lượt theo lịch chỉ xem thử. Chạy thủ công `preview` luôn chỉ xem thử; `upload` luôn tải lên; `auto` theo biến này.

## 7. Chu kỳ kiểm tra

Mặc định 5 phút/lần trong `.github/workflows/check.yml`:

```yaml
- cron: '3-59/5 * * * *'
```

Tức các phút 03, 08, 13, 18... 58 mỗi giờ. Muốn đổi thành 10 phút/lần thì dùng `3-59/10 * * * *`.

GitHub không có lịch chuẩn 1 hoặc 3 phút/lần. Lịch có thể bị trễ, không cam kết đúng từng phút. Chu kỳ dưới đây không phải một tiến trình chạy suốt ngày: GitHub tạo lượt chạy, kiểm tra xong thì kết thúc.

## 8. Lịch sử chống trùng

Khi có thay đổi, tool tự ghi `json/github_state.json` trên nhánh mặc định bằng GitHub API. File chỉ có mã SHA-256, trạng thái và thời gian, không có tài khoản/mật khẩu, tên sinh viên, MSV hay nội dung PDF/JSON.

- PDF đã xử lý: bỏ qua.
- JSON đã được web xác nhận thành công: không nhập lại.
- Trước khi gửi POST: phải ghi trạng thái `sending` lên GitHub thành công.
- Sau khi web xác nhận: đổi sang `success`.
- Nếu mất mạng/tắt lượt chạy sau POST: giữ `sending`, chặn tự gửi lại để tránh trùng.
- Lỗi trước khi gửi lên web: lượt sau có thể thử lại.

Không dùng cache làm nguồn lịch sử chính. Không xóa file trạng thái vì tool sẽ quên lịch sử. Các file PDF và dữ liệu sinh viên chỉ nằm tạm trong máy chạy của GitHub; không được commit hoặc upload artifact.

### Xử lý trạng thái chưa rõ kết quả

Log in ra mã JSON 64 ký tự. Trước hết vào **Settings → Secrets and variables → Actions → Variables**, đổi `KMA_ENABLE_UPLOAD` thành `false` và chờ lượt đang chạy kết thúc.

Kiểm tra danh sách trên web:

- Nếu dữ liệu đã nhập đủ: trong `json/github_state.json`, tìm mã JSON trong mục `uploads`, đổi `"status":"sending"` thành `"status":"success"`.
- Nếu chắc chắn dữ liệu chưa được nhập: đổi thành `"status":"failed"` để cho phép gửi lại.
- Nếu chỉ nhập một phần hoặc không chắc chắn: không đổi trạng thái; đối chiếu/khắc phục trên admin trước.

Commit file rồi bật lại biến `KMA_ENABLE_UPLOAD=true`. Không sửa phần mã băm và không chỉnh file khi lượt khác còn đang chạy.

## 9. Tắt hoặc tiếp tục

- Chỉ tắt nhập dữ liệu nhưng vẫn kiểm tra: đổi `KMA_ENABLE_UPLOAD=false`.
- Dừng toàn bộ lịch: **Actions → KMA Schedule Auto → dấu ba chấm → Disable workflow**.
- Bật lại: chọn Enable workflow.

## 10. Giới hạn và chi phí

- Dùng repository Public và `ubuntu-latest` tiêu chuẩn để hưởng thời gian chạy miễn phí theo chính sách GitHub. Không chọn larger runner.
- Repository Private của GitHub Free có hạn mức phút chạy; kiểm tra thường xuyên có thể hết hạn mức.
- Repository công khai có thể bị tắt lịch sau 60 ngày không có hoạt động. Thỉnh thoảng kiểm tra Actions.
- Mỗi lượt có giới hạn 20 phút; nếu chưa xử lý hết thì lượt sau tiếp tục dựa vào lịch sử.
- Chỉ lấy bài đầu tiên/mới nhất, không quét toàn bộ bài cũ, không lọc bài theo ngày hiện tại.
- PDF tối đa 30MB; JSON nhập tối đa 10MB và 50.000 dòng theo giới hạn của trang admin.
- Không thay đổi login.php hoặc lichthi.php. Website vẫn tự kiểm tra dữ liệu và có thể bỏ dòng lỗi; nếu có cảnh báo, vào admin đối chiếu.

Tài liệu chính thức:

- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- https://docs.github.com/en/rest/repos/contents

## Bản cập nhật: giấu URL admin

Thay mã nguồn cũ bằng bộ này, giữ nguyên `json/github_state.json` đã được tool tạo trên GitHub. Thêm Secret `KMA_ADMIN_BASE_URL` cùng nơi bạn lưu username/password. Lịch mặc định là 5 phút/lần.

URL admin không xuất hiện trong mã nguồn mới, dữ liệu trạng thái hoặc log do tool chủ động ghi. Workflow chỉ tham chiếu tên Secret. Đăng nhập vẫn dùng HTTPS, cookie và CSRF như cũ.

Nếu đã public bản cũ, xóa URL trong file hiện tại không xóa URL trong lịch sử commit. Muốn đường dẫn cũ không còn truy cập được, cần đổi đường dẫn admin thực tế trên hosting và cập nhật Secret; việc đó chưa được bộ mã này thực hiện. Đường dẫn ẩn không thay thế cơ chế đăng nhập/kiểm tra quyền trên website.
