import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import uvicorn

if __name__ == "__main__": 
    uvicorn.run("main.main:app", host="127.0.0.1", port=7000, reload=True, log_level="debug")