"""
Rasterize film.html into diago_promo.mp4.

Technique: the film runs on one deterministic 88s CSS timeline, so freezing it
at time T is just `animation-delay:-Ts + animation-play-state:paused` on every
element. To render fast we stack BATCH frozen copies of the stage on one tall
page (each copy frozen at its own consecutive timestamp), take ONE headless-
Chrome screenshot per page, and slice it into frames with PIL. ffmpeg (bundled
via imageio-ffmpeg) assembles the frames into H.264.

Usage: python3 -m product.promo.render_film
"""
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image
import imageio_ffmpeg

FPS = 15
D = 88.0
W, H = 1280, 720
BATCH = 15                     # frames per screenshot page (15*720 = 10800px tall)
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    film = open(os.path.join(HERE, 'film.html'), encoding='utf-8').read()
    m = re.search(r'<body>(.*)</body>', film, re.S)
    stage_html = m.group(1)
    head = film[:film.index('<body>')]

    total = int(D * FPS)
    workdir = tempfile.mkdtemp(prefix='diago_film_')
    frames_dir = os.path.join(workdir, 'frames')
    os.makedirs(frames_dir, exist_ok=True)
    print(f'{total} frames @ {FPS}fps -> {workdir}')

    n_pages = (total + BATCH - 1) // BATCH
    for p in range(n_pages):
        copies, css = [], []
        for k in range(BATCH):
            f = p * BATCH + k
            if f >= total:
                break
            t = f / FPS
            copies.append(f'<div class="frwrap" id="fr{k}">{stage_html}</div>')
            css.append(f'#fr{k}, #fr{k} * {{ animation-delay:-{t:.4f}s !important; '
                       f'animation-play-state:paused !important; }}')
        page = (head + f'<style>.frwrap {{ width:{W}px; height:{H}px; overflow:hidden; }} '
                + ' '.join(css) + '</style><body>' + ''.join(copies) + '</body></html>')
        page_path = os.path.join(workdir, f'page_{p}.html')
        with open(page_path, 'w', encoding='utf-8') as fh:
            fh.write(page)
        shot = os.path.join(workdir, f'page_{p}.png')
        subprocess.run([CHROME, '--headless', '--disable-gpu', f'--screenshot={shot}',
                        f'--window-size={W},{len(copies) * H}', '--hide-scrollbars',
                        f'file://{page_path}'],
                       check=True, capture_output=True)
        im = Image.open(shot)
        for k in range(len(copies)):
            f = p * BATCH + k
            im.crop((0, k * H, W, (k + 1) * H)).save(
                os.path.join(frames_dir, f'f_{f:05d}.png'))
        im.close()
        os.remove(shot)
        os.remove(page_path)
        if p % 10 == 0 or p == n_pages - 1:
            print(f'  page {p + 1}/{n_pages} done', flush=True)

    out = os.path.join(HERE, 'diago_promo.mp4')
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([ffmpeg, '-y', '-framerate', str(FPS),
                    '-i', os.path.join(frames_dir, 'f_%05d.png'),
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '19',
                    '-movflags', '+faststart', out],
                   check=True, capture_output=True)
    size = os.path.getsize(out) / 1e6
    print(f'✅ {out} ({size:.1f} MB, {D:.0f}s @ {FPS}fps)')


if __name__ == '__main__':
    main()
