# Voice-over (Kokoro, through the engine's `tts`)

Free, on this computer, no account. The voice model (Kokoro-82M, Apache-2.0) downloads once on first use.

```bash
PY=$(python3 <kit-to-clip>/scripts/toolbox.py path kokoro-voice python)
HYPERFRAMES_PYTHON="$PY" npx hyperframes tts script.txt -v am_michael -o assets/voice.wav --json
HYPERFRAMES_PYTHON="$PY" npx hyperframes tts --list                     # the voices
```

| Voice | Sound | Language |
|---|---|---|
| `af_heart`, `af_nova`, `af_sky` | female, US | `en-us` |
| `am_adam`, `am_michael` | male, US | `en-us` |
| `bf_emma`, `bf_isabella` | female, UK | `en-gb` |
| `bm_george` | male, UK | `en-gb` |
| `ef_dora` | Spanish | `es` |
| `ff_siwis` | French | `fr-fr` |
| `jf_alpha` | Japanese | `ja` |
| `zf_xiaobei` | Chinese | `zh` |

`-s 1.1` speeds the voice up. Short sentences sound most natural.

## Voice first, picture second (explainers, narrated posts)
1. Write the script with the person (✋ the words before any audio).
2. Make the voice, then transcribe it for word timings: `npx hyperframes transcribe assets/voice.wav -d <project>`
   (card `hf-transcribe`) writes `transcript.json`.
3. Put each scene or key word on its word time with `data-anchor` and `data-at`. `finish.py anchors` then proves every
   visual lands on its word.
4. Music under a voice: duck the music about 10 dB under speech, or use no music. Keep one main sound source when the
   video is mostly watched muted with captions.
5. Burn in captions from the same transcript (`embedded-captions`).

## Rules
- **It's a synthetic voice: say so** when the person shares the video publicly, if they or the platform need it
  disclosed. Never imitate a real person's voice.
- **Listening:** the voice is unheard by the agent until the person listens (✋ listening checkpoint, as for music).
- **Tested 2026-10-08:** a 4-word line in `am_michael` gave a clean WAV longer than 0.8 s. Install 160 MB, plus the
  model on first use.
