# Báo cáo tối ưu dữ liệu gọi LLM

Các số đo bên dưới ghi nhận trước khi thêm bảng học phí 9 kỳ vào FAQ; không đại diện cho độ dài FAQ sau thay đổi đó.

Đo offline trên prompt và FAQ hiện tại, bằng Python `len()` (ký tự Unicode). Không có tokenizer khả dụng; chưa gọi API thật. Các số dưới đây **không phải token** và không phải chi phí thực tế. Chỉ tính instructions, chưa cộng câu hỏi, lịch sử và overhead API.

| Nội dung | Trước (ký tự) | Sau (ký tự) |
|---|---:|---:|
| System prompt | 1.261 | 841 |
| Instructions: hỏi học phí | 4.366 | 2.100 |
| Instructions: hỏi đăng ký học phần | 4.366 | 1.961 |
| Instructions: hỏi giấy xác nhận | 4.366 | 1.946 |
| Instructions: câu mơ hồ “Còn hạn thì sao?” | 4.366 | 3.871 |

Ba câu mẫu là các gợi ý trên giao diện. FAQ vẫn giữ nguyên trên ổ đĩa; mỗi nhóm được gửi nguyên vẹn cùng tiêu đề và cảnh báo demo. Khi không nhận diện được chủ đề hoặc cấu trúc FAQ mới, gửi toàn bộ tài liệu. Bộ định tuyến từ khóa không bao phủ mọi cách diễn đạt; cần đánh giá thêm bằng câu hỏi thực tế khi có key.

Giới hạn đầu ra: trước 600 token mọi câu, sau 450 cho một chủ đề và 600 khi nhiều chủ đề/chưa rõ. Đây là mức trần, không phải lượng token thực tế tiêu thụ. Câu trả lời chưa hoàn thành không được cache hoặc hiển thị như đáp án đầy đủ.

Cache câu trả lời riêng từng phiên: tối đa 32 mục, TTL 300 giây, dùng khóa của toàn bộ request và cấu hình xác thực. FAQ/prompt sửa, model/key đổi hoặc ngữ cảnh đổi thì không dùng lại đáp án cũ. Cache không lưu xuống đĩa. SDK vẫn có tối đa 2 retry cho lỗi tạm thời, nên retry mạng có thể tạo nhiều lượt HTTP; không đảm bảo exactly-once khi mất kết nối.

Kiểm thử dùng API giả lập để kiểm tra định tuyến đủ 12 câu FAQ, câu nhiều chủ đề, fallback, lịch sử, cache/hết hạn, sửa tài liệu, câu trả lời bị cắt và giao diện. Không chứng minh chất lượng câu trả lời LLM thật bằng mock.

Đối chiếu cách giảm context/đầu ra theo [OpenAI Docs](https://developers.openai.com/api/docs/guides/latency-optimization).
