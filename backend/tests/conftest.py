import os
import sys

# Ensure backend root is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("SMTP_HOST", "smtp.test.company.com")
os.environ.setdefault("SMTP_USER", "noreply@company.com")

try:
    from app.config import settings
    if not settings.SMTP_HOST:
        settings.SMTP_HOST = "smtp.test.company.com"
    if not settings.SMTP_USER:
        settings.SMTP_USER = "noreply@company.com"
except Exception:
    pass
