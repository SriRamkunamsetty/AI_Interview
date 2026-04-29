from fastapi import APIRouter, UploadFile, File, Form
import whisper, tempfile, os
from difflib import SequenceMatcher

router = APIRouter()
model = whisper.load_model("small")

def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def fix_name(text, name):
    words = text.split()
    for i, w in enumerate(words):
        if similarity(w, name) > 0.75:
            words[i] = name
    return " ".join(words)

@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    candidate_name: str = Form(...)
):
    data = await audio.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
        f.write(data)
        path = f.name

    result = model.transcribe(
        path,
        language="en",
        task="transcribe",
        fp16=False,
        initial_prompt=(
            f"This is a job interview. "
            f"The candidate's name is {candidate_name}. "
            f"Proper nouns and technical terms may appear."
        )
    )

    os.remove(path)

    text = result["text"].strip()
    text = fix_name(text, candidate_name)

    return {"text": text}
