import http.server
import ssl
import os

# Change to the directory with your files
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class NoCacheHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Serves files with no-cache headers so the browser always gets the latest version."""
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

# Set up the server
server_address = ('0.0.0.0', 3000)
# Use ThreadingHTTPServer to handle multiple requests concurrently
httpd = http.server.ThreadingHTTPServer(server_address, NoCacheHTTPRequestHandler)

# Add SSL
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(certfile='cert.pem', keyfile='key.pem')
httpd.socket = context.wrap_socket(httpd.socket, server_side=True)

print(f"Serving HTTPS on port {server_address[1]} (no-cache mode)...")
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\nServer stopped by user.")
    httpd.server_close()