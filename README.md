# ASCII yolka

A rotating New Year tree made of digits and math symbols. Press a key and it assembles itself out of a swirl of characters, then the garland lights up, presents drop from the sky and the snow keeps falling.

![ASCII yolka](docs/yolka.gif)

**Live in the browser:** https://mmm0bucks.github.io/ascii-yolka/ (first load takes a while: it downloads Python and numpy compiled to WebAssembly).

## Run locally

Python 3.10+.

```
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python yolka/main.py
```

With [uv](https://docs.astral.sh/uv/) it is one line, no setup: `uv run yolka/main.py`.

| Key | Action |
|---|---|
| `Space` / click | assemble the tree, then pause |
| `R` | assemble again |
| `S` | save a screenshot |
| drag the mouse | rotate |
| `Esc` | quit |

The greeting is the `GREETING` constant at the top of `yolka/main.py`.

## How it works

1. The scene is a 3D point cloud of about 37,000 points: ground, trunk, tiers of drooping branches, two garland spirals, 170 bulbs, baubles, a star, five presents and snow.
2. Every frame the points are rotated, projected with perspective onto an 88×74 character grid, and a z-buffer keeps the nearest point in each cell.
3. The character is picked by brightness (Lambert shading). The ramp is sorted by real glyph coverage measured from the font, so dark areas get `. : -` and bright ones get `8 # @`, with `∑ ∫ √ ∞ π` in between.
4. The whole frame is composed from a glyph atlas in one numpy expression; the glow is the frame downscaled, upscaled and added to itself.

The same file runs in the browser through [pygbag](https://pygame-web.github.io/) (pygame compiled to WebAssembly). The GitHub Actions workflow in `.github/workflows/pages.yml` builds it and publishes to GitHub Pages on every push to `main`.

## Credits

Inspired by an ASCII Christmas tree reel signed `wcminh.ascii`; the code here is written from scratch. The bundled font is DejaVu Sans Mono, see `docs/DejaVu-LICENSE.txt`.

MIT License.
