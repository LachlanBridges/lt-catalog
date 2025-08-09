import os
from dotenv import load_dotenv
load_dotenv()  # loads .env from project root
LT_TOKEN = os.getenv("LT_TOKEN")
UA = os.getenv("UA", "library-data/levels (+mailto:you@example.com)")
