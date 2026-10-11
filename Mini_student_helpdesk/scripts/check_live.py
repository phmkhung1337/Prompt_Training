"""Explicit live API smoke check. Run manually; consumes the configured API quota."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import llm_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", nargs="+", help="Non-sensitive academic questions")
    parser.add_argument("--show-invalid", action="store_true", help="Print invalid final content for these test questions")
    parser.add_argument("--ui", action="store_true", help="Submit questions as one real Streamlit conversation")
    args = parser.parse_args()
    print(json.dumps(llm_client.get_runtime_info(), ensure_ascii=False), flush=True)
    original_post = llm_client.httpx.post
    diagnostics = {}
    final_content = ""

    def capture(*args, **kwargs):
        nonlocal final_content
        response = original_post(*args, **kwargs)
        diagnostics["http_status"] = response.status_code
        if response.status_code == 200:
            data = response.json()
            message = data.get("message", {})
            final_content = message.get("content", "")
            diagnostics.update(done_reason=data.get("done_reason"),
                               content_chars=len(message.get("content", "")),
                               has_thinking=bool(message.get("thinking")))
        return response

    llm_client.httpx.post = capture
    failures = 0
    try:
        app = None
        if args.ui:
            from streamlit.testing.v1 import AppTest
            app = AppTest.from_file(str(Path(llm_client.PROJECT_DIR) / "app.py")).run(timeout=120)
            if app.exception:
                raise llm_client.HelpdeskError("Streamlit initialization failed")
        for question in args.questions:
            stats = {}
            diagnostics.clear()
            final_content = ""
            try:
                if app is None:
                    result = llm_client.ask_student(question, [], request_stats=stats)
                else:
                    app.text_area(key="draft_question").set_value(question).run(timeout=120)
                    app.button(key="send_question").click().run(timeout=120)
                    if app.exception or app.session_state["failed_question"]:
                        raise llm_client.HelpdeskError(app.session_state["last_error"] or "Streamlit execution failed")
                    message = app.session_state["messages"][-1]
                    result = message["response_json"]
                    stats = message["runtime_info"]["request_stats"]
                failures += result["status"] != "answered"
                outcome = {"response": result}
                if args.show_invalid and result["status"] == "error":
                    outcome["invalid_content"] = final_content
            except llm_client.HelpdeskError as exc:
                failures += 1
                outcome = {"error": str(exc)}
            print(json.dumps({"question": question, **outcome, "stats": stats,
                              "diagnostics": diagnostics}, ensure_ascii=False), flush=True)
    finally:
        llm_client.httpx.post = original_post
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())
