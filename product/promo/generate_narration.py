import os
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs


load_dotenv()

API_KEY = os.getenv("ELEVENLABS_API_KEY")

# תחליף לזה את ה-Voice ID שתבחר ב-ElevenLabs
VOICE_ID = "FVmoZ3rdjE40rie2ICby"

OUTPUT_DIR = Path(__file__).resolve().parent / "narration"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = ElevenLabs(api_key=API_KEY)


SCENES = [
    # texts sized for the 60-second cut at a NATURAL speaking pace (~2.4 w/s):
    # no atempo compression needed. Windows match the 60s film timeline.
    {
        "file": "scene_01.mp3",
        "start": "00:00",
        "end": "00:07",
        "text": """
Every chart hides a line — a diagonal.

And when price breaks it... things happen.
""".strip(),
    },
    {
        "file": "scene_02.mp3",
        "start": "00:07",
        "end": "00:15",
        "text": """
More than two thousand stocks are worth watching.

You can't watch them all. Nobody can.
""".strip(),
    },
    {
        "file": "scene_03.mp3",
        "start": "00:15",
        "end": "00:28",
        "text": """
This is Diago. Every night, it redraws the trendlines of over two thousand stocks.

And when one closes above its diagonal —

you get the alert. With a score.
""".strip(),
    },
    {
        "file": "scene_04.mp3",
        "start": "00:28",
        "end": "00:38",
        "text": """
It works the other way too.

A stock falls back to its rising support line... holds, and bounces.

Diago's strongest setup.
""".strip(),
    },
    {
        "file": "scene_05.mp3",
        "start": "00:38",
        "end": "00:49",
        "text": """
Every signal gets a calibrated confidence score.

And every signal is tracked publicly — winners and losers.

Nothing deleted. Ever.
""".strip(),
    },
    {
        "file": "scene_06.mp3",
        "start": "00:49",
        "end": "01:00",
        "text": """
Diago. Your ranked shortlist, ready before the market opens.

Seven days free, then five dollars a month.

Statistics — not promises. Never investment advice.
""".strip(),
    },
]


def generate_scene(scene):
    print(
        f"Generating {scene['file']} "
        f"({scene['start']} → {scene['end']})..."
    )

    audio = client.text_to_speech.convert(
        voice_id=VOICE_ID,
        text=scene["text"],
        model_id="eleven_v3",
        output_format="mp3_44100_128",
    )

    output_path = OUTPUT_DIR / scene["file"]

    # write to a temp file, then atomically replace — an interrupted run
    # can never leave a truncated/empty mp3 behind
    tmp_path = output_path.with_suffix(".tmp")
    with open(tmp_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)
    if tmp_path.stat().st_size == 0:
        tmp_path.unlink()
        raise RuntimeError(f"empty audio received for {scene['file']}")
    os.replace(tmp_path, output_path)

    print(f"✓ {output_path}")


def main():
    if not API_KEY:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is missing. "
            "Add it to your .env file."
        )

    for scene in SCENES:
        generate_scene(scene)

    print("\nDone.")
    print(f"Narration files saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()