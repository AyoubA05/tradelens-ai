#!/usr/bin/env bash
#
# Bake a ping-pong ("boomerang") loop into a background video.
#
# Why this is a build step and not JavaScript: reversing at runtime means
# stepping currentTime backwards, and H.264 only decodes forward — every step
# back can mean re-decoding from the previous keyframe. Measured on
# site/assets/ai-loop.mp4 that froze the picture for up to 3.2 seconds at a
# time, which is worse than the hard cut it was meant to remove. There is also
# no negative playbackRate in any shipping browser. Baking the reverse into the
# file makes the whole thing an ordinary forward decode with plain `loop`.
#
# The reversed half drops its first and last frame. Without that, the turn
# repeats the end frame and the wrap repeats the start frame — two visible
# hitches per cycle, in the exact places this is supposed to smooth out.
#
# Audio is dropped: these play muted, and the source carried a 132 kb/s AAC
# track nobody will ever hear.
#
# Usage:  scripts/bake_boomerang.sh in.mp4 out.mp4 [crf]
#
# ffmpeg is not a project dependency and is not installed system-wide. If it is
# not on PATH this falls back to the static binary vendored by the
# imageio-ffmpeg wheel:  python3 -m pip install imageio-ffmpeg

set -euo pipefail

IN=${1:?usage: bake_boomerang.sh in.mp4 out.mp4 [crf]}
OUT=${2:?usage: bake_boomerang.sh in.mp4 out.mp4 [crf]}
# 24 was chosen against the source by SSIM (0.986) rather than by eye. These
# clips sit behind a heavy scrim, but they are also dark gradients, which band
# before anything else does — hence a lower CRF than ambience would suggest.
CRF=${3:-24}

FF=$(command -v ffmpeg || python3 -c \
  'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null || true)
if [ -z "$FF" ]; then
  echo "No ffmpeg. Install it, or: python3 -m pip install imageio-ffmpeg" >&2
  exit 1
fi

FRAMES=$("$FF" -hide_banner -i "$IN" -map 0:v -c copy -f null - 2>&1 |
  grep -oE 'frame=[[:space:]]*[0-9]+' | tail -1 | grep -oE '[0-9]+')
if [ -z "$FRAMES" ] || [ "$FRAMES" -lt 3 ]; then
  echo "Could not read a usable frame count from $IN" >&2
  exit 1
fi

echo "$IN: $FRAMES frames -> $(( FRAMES * 2 - 2 )) frames at crf $CRF"

"$FF" -hide_banner -loglevel error -y -i "$IN" \
  -filter_complex "[0:v]split[a][b];\
[b]reverse,trim=start_frame=1:end_frame=$(( FRAMES - 1 )),setpts=PTS-STARTPTS[r];\
[a][r]concat=n=2:v=1[v]" \
  -map "[v]" -an \
  -c:v libx264 -preset slow -crf "$CRF" -pix_fmt yuv420p -movflags +faststart \
  "$OUT"

echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"
