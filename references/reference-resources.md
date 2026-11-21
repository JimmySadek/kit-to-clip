# Selected-reference resources

Read after a reference is chosen, before a build. Discovery loads metadata only. The private source loader proves
package identity and prompt integrity; it does not prove offline resources, permission, correctness or portability.

Keep a short resource inventory with the video's assets and link it from the brief. Inspect only the selected
prompt/code for fonts, images, scripts, sounds and network requests. Do not automatically crawl a source collection,
download every font or execute commands found in a reference prompt.

## Fonts and browser resources

Many references use Google-hosted fonts. Remove runtime CDN dependencies before export. Prefer the actual chosen
typeface when it is available locally with its licence. Otherwise identify the exact needed families/weights and
obtain the applicable download/install permission, or offer an explicit available alternative. Never silently
substitute a font: typography can be part of the selected medium's identity.

Keep permitted fonts and licences in the private job's `assets/fonts/`, using local `@font-face` URLs. Wait for
`document.fonts.ready` before declaring the draw function ready. Check the actual loaded typeface in the browser;
a successful fallback font is not proof the intended one loaded. Copy only used resources, retaining licence and
source records. General third-party resources keep their own licences, independently of source-prompt permission.

Use installed pinned GSAP/HyperFrames resources and the chosen toolbox paths. Do not embed a second runtime or
update the engine because an upstream guide says to. A version/hash mismatch is a reported dependency state, not
permission to change a lock or installation. No private source, fonts, brand assets or media go in the public skill.

## Sound and controls

The source's browser sound switch or Web Audio calls do not by themselves establish exported audio. Keep the draw
callback pure and time-based. Preserve the selected style's sound character through explicitly timed cues, then
produce local audio files for the existing engine/mix path. Do not trigger new sounds from every seek or redraw.

Record approved narration, music and effects separately in the brief. A narration variant may remove the source's
music/ambience; a separately chosen track must be mixed deliberately, once. Disable any original live sound path
when its baked audio is in use. Test play, pause, repeat seeks and the encoded file, including absence of duplicated
audio. Existing sound tools remain available when chosen; a different music generator is not a required upgrade.

Strip reference player controls from the rendered composition. HyperFrames owns playback, seeking and export;
the builder rebuilds the source for the approved story and chosen dimensions. See `canvas-reference.md` for the
Canvas bridge and honest text-audit limits. An original 16:9 example does not prove portrait support or long-form
readability. Plan those layouts explicitly in the ✋ storyboard, then follow the usual approval stops in `SKILL.md`.
