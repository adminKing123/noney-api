from dotenv import load_dotenv
load_dotenv()

import os
import code
from db import db
from config import CONFIG

class ClearCommand:
    def __repr__(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        return ""

clear = ClearCommand()

debug_status = "ON" if CONFIG.get("DEBUG") else "OFF"

banner = rf"""
====================================================================
                    🚀  N O N E Y  S H E L L  🚀
====================================================================

Welcome to the Noney interactive shell!

Debug Mode: {debug_status}

Available Objects:

  • CONFIG — Loaded environment & project configuration
  • db     — database controller

====================================================================
"""

code.interact(local=globals(), banner=banner)
