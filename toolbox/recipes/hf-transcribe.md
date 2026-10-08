# Transcription and captions (HyperFrames transcribe)

```bash
npx hyperframes transcribe <clip.mp4|audio.wav> -d <project> --json        # writes <project>/transcript.json (word timings)
npx hyperframes transcribe <clip.mp4> -d <project> --to srt -o captions.srt # a sidecar for LinkedIn and YouTube
npx hyperframes transcribe captions.srt -d <project>                       # import an existing transcript instead
```

Then the `embedded-captions` skill (in `$REEL_STUDIO/.claude/skills/`) styles burned-in captions from `transcript.json`.

## Engines
- **Parakeet (card `parakeet`, Apple silicon, recommended):** fast and accurate, no Homebrew needed. Point HyperFrames
  at it:
  ```bash
  HYPERFRAMES_PARAKEET="$(python3 <kit-to-clip>/scripts/toolbox.py path parakeet cli)" npx hyperframes transcribe clip.mp4 -d <project> --json
  ```
  The first run downloads the model (`parakeet-tdt-0.6b-v3`, about 600 MB, CC-BY-4.0). When captions made with it
  ship, credit "speech recognition: NVIDIA Parakeet (CC-BY-4.0)" in the project's `CREDITS.md`. It covers 25
  European languages; `-l <code>` filters to one.
- **whisper.cpp (card `hf-transcribe`):** used when `whisper-cli` is on the PATH. With Homebrew present,
  `toolbox.py install hf-transcribe` runs `brew install whisper-cpp` after a ✋ yes. Never install Homebrew itself.
  Models download into `~/.cache/hyperframes/whisper`. The default is `small.en`; use `-m medium.en` for noisy sport
  audio.
- **Video reader's Whisper (card `video-reader-tools`):** for `reference.py` and the media fetcher, not for captions.

## Lessons (tested 2026-10-08)
- **Parakeet** transcribed a spoken 8-word line perfectly, with word start times every 0.2-0.5 s. That is the
  precision captions and voice-anchored scenes (`data-anchor` words) need.
- **A padel clip with crowd noise gave 1 word in 8 s.** That was correct: nobody spoke. Check `wordCount` before
  promising captions, and say "no speech found" plainly.
- **Burned-in captions matter:** most feed video is watched without sound (LinkedIn says 79%, 2021 data).
