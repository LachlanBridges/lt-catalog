import os
from dotenv import load_dotenv
from library_data.config import DATA_ROOT

# Load env from CWD (.env) and from data root if present; env vars override
load_dotenv()  # default search from CWD upwards
try:
    load_dotenv(DATA_ROOT / ".env")
except Exception:
    pass

LT_TOKEN = os.getenv("LT_TOKEN")
UA = os.getenv("UA", "library-data/levels (+mailto:you@example.com)")
