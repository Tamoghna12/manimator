import logging
import os
import webbrowser

from manimator.web.app import app

log = logging.getLogger(__name__)


def main():
    host = os.environ.get("MANIMATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("MANIMATOR_PORT", "5100"))
    log.info("Starting web UI at http://%s:%d", host, port)
    webbrowser.open(f"http://localhost:{port}")
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
