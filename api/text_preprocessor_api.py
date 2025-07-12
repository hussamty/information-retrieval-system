from fastapi import FastAPI
from pydantic import BaseModel
import sys
import os

# Add the parent directory to the Python path to allow for absolute imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.text_preprocessor import TextPreprocessor

app = FastAPI()
preprocessor = TextPreprocessor()

class Query(BaseModel):
    text: str

@app.post("/preprocess/")
async def preprocess_text(query: Query):
    processed_text = preprocessor.preprocess(query.text)
    return {"processed_text": processed_text}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
