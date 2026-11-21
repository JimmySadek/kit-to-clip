# Voice-over: supplied, guided or local

Read only when the story needs speech. An existing approved recording skips generation. A silent or music-led
video can have no voice. Prepare `script.txt` with exact spoken words and `voice-direction.md` with performance
instructions, pronunciation, pace, emotion and intended audience. Keep these separate so stage directions are
not accidentally spoken. Record both in the film's brief (`film.json`).

## Supplied recording

Inspect the supplied file and retain its original. Ask the person to listen and approve the actual take. Use its
measured duration and word timings for a narration-led edit; do not force the reading into musical bars. A voice
replacement reopens the voice choice, the affected storyboard frames, the music pick and the ✋ final film.

## Guided Google AI Studio (optional external route)

Only offer to open the service after the person chooses it. Explain that the script and delivery instructions go
to Google, and that account access, availability and pricing are determined by Google. Do not upload private
assets or create keys. If browser interaction is unavailable, give the link and a copyable handoff instead.

1. Open [Google AI Studio speech generation](https://aistudio.google.com/generate-speech), or follow its current
   speech-generation entry point if that link has moved. Inspect the actual interface before naming controls.
2. Choose a single speaker for ordinary narration. Put exact words in the transcript field and the delivery
   direction in its separate style/instructions field. Use a currently offered TTS model and audition voices.
3. Generate a short representative passage first. Check names, acronyms, tone, pauses and intelligibility by
   listening. Revise direction before generating the approved full script. No background soundtrack in this take.
4. Download the approved audio, preferably WAV if offered. Return that file, the exact script and voice/model
   settings to the project. Do not treat a player link or a successful generation message as the audio asset.
5. Inspect the returned recording, check the spoken words and actual length, then transcribe locally for timing.
   Record the agreed take in `film.json`. Align visuals to this take, then mix approved music/effects.

Google documents controlled TTS delivery and separate styling in its
[speech-generation guide](https://ai.google.dev/gemini-api/docs/speech-generation) (checked 20 October 2026).
Recheck the interface/model options when used. This guided path does not install an API integration or guarantee
free access. The local route below remains available.

## Local Kokoro through the engine's `tts`

Free, on this computer, no account. The voice model (Kokoro-82M, Apache-2.0) downloads once on first use. Use only an
already available tool/model or obtain the applicable install/download approval. Source `scripts/env.sh` first;
the commands below resolve the installed engine rather than requesting a new version.

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
4. Music under a voice: start with a quieter bed, then judge intelligibility by listening. Ducking amount depends
   on the recording and track, not a fixed universal offset. Captions support muted viewing.
5. Burn in captions from the same transcript (`embedded-captions`).

## Rules
- **It's a synthetic voice: say so** when the person shares the video publicly, if they or the platform need it
  disclosed. Never imitate a real person's voice.
- **Listening:** the voice is unheard by the agent until the person listens (part of the ✋ final film).
- **Tested 2026-10-08:** a 4-word line in `am_michael` gave a clean WAV longer than 0.8 s. Install 160 MB, plus the
  model on first use.
