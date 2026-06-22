$ErrorActionPreference = "Stop"
$Python = "D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Không tìm thấy môi trường VieNeu tại $Python"
}
& $Python -m story_audio.main @args
