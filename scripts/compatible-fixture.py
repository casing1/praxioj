#!/usr/bin/env python3
"""Loopback-only Chat Completions TEST FIXTURE, not an LLM or production service.

Runs without keys, never makes outbound requests, and returns a deterministic
write-file tool call followed by a completion. Usage values are synthetic test
data; --omit-usage exercises providers that do not report token usage.
"""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time


class FixtureServer(ThreadingHTTPServer):
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--delay", type=float, default=0)
    parser.add_argument("--omit-usage", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.delay <= 120:
        parser.error("delay must be between 0 and 120 seconds")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log request bodies, authorization headers, or arbitrary URLs.

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.respond(404, {"error": {"message": "Unknown fixture route"}})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 262_144:
                    self.respond(413, {"error": {"message": "Fixture request size exceeded"}})
                    return
                request = json.loads(self.rfile.read(size))
                messages = request["messages"]
                if not isinstance(messages, list) or not messages:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                self.respond(400, {"error": {"message": "Invalid fixture request"}})
                return
            time.sleep(args.delay)
            tools = {tool.get("function", {}).get("name") for tool in request.get("tools", [])}
            if messages[-1].get("role") == "tool":
                message = {"role": "assistant", "content": "The test fixture has saved plan.txt. Review it before submitting."}
                finish_reason = "stop"
            elif "write_file" in tools:
                message = {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "fixture_write_plan", "type": "function", "function": {
                        "name": "write_file", "arguments": json.dumps({
                            "path": "plan.txt",
                            "content": "Goal: deliver the release. Verification: run the checks. Risk: prepare a rollback.",
                        }),
                    }}],
                }
                finish_reason = "tool_calls"
            else:
                message = {"role": "assistant", "content": "This is a local protocol fixture. No model inference was performed."}
                finish_reason = "stop"
            response = {
                "id": "fixture-completion", "object": "chat.completion",
                "model": request.get("model", "fixture-model"),
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            }
            if not args.omit_usage:
                response["usage"] = {"prompt_tokens": 37, "completion_tokens": 12, "total_tokens": 49}
            self.respond(200, response)

        def respond(self, status, body):
            data = json.dumps(body).encode()
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Client cancellation is expected in fixture-based tests.

    server = FixtureServer(("127.0.0.1", args.port), Handler)
    print(f"TEST FIXTURE ONLY: http://127.0.0.1:{server.server_port}/v1 (no LLM, no outbound calls)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
