from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import json
import subprocess
import tempfile
import os
from datetime import datetime


class Handler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        json_file_path = None

        try:
            data = json.loads(post_data)
            print("Received JSON:", data)

            # # Create a JSON file in the open_rm_auto directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_file_path = f'../bug_data_{timestamp}.json'
            with open(json_file_path, 'w') as json_file:
                json.dump(data, json_file, indent=2)
            result = subprocess.run(['python3', '../create_rm_bug.py', json_file_path],
                                    capture_output=True, text=True)

            response = {
                "status": "success",
                "output": result.stdout,
                "errors": result.stderr if result.stderr else None,
                "return_code": result.returncode
            }
            print(response)
        except json.JSONDecodeError as e:
            response = {"status": "error", "message": f"Invalid JSON: {str(e)}"}
        except Exception as e:
            response = {"status": "error", "message": str(e)}
        finally:
            if json_file_path and os.path.exists(json_file_path):
                try:
                    os.unlink(json_file_path)
                except Exception as e:
                    print(f"Warning: Could not delete temp file {json_file_path}: {e}")

        self._set_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))


def run(server_class=HTTPServer, handler_class=Handler):
    server_address = ('0.0.0.0', 8443)
    httpd = server_class(server_address, handler_class)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile='server.crt', keyfile='private.key')
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

    print("HTTPS server running on https://0.0.0.0:8443")
    httpd.serve_forever()


if __name__ == '__main__':
    run()
