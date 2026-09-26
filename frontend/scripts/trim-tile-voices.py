"""Trim generated PCM voice clips while keeping short margins around speech."""

from pathlib import Path
import wave


VOICE_DIR = Path(__file__).resolve().parents[1] / "public" / "audio" / "tiles"

for path in VOICE_DIR.glob("*.wav"):
    with wave.open(str(path), "rb") as source:
        params = source.getparams()
        if params.nchannels != 1 or params.sampwidth != 2:
            raise ValueError(f"Expected mono 16-bit PCM: {path}")
        frames = source.readframes(params.nframes)
    samples = memoryview(frames).cast("h")
    peak = max((abs(sample) for sample in samples), default=0)
    if not peak:
        raise ValueError(f"Silent voice clip: {path}")
    audible = [index for index, sample in enumerate(samples) if abs(sample) >= peak * 0.015]
    start = max(0, audible[0] - int(params.framerate * 0.05))
    end = min(len(samples), audible[-1] + int(params.framerate * 0.15))
    with wave.open(str(path), "wb") as output:
        output.setparams(params)
        output.writeframes(frames[start * 2:end * 2])

print(f"Trimmed {len(list(VOICE_DIR.glob('*.wav')))} voice clips")
