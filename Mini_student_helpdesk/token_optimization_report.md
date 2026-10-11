# Tối ưu API cho trợ lý học tập

Ứng dụng hiện có phạm vi hỗ trợ học tập độc lập. Các số đo ký tự ở phiên bản có dữ liệu trường trước đây không còn đại diện cho prompt/tài liệu hiện tại.

- Gửi kiến thức phương pháp bổ sung theo nhóm: kiến thức/bài tập, lập trình, kế hoạch, kỹ năng học, định hướng.
- Chủ đề không khớp tài liệu vẫn được model giải thích; không gửi dữ liệu trường giả lập.
- Giữ ngữ cảnh cần thiết, tối đa 24 cặp theo cấu hình; bỏ các cặp cũ khi vượt input ước tính.
- Output thích nghi theo yêu cầu/mức trả lời; không ép dùng hết ngân sách.
- Cache request giống nhau trong phiên và cache nội dung file; không gọi LLM để tóm tắt hoặc phân loại.
- Usage thực tế lấy từ API, input ước tính chỉ phục vụ quản lý ngân sách. Không quy đổi ký tự thành số token tính phí.

Chi tiết cấu hình và giới hạn: `README.md`, `api_budget.py`, `llm_client.py`.

## Sửa lỗi API thực tế — 11/10/2026

Provider: Ollama Cloud; model giữ nguyên `gpt-oss:120b`. Các câu hỏi thử không chứa thông tin cá nhân.

| Câu hỏi | Trước sửa: output API báo | Sau sửa cuối: output API báo | Kết quả |
|---|---:|---:|---|
| Tích phân 2x từ 0 đến 3 | 442 | 385 | Trước: HTTP 200 nhưng JSON chứa escape LaTeX sai; sau: JSON hợp lệ, đáp án 9 |
| Giải thích vòng lặp for Python kèm ví dụ | 450 | 1061 | Trước: `done_reason=length`, bị cắt; sau: `stop`, JSON hoàn chỉnh và ví dụ code |

Đây là usage của các lượt thực tế, có thể bao gồm token suy luận; không phải phép đo token phần đáp án riêng. Prompt đã thay đổi và model có tính ngẫu nhiên, nên bảng không chứng minh tỷ lệ tiết kiệm. Sửa này ưu tiên hoàn tất câu trả lời; không tuyên bố giảm token trong mọi trường hợp.

- Bỏ trần 450 gắn với FAQ. Mức đáp án bình thường mặc định 900; cộng dự phòng suy luận 1024 cho gpt-oss, trần `num_predict=1924`. Trần không phải lượng token luôn tiêu thụ.
- Chuẩn hóa escape không hợp lệ/xuống dòng thật trong chuỗi JSON ở Python, giữ nội dung rồi validate toàn bộ schema. Không gọi thêm API; vẫn từ chối trường sai/thừa/lặp, kiểu sai và JSON bị cắt.
- FAQ thiếu/trống không chặn model. Câu hỏi chủ đề mới không kế thừa FAQ từ chủ đề trước; câu nối tiếp vẫn giữ ngữ cảnh.
- Prompt có mẫu JSON hợp lệ cho công thức và code. [Ollama Cloud chưa hỗ trợ structured outputs](https://docs.ollama.com/capabilities/structured-outputs), vì vậy vẫn cần validation trong ứng dụng.

Kết quả: 53 kiểm thử tự động đạt; 6 câu hỏi ở bản cuối về toán, Python, sinh học, vật lý, hóa và tiếng Anh đều trả JSON hợp lệ với `status=answered`. Thêm 2 lượt qua Streamlit AppTest gọi API thật: nghiệm x=4, câu nối tiếp đổi vế phải trả x=6 với 2 tin lịch sử. Đây là kiểm tra hoạt động và một số nội dung cụ thể, không phải đánh giá toàn diện độ chính xác mọi môn học.

Streamlit đã khởi động lại tại `http://127.0.0.1:8501/`; trang chủ và `/_stcore/health` trả HTTP 200. Script kiểm tra thật: `scripts/check_live.py`; chỉ chạy khi chủ động chấp nhận tiêu thụ quota API.
