# KMA Schedule - Hướng dẫn thiết lập GitHub Actions + cron hosting

Dự án KMA Schedule được phát triển bởi cPcDev.

Bản hướng dẫn này sử dụng cách đã thiết lập thành công: **cron trên hosting gọi GitHub Actions**, còn GitHub xử lý PDF và nhập danh sách thi lên website. Không cần bật máy tính cá nhân. Hosting không cần cài Python.

## 1. Cách hoạt động

Cứ 5 phút, hosting gọi API GitHub để kích hoạt workflow `check.yml` trên nhánh `main` với chế độ `auto`. Workflow thực hiện:

1. Đọc bài đầu tiên/mới nhất trên trang danh sách thi của trường.
2. Lấy các PDF được liên kết trong bài đó.
3. Tải PDF, so sánh mã SHA-256 với lịch sử.
4. Đọc bảng danh sách thi và chuyển thành dữ liệu JSON trong bộ nhớ.
5. Nếu chưa nhập trước đó, đăng nhập admin bằng cookie và CSRF rồi tải JSON lên.
6. Ghi trạng thái vào `json/github_state.json` để lần sau không nhập lại.
7. Kết thúc lượt chạy; chờ cron hosting gọi lượt tiếp theo.

Bản này đọc **PDF có chữ/bảng**, chưa OCR PDF scan hoặc ảnh. Không quét toàn bộ bài cũ và không chỉ lọc bài đăng trong ngày. Trang nguồn:

https://ktdbcl.actvn.edu.vn/khao-thi/to-chuc-thi/danh-sach-thi.html

## 2. Những thứ cần có

- Tài khoản GitHub.
- Repository chứa bộ mã; trong ví dụ là `cpcdev85/GetDanhSachThi`, nhánh mặc định `main`.
- Hosting có Cron Jobs, lệnh `curl` và được phép gọi HTTPS tới `api.github.com`.
- URL thư mục admin, tài khoản và mật khẩu admin của website KMA Schedule.

**GitHub và hosting dùng hai loại thông tin xác thực khác nhau:**

| Thông tin | Đặt ở đâu? | Dùng làm gì? |
|---|---|---|
| URL admin, username, password | GitHub Repository Secrets | Tool đăng nhập và nhập dữ liệu lên website |
| Personal access token của GitHub | Lệnh cron trong trang quản lý hosting | Hosting kích hoạt GitHub Actions |
| `GITHUB_TOKEN` | GitHub tự cấp cho từng lượt chạy | Tool ghi lịch sử chống trùng vào repository |

Không đưa mật khẩu hoặc personal access token vào file mã nguồn, README hoặc file JSON trong repository.

## 3. Tạo repository và tải bộ mã

1. Đăng nhập https://github.com.
2. Chọn **New repository**.
3. Đặt tên, ví dụ `GetDanhSachThi`.
4. Chọn **Public** nếu muốn hưởng thời gian chạy miễn phí trên runner tiêu chuẩn theo chính sách GitHub.
5. Có thể chọn tạo README rồi nhấn **Create repository**.
6. Giải nén bộ ZIP, đưa các file/thư mục bên trong lên **thư mục gốc** của repository bằng **Code → Add file → Upload files**.
7. **Commit changes** vào nhánh mặc định, trong hướng dẫn này là `main`.

| Đường dẫn | Vai trò |
|---|---|
| `kmaschedule_actions.py` | Một lượt theo dõi và nhập dữ liệu |
| `kma_core.py` | Đọc PDF, đăng nhập admin, lấy CSRF |
| `requirements.txt` | Thư viện Python cần cài |
| `.github/workflows/check.yml` | Cấu hình GitHub Actions |
| `.gitignore` | Bỏ qua một số file tạm |
| `README.md` | Hướng dẫn này |
| `json/github_state.json` | Tool tự tạo khi nhập dữ liệu; không tạo rỗng thủ công |

Không chỉ tải nguyên file ZIP lên GitHub. Không đặt toàn bộ mã trong một thư mục bao ngoài. Không cần tải `.pyw`, `login.php` hoặc `lichthi.php` lên repository.

Nếu `.github` chưa được tải lên: **Add file → Create new file**, nhập `.github/workflows/check.yml`, dán nội dung file tương ứng trong ZIP rồi Commit changes.

Nếu đổi tên tài khoản/repository hoặc dùng nhánh khác `main`, phải cập nhật URL API và `ref` trong lệnh cron ở phần 8.

## 4. Cấu hình ba Secrets của website

Vào **repository → Settings → Secrets and variables → Actions → Secrets → New repository secret**. Đây là Settings của repository, không phải Settings cá nhân.

Tạo đủ ba mục:

| Name | Giá trị Secret |
|---|---|
| `KMA_ADMIN_BASE_URL` | URL tới thư mục admin, không có `/login`, `/home`, `/lichthi` hoặc phần `?…` |
| `KMA_ADMIN_USERNAME` | Tài khoản admin |
| `KMA_ADMIN_PASSWORD` | Mật khẩu admin |

Ví dụ giả định để xác định URL thư mục admin:

```text
Trang đăng nhập:
https://kmaschedule.io.vn/thu-muc-admin-rieng/login?redirect=/thu-muc-admin-rieng/home

KMA_ADMIN_BASE_URL:
https://kmaschedule.io.vn/thu-muc-admin-rieng
```

Thay bằng đường dẫn thực tế của bạn. Không thêm dấu nháy quanh giá trị Secret. Bản mã hiện tại chỉ nhận URL HTTPS trên tên miền `kmaschedule.io.vn`.

Khi đổi đường dẫn admin thực tế trên hosting, cập nhật Secret này. Thay Secret không tự đổi đường dẫn website. Nếu đường dẫn cũ từng xuất hiện trong commit công khai thì xóa khỏi file hiện tại không xóa nó khỏi lịch sử Git.

## 5. Cấu hình biến bật/tắt nhập dữ liệu

Vào **Settings → Secrets and variables → Actions → Variables → New repository variable**:

| Name | Value |
|---|---|
| `KMA_ENABLE_UPLOAD` | Ban đầu đặt `false`; sau khi kiểm tra thành công đổi thành `true` |

Phải là tab **Variables**, khác với ba mục ở tab Secrets phía trên.

| Chế độ workflow | Hành vi |
|---|---|
| `preview` | Đọc PDF, đếm dòng; không đăng nhập, không tải lên, không ghi đã xử lý |
| `upload` | Thực hiện nhập dữ liệu dù biến bật/tắt đang là gì |
| `auto` | Chỉ nhập khi `KMA_ENABLE_UPLOAD=true`; nếu không thì xem thử |

Lệnh cron ở phần 8 dùng `auto`. Đổi `KMA_ENABLE_UPLOAD=false` chỉ tắt nhập dữ liệu, không ngăn cron tạo lượt chạy.

## 6. Chạy thử thủ công

1. Vào **Actions → KMA Schedule Auto**.
2. Nếu có yêu cầu bật Actions, chọn bật.
3. Nhấn **Run workflow**.
4. Chọn nhánh `main`, chế độ `preview`, rồi Run workflow.
5. Mở lượt chạy → job **check** → bước **Check PDFs and upload new JSON**.

Log thành công có dạng:

```text
Tìm thấy 1 PDF trong bài mới nhất. Chế độ: XEM THỬ.
PDF 1: ... dòng; mã JSON ...
Xem thử: không đăng nhập, không tải lên, không đánh dấu đã xử lý.
Hoàn tất lượt kiểm tra.
```

Dấu xanh cho biết lượt chạy không báo lỗi. Số dòng là số bản ghi trích xuất được, không tự chứng minh mọi trường dữ liệu đều chính xác.

Sau khi đối chiếu đúng và chắc chắn danh sách chưa có trên website, chạy chế độ `upload`. Xem log xác nhận đã nhập bao nhiêu dòng và kiểm tra danh sách trên web. Sau đó đặt `KMA_ENABLE_UPLOAD=true`.

**Lần đầu GitHub không biết những danh sách đã nhập bằng desktop hoặc thủ công.** Không chạy upload nếu dữ liệu đã có mà chưa có lịch sử tương ứng. Không chạy bản desktop tự tải lên song song vì hai bản không dùng chung lịch sử.

## 7. Cấu hình workflow để dùng cron hosting

Trong quá trình thiết lập này, lịch `schedule` của GitHub không tạo lượt chạy dù cấu hình hợp lệ. Vì vậy sử dụng cron hosting để kích hoạt `workflow_dispatch`.

Nếu file ZIP còn đoạn sau trong `check.yml`, xóa hai dòng `schedule` và `cron`:

```yaml
  schedule:
    - cron: '3-59/5 * * * *'
```

**Giữ nguyên `on:` và toàn bộ `workflow_dispatch` cùng các inputs bên dưới.** Không Disable workflow chính, vì cron hosting vẫn cần gọi workflow này.

Phần đầu file sau khi sửa phải là:

```yaml
name: KMA Schedule Auto

on:
  workflow_dispatch:
    inputs:
      mode:
        description: 'preview: xem thử; upload: nhập lên web ngay; auto: theo biến KMA_ENABLE_UPLOAD'
        required: true
        default: preview
        type: choice
        options:
          - preview
          - upload
          - auto
```

Giữ nguyên toàn bộ `permissions`, `concurrency`, `jobs` và các bước còn lại của file. Commit changes vào `main`.

Nếu đã tạo workflow thử `test-schedule.yml`, có thể xóa hoặc Disable workflow thử đó.

Workflow chính đã khai báo `permissions: contents: write` để ghi lịch sử. Không cần bật quyền tạo/duyệt pull request. Nếu lưu lịch sử báo 403, kiểm tra quyền GitHub Actions, chính sách organization và bảo vệ nhánh; chưa ghi được trạng thái thì tool không gửi POST nhập dữ liệu.

## 8. Tạo token để hosting gọi GitHub

Đây là **Settings cá nhân GitHub**, không phải Settings của repository.

Đường dẫn: **ảnh đại diện → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.

Có thể dùng link điền sẵn tên và quyền:

https://github.com/settings/personal-access-tokens/new?name=KMA%20Schedule%20Cron&target_name=cpcdev85&expires_in=none&actions=write

Kiểm tra lại các trường trước khi tạo:

| Mục | Giá trị |
|---|---|
| Token name | `KMA Schedule Cron` |
| Resource owner | `cpcdev85` hoặc tài khoản sở hữu repository |
| Expiration | `No expiration` nếu chính sách tài khoản cho phép và bạn muốn không có hạn định sẵn |
| Repository access | `Only select repositories` |
| Selected repositories | `GetDanhSachThi` |
| Permissions | `Actions: Read and write` |

Nếu không thấy tiêu đề “Repository permissions”, tìm **Permissions → Add permissions → Actions**, rồi đặt **Read and write**. Chỉ chọn “Public repositories” thì không đủ quyền ghi để kích hoạt workflow. `Metadata: Read-only` tự xuất hiện thì giữ nguyên.

Nhấn **Generate token**, sao chép và lưu riêng. GitHub chỉ hiển thị đầy đủ token lúc tạo. Không chụp/gửi ảnh có token đầy đủ.

`No expiration` là không có ngày hết hạn đặt sẵn, không có nghĩa token không bao giờ mất hiệu lực: bạn hoặc chính sách GitHub vẫn có thể thu hồi nó. Nếu chọn thời hạn, khi hết hạn phải thay token trong cron hosting. Không cần sửa ba Secrets admin khi thay token GitHub.

## 9. Tạo cron trên hosting

Mở mục **Cron Jobs** trong trang quản lý hosting. Chọn chạy 5 phút/lần:

| Trường | Giá trị |
|---|---|
| Minute | `*/5` |
| Hour | `*` |
| Day of month | `*` |
| Month | `*` |
| Day of week | `*` |

Nếu hosting yêu cầu cả biểu thức trong một ô, nhập:

```text
*/5 * * * *
```

Trong ô **Command**, dán **một dòng duy nhất** dưới đây. Chỉ thay `TOKEN_CUA_BAN` bằng token thật; không thêm dấu ngoặc nhọn quanh token. Nếu repository/nhánh khác thì sửa URL và `ref` cho đúng.

```bash
curl --fail --silent --show-error --max-time 30 -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer TOKEN_CUA_BAN" -H "Content-Type: application/json" "https://api.github.com/repos/cpcdev85/GetDanhSachThi/actions/workflows/check.yml/dispatches" -d '{"ref":"main","inputs":{"mode":"auto"}}'
```

Không chèn dấu `\` nối dòng khi dán vào ô lệnh cron một dòng. Lưu cron. Không cần đặt token này vào Secrets GitHub: token được hosting dùng để gọi API, không phải chương trình Python dùng để đăng nhập admin.

### Sau khi đã kiểm tra cron chạy ổn

Nếu muốn bỏ toàn bộ phản hồi và lỗi ở phía hosting, dùng lệnh này:

```bash
curl --fail --silent --show-error --max-time 30 -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer TOKEN_CUA_BAN" -H "Content-Type: application/json" "https://api.github.com/repos/cpcdev85/GetDanhSachThi/actions/workflows/check.yml/dispatches" -d '{"ref":"main","inputs":{"mode":"auto"}}' >/dev/null 2>&1
```

| Tùy chọn | Ý nghĩa |
|---|---|
| `--fail` | Trả mã lỗi khi nhận phản hồi HTTP lỗi |
| `--silent` | Không hiển thị thanh tiến trình |
| `--show-error` | Vẫn xuất lỗi khi không bị chuyển hướng |
| `--max-time 30` | Mỗi yêu cầu curl tối đa 30 giây; không giới hạn thời gian xử lý PDF trên GitHub |
| `>/dev/null` | Bỏ đầu ra thông thường |
| `2>&1` | Bỏ cả đầu ra lỗi cùng nơi với đầu ra thông thường |

Không có phần chuyển hướng thì lệnh **không tự tạo file log**. Hosting có thể gửi đầu ra bằng Cron Email, lưu trong hệ thống quản lý hoặc bỏ đi, tùy cấu hình. Thêm `>/dev/null 2>&1` sẽ không còn nhận được các lỗi curl đó; log chương trình Python trong GitHub Actions vẫn còn.

Không thêm `-v` hoặc `--trace` vào lệnh có token nếu không hiểu rõ việc ghi log header xác thực.

## 10. Xác nhận cron thật sự chạy

1. Không bấm Run workflow trong lúc theo dõi lịch.
2. Vào **Actions → KMA Schedule Auto**.
3. Chờ qua mốc cron kế tiếp rồi xem có lượt mới không.
4. Mở lượt → **check → Check PDFs and upload new JSON** để xem kết quả.

**Cron hosting gọi API cũng xuất hiện với event `workflow_dispatch`, giống thao tác bấm thủ công.** Vì vậy sau khi chuyển sang cron hosting, không lọc `event:schedule` để tìm các lượt này. Dựa vào thời gian các lượt mới khi bạn không tự bấm Run workflow.

| Dấu hiệu | Ý nghĩa |
|---|---|
| Lượt mới xuất hiện từ hosting | Yêu cầu kích hoạt đã tới GitHub |
| `Chế độ: TẢI LÊN` | Tool đang cho phép nhập dữ liệu |
| `Chế độ: XEM THỬ` | Lượt chạy không nhập dữ liệu |
| `PDF ...: đã xử lý; bỏ qua.` | File cũ đã có lịch sử, không nhập lại |
| `Đã nhập ... dòng` | Website đã xác nhận nhập dữ liệu |
| Dấu đỏ | Mở log để xem bước lỗi |

**Dấu xanh không nhất thiết nghĩa là vừa nhập dữ liệu mới:** có thể không có file mới hoặc lượt đó chỉ chạy preview.

Nếu phần log không hiện, tải lại trang, mở job `check` rồi mở bước xử lý. Có thể tải log từ menu của lượt chạy nếu giao diện cung cấp Download log archive.

## 11. Đổi chu kỳ

Chỉ sửa lịch **cron hosting**, không cần sửa code Python:

| Chu kỳ | Biểu thức cron |
|---|---|
| 1 phút/lần | `* * * * *` |
| 3 phút/lần | `*/3 * * * *` |
| 5 phút/lần | `*/5 * * * *` |
| 10 phút/lần | `*/10 * * * *` |

Hosting phải cho phép mức chu kỳ đó. Ví dụ `*/5` dự kiến gọi ở các phút 00, 05, 10, 15… mỗi giờ; không phải 5 phút kể từ lúc bạn lưu cron.

Giới hạn tối thiểu 5 phút của lịch `schedule` GitHub không áp dụng trực tiếp cho các yêu cầu `workflow_dispatch` từ hosting. Tuy nhiên, GitHub vẫn có giới hạn API, tài nguyên và hàng đợi, nên gọi mỗi phút không đảm bảo chương trình thực sự bắt đầu đúng mỗi phút.

Workflow có khóa `concurrency` để không chạy hai lượt cùng lúc. Nếu lượt trước còn chạy, lượt mới phải chờ; cấu hình mặc định không giữ vô hạn tất cả lượt đang chờ. Mức 5 phút phù hợp với nhu cầu theo dõi danh sách thi và giảm tải cho trang nguồn.

## 12. File ghi nhớ - không xóa để thử cron

`json/github_state.json` được tạo/ghi khi có thao tác nhập dữ liệu. File chỉ chứa mã băm, trạng thái và thời gian; không chứa tài khoản admin hoặc danh sách sinh viên.

- `pdfs`: các nội dung PDF đã hoàn tất.
- `uploads`: mã nội dung JSON và trạng thái tải lên.
- `sending`: đã ghi lịch sử trước khi gửi; chưa có xác nhận thành công được lưu bền.
- `success`: đã được website xác nhận và ghi nhận thành công.
- `failed`: cho phép thử lại sau lỗi đã xác định.

File không nhất thiết thay đổi sau mỗi lượt kiểm tra. Preview không tạo lịch sử đã xử lý. Không có dữ liệu mới thì không nhất thiết có commit mới.

**Xóa file JSON không kích hoạt cron.** Việc đó chỉ khiến tool mất thông tin chống trùng, có thể nhập lại dữ liệu cũ.

### Khôi phục file nếu lỡ xóa

1. Đặt `KMA_ENABLE_UPLOAD=false` và chờ lượt đang chạy kết thúc.
2. Mở lịch sử commit của repository; tìm commit trước lúc xóa file.
3. Mở `json/github_state.json` trong commit cuối cùng có trạng thái đúng; ưu tiên bản đã ghi `success`, không lấy bản chỉ mới ghi `sending` nếu có bản thành công mới hơn.
4. Sao chép toàn bộ nội dung.
5. Trên nhánh `main`, **Add file → Create new file**, đặt tên `json/github_state.json`.
6. Dán nội dung, Commit changes.
7. Đặt lại `KMA_ENABLE_UPLOAD=true`.

Nếu tạo lại repository, phải mang theo file lịch sử cuối cùng nếu đã nhập dữ liệu, đồng thời tạo lại Secrets/Variables. Chỉ mang mã mới từ ZIP sang thì không mang lịch sử chống trùng.

### Khi chưa rõ kết quả tải lên

Mất mạng hoặc bị hủy sau POST có thể khiến web đã nhập nhưng tool chưa lưu được `success`. Tool giữ `sending` và không tự gửi lại.

1. Đặt `KMA_ENABLE_UPLOAD=false`, chờ lượt đang chạy xong.
2. Đối chiếu dữ liệu trên admin, dùng mã JSON trong log để tìm đúng mục `uploads`.
3. Nếu chắc chắn đã nhập đủ: đổi `sending` thành `success`.
4. Nếu chắc chắn chưa nhập: đổi thành `failed`.
5. Nếu chỉ nhập một phần hoặc không chắc: chưa đổi trạng thái, xử lý dữ liệu trên web trước.
6. Commit rồi bật lại `KMA_ENABLE_UPLOAD=true`.

Không sửa file khi lượt khác đang ghi. Không sửa các mã băm.

## 13. Nhập dữ liệu và khả năng trùng

- Gửi vào tab danh sách thi bằng action `dsthi_upload`.
- Dùng `mode=append`: thêm dữ liệu, không xóa danh sách hiện có.
- Tên đợt thi lấy từ tên PDF/JSON bỏ đuôi `.pdf`/`.json`, chuẩn hóa ký tự tên file không hợp lệ và giới hạn 150 ký tự theo website.
- JSON có cùng nội dung đã thành công thì bỏ qua, kể cả đổi tên file.
- PDF có nội dung thay đổi sẽ được đọc lại. Nếu JSON mới có cả dòng cũ, web nhập thêm vẫn có thể trùng dòng. Bản này chưa cập nhật theo từng sinh viên.
- Website có thể bỏ dòng lỗi hoặc dòng trùng trong cùng một file; có cảnh báo thì cần đối chiếu trên admin, không tự gửi lại cả file.
- PDF và bản ghi sinh viên chỉ xử lý tạm trong runner, không commit vào repository hoặc tạo artifact. Log do tool chủ động ghi chỉ có số dòng, mã băm và trạng thái.

## 14. Tắt, bật, thay thông tin

| Việc cần làm | Cách thực hiện |
|---|---|
| Tắt nhập dữ liệu nhưng vẫn kiểm tra | `KMA_ENABLE_UPLOAD=false`; không ảnh hưởng yêu cầu upload thủ công nếu bạn cố ý chọn mode đó |
| Dừng toàn bộ lượt tự động từ hosting | Tắt/xóa cron hosting |
| Dừng tất cả cách kích hoạt workflow | Disable workflow chính; cron gọi sẽ không chạy được |
| Bật lại | Enable workflow và bật lại cron hosting |
| Đổi mật khẩu admin | Sửa Secret `KMA_ADMIN_PASSWORD` |
| Đổi đường dẫn admin | Sửa đường dẫn trên hosting, rồi sửa Secret `KMA_ADMIN_BASE_URL` |
| Thay token GitHub | Tạo token mới đúng quyền, thay trong lệnh cron, kiểm tra chạy rồi thu hồi token cũ |

Bật/tắt cron không hủy lượt đã chạy trước đó. Chỉ đổi biến `KMA_ENABLE_UPLOAD` cũng không dừng một lượt đang xử lý.

## 15. Lỗi thường gặp

| Hiện tượng | Kiểm tra / xử lý |
|---|---|
| Không có lượt mới | Cron hosting có bật không; lịch đúng không; token còn hiệu lực; URL repository, `check.yml`, `ref=main` đúng không; workflow có active không |
| Bấm thủ công được nhưng hosting không gọi được | Bỏ tạm `>/dev/null 2>&1` để xem lỗi cron qua kênh đầu ra hosting cung cấp; kiểm tra dấu nháy và xóa dấu nối dòng `\` |
| HTTP 401 | Token thiếu, sai, hết hạn hoặc bị thu hồi |
| HTTP 403 | Quyền token hoặc chính sách truy cập; cũng có thể giới hạn API, cần xem thông báo phản hồi |
| HTTP 404 khi gọi API | Sai URL/tên workflow hoặc token không nhìn thấy repository được chọn |
| HTTP 422 | `ref`, input `mode`, định dạng JSON hoặc cấu hình workflow không phù hợp |
| Lỗi đăng nhập admin | Kiểm tra ba Secrets; URL phải là thư mục admin; kiểm tra tài khoản bị khóa hoặc website chặn kết nối |
| Đọc được PDF nhưng chưa nhập | Kiểm tra mode, biến `KMA_ENABLE_UPLOAD`, trạng thái đã xử lý và lỗi trong log |
| Không có thư mục json | Có thể chưa có lần nhập nào; preview không tạo file. Không dùng sự xuất hiện của folder để kết luận cron chạy hay không |
| JSON `sending` | Kiểm tra website trước khi xử lý trạng thái; không xóa file để chạy lại |
| Tool không đọc được PDF | PDF scan, cấu trúc bảng khác, thiếu tên môn hoặc dữ liệu bắt buộc; bản này chưa OCR |
| Job timeout | Giới hạn 20 phút/lượt. Lượt sau bỏ qua các file đã hoàn tất và thử tiếp file còn lại |

## 16. Chi phí, giới hạn và tài liệu

Repository public dùng runner GitHub tiêu chuẩn có thời gian chạy miễn phí theo chính sách GitHub tại lúc thiết lập. Repository private có hạn mức của gói; không tự suy ra chạy private liên tục là miễn phí. Hosting vẫn theo gói dịch vụ bạn đang sử dụng. Không chọn larger runner nếu muốn giữ mô hình miễn phí trên GitHub.

Không coi GitHub Actions là máy chủ chạy nền có cam kết đúng từng phút. Cron hosting chủ động gửi yêu cầu nhưng GitHub vẫn quyết định thời điểm cấp máy chạy.

Tài liệu chính thức để kiểm tra khi giao diện/chính sách thay đổi:

- Tạo token và link điền sẵn: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- API kích hoạt workflow: https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- Secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- Phút chạy miễn phí: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Giới hạn Actions: https://docs.github.com/en/actions/reference/limits
- Giới hạn API: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

## Checklist thiết lập lại nhanh

- [ ] Mã nguồn nằm đúng thư mục gốc và workflow ở `.github/workflows/check.yml` trên nhánh mặc định.
- [ ] Có đủ ba Repository Secrets của website.
- [ ] Preview chạy thành công và đối chiếu dữ liệu.
- [ ] Đã kiểm tra lịch sử nhập cũ trước lần upload đầu tiên.
- [ ] `KMA_ENABLE_UPLOAD=true` trong Repository Variables.
- [ ] Workflow giữ `workflow_dispatch`; đã bỏ lịch `schedule` nếu chỉ dùng cron hosting.
- [ ] Token fine-grained chọn đúng repository và quyền Actions: Read and write.
- [ ] Cron hosting có lịch `*/5 * * * *`, lệnh curl một dòng, `mode=auto`.
- [ ] Có lượt mới từ cron khi không tự bấm Run workflow.
- [ ] Giữ và sao lưu `json/github_state.json`.
- [ ] Sau khi kiểm tra ổn mới thêm `>/dev/null 2>&1` nếu muốn bỏ đầu ra cron.
