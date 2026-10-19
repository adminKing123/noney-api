from datetime import datetime, timedelta, timezone
import base64
import wave

IST = timezone(timedelta(hours=5, minutes=30))

def nearest_15_min():
    now = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(IST)
    rounded = now + timedelta(minutes=7.5)
    rounded = rounded.replace(minute=(rounded.minute // 15) * 15, second=0, microsecond=0)
    return rounded.strftime("%I:%M %p").lstrip("0")

def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

def wav_to_base64(filepath):
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
