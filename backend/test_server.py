from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
async def read_root():
    return {"message": "Test server is running!"}

@app.post("/test-endpoint")
async def test_endpoint():
    return {"status": "success", "message": "Test endpoint is working!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004, log_level="info")
