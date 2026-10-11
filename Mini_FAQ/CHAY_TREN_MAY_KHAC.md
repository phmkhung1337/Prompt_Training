# Chạy Campus FAQ trên máy khác

## Windows

1. Giải nén toàn bộ `Campus_FAQ_portable.zip` vào một thư mục bạn có quyền ghi.
2. Cài **Python 3.13 bản 64-bit** từ [python.org](https://www.python.org/downloads/) nếu máy chưa có Python. Bật **Add Python to PATH** khi cài.
3. Mở `start.bat`. Lần đầu, chương trình tự tạo `.venv`, cài thư viện và tạo `.env` từ mẫu. Cần Internet để tải thư viện và model embeddings.
4. Mở `.env`, điền API key/model của bạn. Khởi động lại sau khi thay cấu hình. Nếu dùng Ollama local, cài/chạy Ollama và tải model tương ứng trên máy đích.
5. Mở [http://127.0.0.1:8510](http://127.0.0.1:8510). Giữ cửa sổ chạy mở; dùng **Ctrl+C** để dừng.

Không cần kích hoạt môi trường ảo hoặc thay PowerShell ExecutionPolicy. Có thể chạy từ PowerShell:

```powershell
.\start.bat
.\start.bat --setup
.\start.bat --check
.\start.bat --port 8511
.\start.bat --cli
```

`--setup` chỉ cài môi trường. `--check` kiểm tra phiên bản thư viện và xung đột phụ thuộc, không gọi API. Nếu cổng đang được dùng, chọn `--port` khác. Lần chạy đầu có thể mất vài phút vì thư viện embeddings khá lớn.

## macOS hoặc Linux

Cài Python 3.10 trở lên; khuyến nghị 3.13, là bản đã kiểm thử trên máy phát triển. Sau khi giải nén, chạy:

```sh
python3 run.py
python3 run.py --check
python3 run.py --port 8511
python3 run.py --cli
```

Python cần có module `venv` và `ensurepip`; một số bản Linux tách chúng thành gói riêng. Chưa kiểm thử trực tiếp trên macOS/Linux hoặc CPU ARM, nên khả năng cài đặt còn phụ thuộc wheel của các thư viện trên hệ điều hành/kiến trúc đó.

## Những file cần chuyển

File ZIP do `scripts/package_project.py` tạo có mã Python, giao diện, design tokens, FAQ, prompt, cấu hình Streamlit, thư viện đã ghim phiên bản và hướng dẫn này. ZIP không chứa `.venv`, `.cache`, `.git`, file `.env` có key hoặc `secrets.toml`.

**Không sao chép `.venv` từ máy cũ:** nó chứa đường dẫn tới Python trên máy cũ. Launcher tạo môi trường mới trên máy đích; nếu phát hiện môi trường cũ không dùng được, nó giữ lại trong `.venv.backup-*` rồi tạo lại. `.env` đã có sẽ được giữ nguyên.

Cách tạo lại ZIP khi sửa FAQ/mã:

```powershell
python scripts/package_project.py
```

Kết quả nằm trong `dist/Campus_FAQ_portable.zip`. File ZIP chứa nội dung FAQ hiện tại; kiểm tra và thay thông tin demo bằng thông tin chính thức khi cần.

## Nếu chưa chạy được

- **Không tìm thấy Python:** cài Python 3.13, mở cửa sổ terminal mới rồi chạy `start.bat`.
- **Lỗi tải thư viện/model:** kiểm tra Internet và chạy lại. Model embeddings được cache trong `.cache/embeddings` sau lần tải đầu.
- **Cổng bị chiếm/chặn:** dùng `start.bat --port 8511`; chương trình luôn chỉ nghe trên `127.0.0.1`.
- **Thiếu key/model:** sửa `.env` trên máy đích; phần tra cứu cần LLM mới dùng cấu hình này. `--check` không xác minh quyền truy cập API.
- **Đóng cửa sổ chạy thì web mất kết nối:** mở lại `start.bat` và giữ cửa sổ đó mở trong lúc sử dụng.
