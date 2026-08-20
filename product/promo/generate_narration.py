import os
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs


load_dotenv()
# ELEVENLABS_API_KEY="sk_47f202f32b7ff3ffb05cce82291a8e89516ab2c0c83678bc"
API_KEY = os.getenv("ELEVENLABS_API_KEY")

# תחליף לזה את ה-Voice ID שתבחר ב-ElevenLabs
VOICE_ID = "FVmoZ3rdjE40rie2ICby"

OUTPUT_DIR = Path(__file__).resolve().parent / "narration"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

client = ElevenLabs(api_key=API_KEY)


SCENES = [
    # v2 — "The Loss We Published" (creative_v2.md). 45s continuous timeline.
    # Delivery notes are in creative_v2.md; punctuation carries the pacing.
    {
        "file": "scene_01.mp3",
        "start": "00:00",
        "end": "00:06",
        "text": "This is one of our losses. We published it. On purpose.",
    },
    {
        "file": "scene_02.mp3",
        "start": "00:06",
        "end": "00:12",
        "text": "Because the wins mean nothing… unless you see everything.",
    },
    {
        "file": "scene_03.mp3",
        "start": "00:12",
        "end": "00:22",
        "text": "Every night, Diago redraws the trendlines on two thousand, two hundred and fifty-nine stocks. When a price breaks its diagonal — Diago catches it.",
    },
    {
        "file": "scene_04.mp3",
        "start": "00:22",
        "end": "00:31",
        "text": "You get one alert. One score — built from seventy-two thousand historical setups. Six means decent. Ten means rare.",
    },
    {
        "file": "scene_05.mp3",
        "start": "00:31",
        "end": "00:38",
        "text": "It works on support too. Price falls to its rising line, holds — and bounces. Diago's strongest setup.",
    },
    {
        "file": "scene_06.mp3",
        "start": "00:38",
        "end": "00:45",
        "text": "Diago. Seven days free — no card. Then five dollars a month. Every signal public. Even the losses.",
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