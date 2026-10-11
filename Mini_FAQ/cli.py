"""Terminal Campus FAQ Assistant: python cli.py."""

import sys

import llm_client


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    history, cache = [], {}
    print("Campus FAQ Assistant · /reset: xóa hội thoại · /exit: thoát")

    def sources(hits, relevant):
        print(f"\n{len(hits)} FAQ tham khảo:")
        for i, hit in enumerate(hits, 1):
            print(f"{i}. {hit['question']} (điểm tìm kiếm: {hit['score']:.3f})")
            print(hit["answer"])
        if not relevant:
            print("Không có FAQ đạt ngưỡng liên quan.")
        print("\nTrợ lý: ", end="", flush=True)

    while True:
        try:
            question = input("\nBạn: ").strip()
            if question.lower() in {"/exit", "/quit"}:
                break
            if question.lower() == "/reset":
                history.clear()
                cache.clear()
                print("Đã xóa lịch sử hội thoại và cache phiên.")
                continue
            if not question:
                continue
            preview = []

            def show_delta(text):
                preview.append(text)
                print(text, end="", flush=True)

            result = llm_client.ask_student(
                question, history, response_cache=cache, on_sources=sources,
                on_delta=show_delta,
            )
            print()
            if result["status"] == "error":
                print(result["answer"])
                continue
            # The final JSON is authoritative; streamed fragments are a preview.
            if "".join(preview).strip() != result["answer"]:
                print(result["answer"])
            history.extend([{"role": "user", "content": question},
                            {"role": "assistant", "content": result["answer"]}])
            history[:] = history[-llm_client.MAX_HISTORY_MESSAGES:]
        except llm_client.HelpdeskError as exc:
            print(f"\nLỗi: {exc}")
        except (EOFError, KeyboardInterrupt):
            print("\nĐã thoát.")
            break


if __name__ == "__main__":
    main()
