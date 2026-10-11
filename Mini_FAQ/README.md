# Campus FAQ Assistant

Trợ lý sinh viên chạy bằng Streamlit hoặc terminal. Giao diện **Chat tập trung**, ưu tiên **desktop**: chủ đề ở thanh bên, thẻ gợi ý khi bắt đầu, khung hội thoại tự cuộn và ô soạn tin phía dưới. Gửi bằng nút **Gửi câu hỏi** hoặc **Ctrl+Enter** (Mac: **Cmd+Enter**), Enter để xuống dòng. Form gom nội dung nhập thành một lần gửi, không chạy lại ứng dụng chỉ vì rời ô nhập. Chọn **Sáng / Tối** tại mục **Giao diện**; lựa chọn được giữ trong phiên và khi bắt đầu cuộc trò chuyện mới.

Bảng màu lấy cảm hứng từ ảnh xanh chàm–tím: nền navy #080A22, điểm nhấn lavender #B7BEFF ở chế độ tối; nền #F7F5FC, điểm nhấn tím #5547BD ở chế độ sáng. Gradient thương hiệu đi từ #263EB5 đến #7550B3.

Thiết kế theo [kiến trúc design token của Figma](https://www.figma.com/resource-library/design-token-architecture/): giá trị gốc trong design_tokens.json, màu semantic riêng cho Sáng/Tối, và alias cho bo góc/khoảng cách của component. ui_theme.py resolve token sang CSS; ui.css sử dụng token thay vì lặp mã màu. Đây là triển khai trong ứng dụng Streamlit; không tạo hoặc đồng bộ một file thiết kế trên Figma.

## Nghiệp vụ

- Tìm kiếm kết hợp embeddings đa ngôn ngữ trên CPU và từ khóa có trọng số. Chuẩn hóa dấu/đánh số câu hỏi để ưu tiên câu khớp chính xác; có mở rộng cách diễn đạt giấy chứng nhận đang học thành giấy xác nhận sinh viên. Điểm cosine được tăng nhẹ theo từ khóa, không phải xác suất câu trả lời đúng.
- Lấy **tối đa 3 FAQ**, loại nguồn dưới `FAQ_MIN_SCORE`; câu khớp chính xác chỉ cần mục tương ứng. Trước khi gọi API, bỏ lịch sử cũ rồi các nguồn xếp sau nếu vượt ngân sách; giữ nguyên nguồn tốt nhất. **Nguồn tham khảo** hiển thị đúng các mục thực sự được gửi vào LLM, mở từng mục để đối chiếu toàn bộ nội dung.
- Gửi nguồn đã chọn cùng tối đa 5 lượt hỏi/đáp gần nhất vào LLM. Giới hạn này áp dụng cả khi `.env` cũ đặt 24; có thể giảm qua `LLM_MAX_HISTORY_PAIRS`. Giao diện và terminal chỉ lưu 5 lượt trong bộ nhớ phiên.
- Streaming thật trên cả OpenAI và Ollama: đọc sự kiện/chunk từ API, giải mã phần `answer` trong JSON để hiển thị dần. Kiểm tra JSON hoàn chỉnh bằng Pydantic trước khi lưu vào lịch sử hoặc cache. Câu trả lời đang truyền chỉ là bản xem trước; UI thay bằng kết quả đã kiểm tra.
- Lời chào, cảm ơn và câu hỏi cách sử dụng có phản hồi thân thiện ngay, không chạy embeddings hay gọi LLM. Chỉ nhận diện toàn bộ câu đơn giản; lời chào kèm câu hỏi nghiệp vụ vẫn được tra FAQ. Gợi ý chủ đề giúp tiếp tục sau lời chào hoặc khi không tìm được nguồn.
- Nếu không có nguồn đủ điểm, trả ngay: **Mình chưa tìm thấy thông tin trong bộ FAQ hiện có.** Không gọi LLM trong trường hợp này. Nếu nguồn không đủ dữ kiện, prompt yêu cầu hỏi lại chi tiết cần thiết hoặc nói rõ thiếu dữ liệu. Ngưỡng tìm kiếm là heuristic, cần hiệu chỉnh trên FAQ thật; không bảo đảm mọi câu ngoài phạm vi đều bị lọc đúng.
- Câu nối tiếp như “giải thích thêm”, “tóm tắt”, “còn hạn thì sao” dùng chủ đề người dùng đã hỏi gần nhất; khi nêu chủ đề mới rõ ràng thì tìm chủ đề mới. Bot không dùng câu trả lời cũ làm nguồn chính sách. Có thể diễn giải, so sánh và tính toán từ FAQ, không thêm quy định chưa có.
- Gõ `/reset` hoặc chọn **Cuộc trò chuyện mới** để xóa lịch sử, câu hỏi đang chờ, trạng thái lỗi và cache phiên. Lựa chọn mức trả lời/bối cảnh cá nhân được giữ lại.
- Có thử lại khi lỗi API hoặc JSON sai. Phản hồi bị ngắt, chưa hoàn thành hoặc không đúng cấu trúc không được lưu/cache. Terminal giữ các lượt trước để người dùng gửi lại.
- Hỏi “Học phí của tôi là bao nhiêu?”: bot hỏi “Bạn đang học kỳ mấy?” và hiện nút chọn kỳ 0 (tiếng Anh), kỳ 1–8. Có thể chọn bất kỳ kỳ nào hoặc gõ “kỳ 3”/“3”/“kỳ ba” ngay sau câu hỏi lại. Nếu đã nói rõ “em đang học kỳ 3” trong lịch sử, bot không hỏi lại. Bot tra mức học phí theo FAQ; không xem mức này là công nợ cá nhân. Bước hỏi lại không gọi API.
- JSON, số token, thời gian tra FAQ và API chỉ hiện khi bật **Thông tin kết nối → Hiện chi tiết kỹ thuật**. Lỗi chỉ hiện một thông báo và một nút thử lại; không lưu lượt thất bại vào lịch sử.
- API key đọc từ `.env`, không nằm trong mã. FAQ là dữ liệu; các chỉ dẫn nằm trong FAQ không có quyền thay thế quy tắc chatbot.

## Cài đặt và chạy

Trên Windows, cài Python 3.13 bản 64-bit và chạy **start.bat**. Launcher tự tạo môi trường riêng của máy này, cài đúng phiên bản trong `requirements.txt` và tạo `.env` từ mẫu nếu chưa có. Nó giữ nguyên `.env` đang có. Không cần kích hoạt `.venv` hoặc đổi ExecutionPolicy.

```powershell
.\start.bat
.\start.bat --setup
.\start.bat --check
.\start.bat --port 8511
```

Mở [http://127.0.0.1:8510](http://127.0.0.1:8510); giữ cửa sổ chạy mở. `--setup` chỉ chuẩn bị môi trường; `--check` kiểm tra môi trường mà không cài thêm hoặc gọi API. Điền key/model của bạn trong `.env` để dùng LLM.

Trên macOS/Linux: `python3 run.py`. Terminal: `python run.py --cli` hoặc `start.bat --cli`. Python tối thiểu 3.10; đã kiểm thử trên Windows x64 với Python 3.13, chưa kiểm thử trực tiếp trên hệ điều hành/kiến trúc khác.

Chuyển sang máy khác bằng file **dist/Campus_FAQ_portable.zip**, tạo lại bằng `python scripts/package_project.py`. ZIP chứa nguồn, giao diện, FAQ và launcher, không chứa `.venv`, cache, Git hay API key. Máy đích cần Python và Internet cho lần cài/tải model đầu tiên; sau đó model nằm trong `.cache/embeddings`. Môi trường ảo cũ không dùng được sẽ được giữ trong `.venv.backup-*` trước khi tạo mới.

Xem hướng dẫn đầy đủ trong [CHAY_TREN_MAY_KHAC.md](CHAY_TREN_MAY_KHAC.md).

## FAQ do bạn chuẩn bị

`faq.md` có 33 mục: 11 FAQ hiện có do người dùng chỉnh sửa, 1 FAQ tra học phí theo kỳ, 7 FAQ quỹ tài trợ khởi nghiệp, 4 FAQ đổi lớp/chuyển lớp và 10 FAQ phòng hành chính. Phòng hành chính ở phòng 302L, tòa B theo thông tin người dùng cung cấp. Nội dung 11 FAQ cũ được giữ nguyên. Mức tài trợ, điều kiện quỹ, phí chuyển lớp và các chính sách chưa được cung cấp đều được nêu rõ. Bạn có thể thay dữ liệu demo bằng dữ liệu chính thức và cập nhật các mục theo cấu trúc:

```markdown
## Nhóm nghiệp vụ
### Câu hỏi
Câu trả lời có thể nhiều đoạn hoặc bảng.
```

Hoặc tạo `faq.json` ở thư mục project; khi tồn tại, file này được ưu tiên. Chấp nhận danh sách dưới đây hoặc object có khóa `faqs` chứa danh sách:

```json
[
  {"id": "faq-01", "question": "Câu hỏi của bạn", "answer": "Câu trả lời của bạn", "category": "Nhóm nghiệp vụ"}
]
```

`question` và `answer` bắt buộc là chuỗi không rỗng; `id` và `category` tùy chọn. Không cần sửa mã khi bạn thêm 20–30 FAQ. File đọc lại khi sửa; index embeddings được tái tạo theo nội dung. Không có bước sinh hoặc điền FAQ tự động. Không tạo sẵn `faq.json` để tránh che dữ liệu hiện tại.

## Cấu hình

Ollama cloud, sử dụng model tài khoản có quyền truy cập:

```env
LLM_PROVIDER=ollama
OLLAMA_API_KEY=key_cua_ban
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=ten_model_cua_ban
```

Ollama local: `OLLAMA_BASE_URL=http://localhost:11434`, có thể để key trống. Local nhận JSON schema qua `format`; cloud dùng chỉ dẫn JSON và kiểm tra cấu trúc tại ứng dụng.

OpenAI:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=key_cua_ban
OPENAI_MODEL=ten_model_cua_ban
```

Các lựa chọn chung:

```env
FAQ_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
FAQ_MIN_SCORE=0.35
LLM_MAX_HISTORY_PAIRS=5
LLM_INPUT_BUDGET=12000
LLM_OUTPUT_SHORT=350
LLM_OUTPUT_NORMAL=900
LLM_OUTPUT_DETAILED=2400
LLM_TIMEOUT_SECONDS=90
```

Khởi động lại sau khi đổi `.env`. Ngân sách input là ước tính, không phải context window hay quota của nhà cung cấp. Khi vượt ngân sách, bỏ lượt cũ rồi nguồn xếp sau; giữ nguyên câu hỏi và FAQ tốt nhất. Nếu riêng câu hỏi + FAQ tốt nhất quá lớn, yêu cầu rút gọn hoặc tăng ngân sách.

Cache câu trả lời riêng mỗi phiên: tối đa 32 mục, thời hạn 5 phút, khóa gồm model, endpoint, prompt, nguồn, bối cảnh và đầu vào. Khi hỏi lặp lại ngay câu vừa hỏi, lượt trùng được loại khỏi context để dùng lại kết quả có cùng cấu hình; thay FAQ, hồ sơ, mức trả lời hoặc API sẽ đổi khóa. Cache phân tích FAQ (16 bộ), index (4 bộ) và vector câu hỏi (256 câu) nằm trong bộ nhớ; vector dùng chung không lưu câu trả lời cá nhân. Đổi FAQ tái tạo index theo nội dung, không dùng dữ liệu cũ. OpenAI SDK dùng lại pool kết nối (tối đa 4 cấu hình). Thống kê thời gian chỉ là số đo thực tế của lần gọi, không bảo đảm tốc độ hoặc phần trăm tiết kiệm.

JSON gồm `answer`, `category` (`tuition`, `course_registration`, `student_services`, `other`) và `status` (`answered`, `unknown`, `clarify`, `out_of_scope`; `error` chỉ dành cho fallback ứng dụng). JSON validation kiểm tra cấu trúc, không xác minh nội dung đúng/sai.

## Kiểm thử

```powershell
python -m unittest discover -s tests -v
```

Kiểm thử dùng mock API/embeddings để không tốn quota. Bao gồm nguồn chính xác/tối đa 3 nguồn, ngưỡng liên quan, đọc lại FAQ, câu nối tiếp, tối đa 5 lượt, reset, streaming Unicode, stream bị ngắt, retry, cache, ngân sách và JSON validation.

Đánh giá với model embeddings đã cache trên máy (không tải mạng, không gọi API):

```powershell
.\.venv\Scripts\python.exe scripts/check_retrieval.py
```

Bộ smoke evaluation gồm 6 cách hỏi về học phí, công nợ, đăng ký môn không dấu, giấy xác nhận, quỹ khởi nghiệp và phí chuyển lớp. Kết quả kiểm tra hiện tại: 6/6 có nguồn kỳ vọng trong tối đa 3 mục; câu lặp sử dụng cache vector. Đây là tập mẫu nhỏ, không đại diện cho mọi cách hỏi. Lần nạp model đầu tiên vẫn có thể chậm hơn những lần tra cứu khi model đã ở trong bộ nhớ.

Các file `token_optimization_report.md` và `token_optimization_baseline.json` là số đo của phiên bản trước; không dùng chúng để khẳng định mức tiết kiệm của luồng embeddings mới.

Tài liệu triển khai: [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses), [Ollama chat](https://docs.ollama.com/api/chat), [model embeddings](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).

Nguyên tắc tối ưu: lọc context và giảm lượt gọi theo [OpenAI latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization); gửi nội dung một lần bằng [Streamlit forms](https://docs.streamlit.io/develop/concepts/architecture/forms). Không đổi model hoặc key hiện có và không tự thêm bước gọi LLM để phân loại câu hỏi.
