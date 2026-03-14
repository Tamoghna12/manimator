from vidgen.web.app import app
import webbrowser

port = 5100
print(f"[vidgen] Starting web UI at http://localhost:{port}")
webbrowser.open(f"http://localhost:{port}")
app.run(host="0.0.0.0", port=port, debug=False)
