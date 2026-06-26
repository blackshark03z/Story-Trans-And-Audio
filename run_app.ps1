$ErrorActionPreference = "Stop"
$Python = "D:\Youtube\VieNeu-TTS\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Không tìm thấy môi trường VieNeu tại $Python"
}
$env:STORY_AUDIO_ALLOW_LIVE_DB = "1"
& $Python -m story_audio.main @args
