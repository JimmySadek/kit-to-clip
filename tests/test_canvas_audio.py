"""Canvas seeking and encoded audio-file integration. Synthetic tones, not listening/taste approval."""
from array import array
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

REPO=Path(__file__).resolve().parents[1]
SKILL=REPO if (REPO/'SKILL.md').exists() else REPO/'addons/kit-to-clip'


def tone(path,frequency,amplitude,duration):
    samples=array('h',(round(32767*amplitude*math.sin(2*math.pi*frequency*i/48000)) for i in range(round(duration*48000))))
    with wave.open(str(path),'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(samples.tobytes())


class CanvasAudioTests(unittest.TestCase):
    def test_seeked_canvas_exports_one_correctly_timed_audio_mix(self):
        engine=os.environ.get('REEL_STUDIO')
        browser=os.environ.get('HYPERFRAMES_BROWSER_PATH')
        if not engine or not browser:
            self.skipTest('Source Kit to Clip scripts/env.sh for actual engine/audio export')
        self.assertNotIn('/Applications/Google Chrome.app',browser)
        with tempfile.TemporaryDirectory(prefix='kit-canvas-audio-') as tmp:
            project=Path(tmp)
            (project/'vendor').mkdir()
            (project/'audio').mkdir()
            shutil.copy2(Path(engine)/'node_modules/gsap/dist/gsap.min.js',project/'vendor/gsap.min.js')
            shutil.copy2(SKILL/'finish/scripts/canvas-bridge.js',project/'canvas-bridge.js')
            tone(project/'audio/bed.wav',220,0.05,2)
            tone(project/'audio/hit.wav',880,0.2,0.08)
            (project/'index.html').write_text('''<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;width:320px;height:180px;overflow:hidden}#root{position:relative;width:320px;height:180px}</style>
<script src="vendor/gsap.min.js"></script><script src="canvas-bridge.js"></script></head><body>
<div id="root" data-composition-id="audio-test" data-width="320" data-height="180" data-duration="2">
<canvas id="art" width="320" height="180" data-k2c-canvas></canvas>
<audio id="bed" src="audio/bed.wav" data-start="0" data-duration="2" data-track-index="1" data-volume="1"></audio>
<audio id="hit" src="audio/hit.wav" data-start="0.8" data-duration="0.08" data-track-index="2" data-volume="1"></audio>
</div><script>window.__timelines=window.__timelines||{};
window.__timelines["audio-test"]=gsap.timeline({paused:true});
KitToClipCanvas.register({id:"art",canvas:document.getElementById("art"),duration:2,ready:document.fonts.ready,
draw(ctx,t){ctx.fillStyle=t<0.8?"#e02020":"#2040e0";ctx.fillRect(0,0,320,180);
ctx.fillStyle="#fff";ctx.font="bold 30px sans-serif";ctx.fillText("SYNC",40+20*t,100);}});
</script></body></html>''')
            probe=r'''
const {withComposition}=await import(process.env.KIT_HFPAGE);
const result=await withComposition(process.env.KIT_AUDIO_PROJECT,"Canvas audio test",async({page,state,errors})=>{
 const rows=await page.evaluate(async()=>{
  const rows=[];
  for(const t of [0.2,1.2,0.2]){
   await window.__reelVisible.seek(t);
   rows.push({time:t,pixels:document.querySelector('canvas').toDataURL(),
    tracks:[...document.querySelectorAll('audio')].map(a=>({id:a.id,paused:a.paused,time:a.currentTime}))});
  }
  return {rows,controls:Object.keys(window.__player).filter(k=>typeof window.__player[k]==='function')};
 });
 return {ready:state.ready,duration:state.duration,...rows,errors:{script:errors.script,console:errors.console,remote:errors.remote,missing:[...errors.missing]}};
}); console.log('@@audio '+JSON.stringify(result));
'''
            r=subprocess.run(['node','--input-type=module','-e',probe],text=True,capture_output=True,
                env={**os.environ,'KIT_HFPAGE':(SKILL/'finish/scripts/hfpage.mjs').as_uri(),
                     'KIT_AUDIO_PROJECT':str(project)},timeout=60)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            line=next(line for line in r.stdout.splitlines() if line.startswith('@@audio '))
            measured=json.loads(line[8:])
            self.assertTrue(measured['ready'])
            self.assertEqual(measured['errors'],{'script':[],'console':[],'remote':[],'missing':[]})
            self.assertEqual(measured['rows'][0]['pixels'],measured['rows'][2]['pixels'])
            self.assertNotEqual(measured['rows'][0]['pixels'],measured['rows'][1]['pixels'])
            self.assertTrue(all(len(row['tracks'])==2 for row in measured['rows']))
            output=project/'mix.mp4'
            command=[str(Path(engine)/'node_modules/.bin/hyperframes'),'render',str(project),
                '--output',str(output),'--quality','draft','--fps','30','--workers','1','--quiet']
            rendered=subprocess.run(command,text=True,capture_output=True,timeout=120)
            self.assertEqual(rendered.returncode,0,rendered.stdout+rendered.stderr)
            self.assertNotIn('PAGEERROR',rendered.stdout+rendered.stderr)
            info=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(output)],
                text=True,capture_output=True,check=True)
            meta=json.loads(info.stdout)
            self.assertEqual(sum(s['codec_type']=='audio' for s in meta['streams']),1)
            self.assertAlmostEqual(float(meta['format']['duration']),2,delta=1/30)
            # Inspect one encoded channel. A stereo-to-mono matrix can add gain
            # when two correlated channels are folded together.
            decoded=subprocess.run(['ffmpeg','-v','error','-i',str(output),'-vn','-af','pan=mono|c0=c0','-ar','48000',
                '-f','f32le','pipe:1'],capture_output=True,check=True)
            pcm=array('f')
            pcm.frombytes(decoded.stdout)
            def rms(start,end):
                values=pcm[round(start*48000):round(end*48000)]
                return math.sqrt(sum(value*value for value in values)/len(values))
            print(json.dumps({'audio_measurement':{'encoded_channels':[s.get('channels') for s in meta['streams']
                if s['codec_type']=='audio'],'single_channel_bed_rms':rms(.15,.45),
                'single_channel_hit_rms':rms(.81,.86),'controls_observed':measured['controls']}}))
            self.assertGreater(rms(.15,.45),.025)
            self.assertLess(rms(.15,.45),.05)  # A doubled bed would exceed this.
            self.assertGreater(rms(.81,.86),.10)
            self.assertLess(rms(.81,.86),.20)  # A doubled hit would exceed this.
            starts=[i/1000 for i in range(650,950,5) if rms(i/1000,i/1000+.01)>.09]
            self.assertTrue(starts)
            self.assertAlmostEqual(starts[0],.8,delta=.04)
            for at,channel in ((.2,0),(1.2,2)):
                frame=subprocess.run(['ffmpeg','-v','error','-ss',str(at),'-i',str(output),'-frames:v','1',
                    '-f','rawvideo','-pix_fmt','rgb24','pipe:1'],capture_output=True,check=True).stdout
                pixel=frame[(10*320+10)*3:(10*320+10)*3+3]
                self.assertGreater(pixel[channel],150)
            print(json.dumps({'canvas_audio':{'duration':float(meta['format']['duration']),'audio_streams':1,
                'bed_rms':rms(.15,.45),'hit_rms':rms(.81,.86),'cue_onset':starts[0],
                'seek_aba':True,'controls_observed':measured['controls'],'listening':'not assessed'}}))


if __name__=='__main__':
    unittest.main()
