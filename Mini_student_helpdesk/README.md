# Student Helpdesk Chatbot

Ứng dụng chat Streamlit hỗ trợ sinh viên tra cứu **học phí**, **đăng ký môn** và **dịch vụ sinh viên**. Đây là demo học tập: FAQ dùng dữ liệu giả lập, chưa kết nối hệ thống nội bộ của trường.

## Cấu trúc

```text
Mini_student_helpdesk/
├── app.py              # Giao diện Streamlit, hội thoại trong session
├── llm_client.py       # OpenAI Responses API, đọc FAQ và xử lý lỗi
├── system_prompt.txt   # Quy tắc trả lời của chatbot
├── faq.md              # 12 mục FAQ giả lập
├── requirements.txt
├── .env.example
└── .gitignore
```

## Cài đặt trên Windows

Mở PowerShell tại thư mục project:

```powershell
python -m venv .venv
```

Kích hoạt môi trường ảo và cài thư viện:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Nếu PowerShell không cho kích hoạt, không cần đổi policy hệ thống; dùng trực tiếp Python trong `.venv`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Cấu hình API key và model

Tạo `.env` nếu chưa có:

```powershell
Copy-Item .env.example .env
```

Mở `.env` bằng VS Code hoặc Notepad và điền API key cùng tên model mà tài khoản của bạn được phép dùng:

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Thay `your_api_key_here` bằng key thật. Không gửi key qua chat, không đưa key vào mã nguồn và không commit `.env`. Ứng dụng tự đọc file `.env` bằng `python-dotenv`.

## Chạy demo tại localhost

Đã kích hoạt `.venv`:

```powershell
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Không kích hoạt `.venv`:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

Mở [http://localhost:8501](http://localhost:8501). Ứng dụng chỉ bind `127.0.0.1`; không deploy hoặc tạo URL công khai.

## Thay dữ liệu FAQ

Mở `faq.md`, thay tên trường giả lập, các bước và đầu mối liên hệ bằng thông tin đã được trường xác nhận. Dữ liệu mẫu dùng miền email `.example` và không đại diện cho một trường thật. Giữ nội dung trong ba nhóm: học phí, đăng ký môn, hỗ trợ sinh viên. Nhãn dữ liệu giả lập trong giao diện cần được bỏ hoặc sửa chỉ khi FAQ đã được thay bằng dữ liệu chính thức.

## Cách hoạt động

- `app.py` giữ lịch sử trong `st.session_state`; lịch sử không được ghi xuống ổ đĩa.
- Mỗi lần gửi, `llm_client.py` gửi FAQ, system prompt, tối đa 5 cặp hội thoại gần nhất và câu hỏi hiện tại trong một lần gọi ở cấp ứng dụng.
- Câu hỏi giới hạn 2.000 ký tự; câu trả lời giới hạn 600 token.
- OpenAI SDK được cấu hình timeout 30 giây và tối đa 2 lần retry tích hợp cho lỗi tạm thời. Lỗi xác thực không retry.
- Khi có lỗi, hội thoại cũ được giữ lại và có nút thử lại câu hỏi thất bại. App không tự tạo câu trả lời thay thế.

## Ví dụ câu hỏi

- “Em xem học phí và công nợ ở đâu?”
- “Em đăng ký học phần như thế nào?”
- “Em xin giấy xác nhận sinh viên ở đâu?”
- “Em đã thanh toán nhưng công nợ chưa cập nhật thì sao?”

## Xử lý lỗi thường gặp

- **Thiếu API key/model:** kiểm tra `OPENAI_API_KEY` và `OPENAI_MODEL` trong `.env`.
- **API key không hợp lệ:** kiểm tra key và quyền truy cập trong trang quản lý API của tài khoản.
- **Không tìm thấy model:** đổi `OPENAI_MODEL` sang model mà tài khoản của bạn được phép sử dụng.
- **Rate limit hoặc hết quota:** đợi nếu bị giới hạn tốc độ; kiểm tra billing/quota nếu tài khoản hết hạn mức.
- **Timeout hoặc mất kết nối:** kiểm tra Internet rồi dùng nút thử lại.
- **FAQ lỗi hoặc trống:** đảm bảo `faq.md` nằm cùng thư mục với `app.py` và có nội dung.

## Kiểm tra bằng mock

Chạy kiểm tra không gọi API thật:

```powershell
python -m unittest discover -s tests -v
```

Mock chỉ dùng trong kiểm tra; bản demo luôn dùng OpenAI API thật và báo lỗi nếu thiếu cấu hình.
