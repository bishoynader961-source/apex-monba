"""Local development server launcher."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "archive"))
os.environ["WEBHOOK_TEST_MODE"] = "1"
os.environ["SERVER_ADMIN_SECRET"] = "test123"
os.environ["SMTP_HOST"] = ""

from server_app import app

if __name__ == "__main__":
    print("=" * 60)
    print("  PharmacyPro Local Dev Server")
    print("  http://127.0.0.1:5000")
    print("  http://127.0.0.1:5000/terms")
    print("  http://127.0.0.1:5000/privacy")
    print("  http://127.0.0.1:5000/refund")
    print("  http://127.0.0.1:5000/admin")
    print("  http://127.0.0.1:5000/portal")
    print("=" * 60)
    app.run(host="127.0.0.1", port=5000, debug=False)
