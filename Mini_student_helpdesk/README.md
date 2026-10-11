# AI Student Helpdesk — Trợ lý học tập

Ứng dụng Python/Streamlit chuyên hỗ trợ sinh viên hiểu kiến thức, giải bài tập, lập trình, ôn thi, lập kế hoạch, kỹ năng học và định hướng học tập/nghề nghiệp. AI dùng kiến thức của model và hướng dẫn học tập bổ sung; không gắn với một trường cụ thể.

## Cấu trúc

| File | Vai trò |
|---|---|
| `app.py` | Giao diện, hội thoại, cá nhân hóa, JSON và thông tin API |
| `llm_client.py` | Chọn hướng dẫn/ngữ cảnh, gọi Ollama hoặc OpenAI, cache, xử lý lỗi |
| `system_prompt.txt` | Vai trò trợ lý học tập và cách trả lời |
| `faq.md` | 10 hướng dẫn học tập bổ sung theo 5 nhóm; không giới hạn kiến thức model |
| `response_schema.py` | Schema JSON và validation bằng Pydantic |
| `api_budget.py` | Ngân sách input/output thích nghi |
| `.env.example` | Cấu hình mẫu; tạo `.env` riêng cho mỗi máy |
| `start.ps1` | Chạy local trên Windows |
| `tests/` | Kiểm thử giao diện/API giả lập, JSON, cache và ngân sách |

## Cài đặt và chạy

Trong PowerShell tại thư mục project:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Tạo `.env` nếu chưa có (không ghi đè file đã có key):

```powershell
Copy-Item .env.example .env
```

Ollama Cloud:

```env
LLM_PROVIDER=ollama
OLLAMA_API_KEY=key_cua_ban
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=gpt-oss:120b
```

Tạo key tại https://ollama.com/settings/keys; chọn model tài khoản được dùng theo https://docs.ollama.com/cloud. Chạy Ollama local thì đặt `OLLAMA_BASE_URL=http://localhost:11434`, để key trống và chọn model đã tải. Dùng OpenAI thì đặt `LLM_PROVIDER=openai`, `OPENAI_API_KEY` và `OPENAI_MODEL` phù hợp.

Chạy ứng dụng:

```powershell
.\start.ps1
```

Nếu PowerShell chặn script, chạy trực tiếp Python trong `.venv`:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

Mở http://127.0.0.1:8501 và giữ terminal chạy. Đổi Wi-Fi không thay đổi địa chỉ loopback. Trong VS Code chọn **Run Streamlit Helpdesk** (extension Python Debugger); cấu hình Chrome chỉ mở trình duyệt. Sửa `.env` cần khởi động lại ứng dụng. `.env` nằm trong `.gitignore`; không commit key.

## Phạm vi và cá nhân hóa

Nút gợi ý: **Hiểu bài**, **Lập trình**, **Ôn thi**, **Cách học**. Thanh bên cho nhập trình độ, mục tiêu/thời gian và chọn Tự động/Ngắn gọn/Chi tiết. Hồ sơ giữ trong phiên; cuộc trò chuyện mới xóa lịch sử/cache nhưng giữ các lựa chọn cá nhân hóa.

AI có thể giải thích và giải bài theo yêu cầu, sửa code, đặt bài luyện tập, phản hồi lời giải và đề xuất kế hoạch. Nếu thiếu dữ kiện, hỏi trọng tâm; không giả vờ đã chạy code hoặc tra web. Khi người dùng hỏi chính sách riêng của trường, AI nói rõ chưa có nguồn chính thức và hướng dẫn tìm nguồn; không tự tạo học phí, hạn, tên người hay liên hệ.

Khi chuyển phiên bản từ phạm vi cũ sang trợ lý học tập, trạng thái hội thoại/cache cũ trong phiên được làm mới để tránh đưa thông tin của phiên bản cũ vào câu trả lời.

## JSON có validation

```json
{
  "answer": "Vòng lặp for duyệt từng phần tử trong một dãy. Ví dụ: for i in range(3): print(i).",
  "category": "programming",
  "status": "answered"
}
```

`category`: `concept`, `programming`, `study_planning`, `study_skills`, `career_guidance`, `other`.

`status`: `answered`, `unknown`, `clarify`, `out_of_scope`; `error` chỉ dành cho fallback ứng dụng.

Pydantic kiểm tra trường bắt buộc, kiểu, enum, trường thừa và answer không rỗng (tối đa 32.000 ký tự); parser từ chối khóa JSON lặp và ký tự điều khiển bất thường. Nếu JSON sai escape (ví dụ dấu backslash trong công thức) hoặc xuống dòng thật trong chuỗi, ứng dụng chuẩn hóa các ký tự đó rồi parse và validate lại toàn bộ schema; không thêm trường, đoán nội dung hoặc đóng JSON bị cắt. Không gọi thêm API để sửa định dạng. Các lỗi còn lại trả fallback đúng schema, không cache, có nút thử lại. Lỗi HTTP hoặc phản hồi chưa hoàn thành hiển thị thông báo để thử lại. Validation cấu trúc không bảo đảm mọi nội dung AI đều đúng.

OpenAI nhận strict schema; Ollama local nhận `format`. Ollama Cloud hiện chưa hỗ trợ structured outputs (https://docs.ollama.com/capabilities/structured-outputs), nên yêu cầu JSON bằng prompt rồi validate ở Python. `ask_student()` trả `dict` đã validate. Giao diện có “JSON đã validate” cùng model, endpoint, usage.

## Ngân sách và cache

Mặc định: 16.000 ký tự/câu hỏi, 24 cặp lịch sử, input 12.000 token ước tính; mức đáp án ngắn 350, thường 900, chi tiết 2.400; timeout 90 giây. FAQ không quyết định độ dài đáp án. Riêng Ollama `gpt-oss` có thêm trần dự phòng 1.024 token cho suy luận: trần `num_predict` mặc định thường là 1.924, chi tiết 3.424. Model khác mặc định không thêm dự phòng. Trần không phải số token luôn tiêu thụ; API có thể dừng sớm, usage mới là lượng thực tế. Có thể điều chỉnh trong `.env`:

```env
LLM_MAX_HISTORY_PAIRS=24
LLM_INPUT_BUDGET=12000
LLM_OUTPUT_SHORT=350
LLM_OUTPUT_NORMAL=900
LLM_OUTPUT_DETAILED=2400
LLM_TIMEOUT_SECONDS=90
# Tùy chọn, đặt 0 để không thêm dự phòng, tối đa 8000.
OLLAMA_REASONING_RESERVE=1024
```

Input dùng heuristic byte UTF-8 cộng overhead, không phải tokenizer của model. Khi vượt ngân sách, bỏ các cặp cũ và chọn lại hướng dẫn; giữ nguyên câu hỏi. Nếu riêng câu hỏi+tài liệu vẫn quá lớn, yêu cầu rút gọn hoặc tăng cấu hình. Các mức này không thay đổi context window của model hoặc áp dụng hạn mức tài khoản/ngày.

Hướng dẫn được chọn theo nhóm học tập; chỉ câu nối tiếp mới lấy chủ đề hướng dẫn từ lịch sử. Chủ đề mới không nhận FAQ của chủ đề trước. FAQ thiếu/trống vẫn gọi model bình thường. Chủ đề chưa có hướng dẫn vẫn được model hỗ trợ bằng kiến thức của nó. Không gọi thêm LLM để phân loại/tóm tắt.

Cache tài liệu trong RAM tự cập nhật khi file thay đổi. Cache đáp án riêng phiên: tối đa 32 mục, TTL 5 phút; khóa gồm schema, provider, endpoint, model, prompt, dữ liệu, profile, mức trả lời, ngữ cảnh và dấu băm key. Lỗi không cache. Lịch sử gửi LLM chỉ có văn bản; JSON được giữ để hiển thị.

Usage API được hiển thị khi nhà cung cấp trả dữ liệu; nếu không có thì ghi rõ. Cache phiên ghi nhận 0 token cho lượt đã tránh gọi, phân biệt với prompt cache nhà cung cấp. OpenAI SDK tối đa 2 retry cho lỗi tạm thời; Ollama không tự retry HTTP.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```

Kiểm thử dùng API giả lập, không tiêu thụ token inference. Chúng kiểm tra luồng và schema, không thay thế đánh giá chất lượng model thật. Hội thoại/profile/cache chỉ trong RAM của phiên; chưa có database, web search hoặc thực thi code.

Kiểm tra API thật (tiêu thụ quota của key đã cấu hình, dùng câu hỏi không nhạy cảm):

```powershell
python scripts/check_live.py "Tính tích phân 2x từ 0 đến 3" "Giải thích vòng lặp Python kèm ví dụ"
```

Script in kết quả, trạng thái HTTP/hoàn thành và usage, không in key hoặc phần suy luận nội bộ. Thêm `--show-invalid` nếu cần xem nội dung cuối bị lỗi JSON của các câu hỏi thử.
Thêm `--ui` để gửi các câu hỏi qua giao diện Streamlit bằng AppTest, giữ lịch sử cho câu nối tiếp; chế độ này cũng gọi API thật.
