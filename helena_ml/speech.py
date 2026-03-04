"""
Speech I/O for HELENA (optional stub)
"""
def speak(text: str):
    print(f"[TTS] {text}")

def listen() -> str:
    return input("[STT] You: ")
