"""A 3D logo from an SVG with Blender: extruded (filled shapes) or tubed (open strokes), standing up, turning on a
turntable, lit, rendered with a transparent background. Output: PNG frames, logo.mov (ProRes 4444 with alpha) and
logo.webm (VP9 with alpha), ready to place in a HyperFrames video as a layer.

  <blender> -b --factory-startup --python blender_logo.py -- <logo.svg> <out_dir> [--frames 72] [--fps 24] [--size 1080]
            [--turn 360] [--depth 0.12] [--tilt 12] [--samples 32]

--turn is the spin in degrees over the whole clip (360 = one full turn, so the clip loops); --depth is the extrusion
as a share of the logo's width; --tilt leans the camera down so the depth reads. Colours come from the SVG fills; a
shape without a fill gets the stroke colour when the importer kept one, else neutral grey (say so to the person).
"""
import math
import subprocess
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 2:
        raise SystemExit("usage: blender -b --python blender_logo.py -- <logo.svg> <out_dir> [options]")
    opts = {"--frames": 72, "--fps": 24, "--size": 1080, "--turn": 360.0, "--depth": 0.12, "--tilt": 12.0, "--samples": 32}
    i = 2
    while i < len(argv):
        key = argv[i]
        if key not in opts:
            raise SystemExit(f"blender_logo: unknown option {key}")
        opts[key] = type(opts[key])(argv[i + 1])
        i += 2
    return Path(argv[0]).resolve(), Path(argv[1]).resolve(), opts


def svg_colours(svg):
    """id -> (r, g, b, 1) from each element's fill, or its stroke when the fill is none. Blender's SVG importer reads
    fills only, so an outline logo would otherwise come in white."""
    import re
    import xml.etree.ElementTree as ET

    def parse(value):
        value = (value or "").strip().lower()
        m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", value)
        if not m:
            return None
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]   # Blender colours are linear
        return (*lin, 1.0)

    colours = {}
    for el in ET.parse(svg).iter():
        ident = el.get("id")
        if not ident:
            continue
        style = dict(p.split(":", 1) for p in (el.get("style") or "").replace(" ", "").split(";") if ":" in p)
        fill = style.get("fill", el.get("fill"))
        stroke = style.get("stroke", el.get("stroke"))
        colour = parse(fill) if fill and fill != "none" else parse(stroke)
        if colour:
            colours[ident] = colour
    return colours


def main():
    svg, out, o = args()
    colours = svg_colours(svg)
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    before = set(bpy.data.objects)
    bpy.ops.import_curve.svg(filepath=str(svg))
    curves = [ob for ob in bpy.data.objects if ob not in before and ob.type == "CURVE"]
    if not curves:
        raise SystemExit("blender_logo: the SVG had no shapes Blender could read")

    # size: the logo's bounding box in the import's units
    pts = [ob.matrix_world @ Vector(c) for ob in curves for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), 0))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), 0))
    width = max(hi.x - lo.x, hi.y - lo.y) or 1.0
    centre = (lo + hi) / 2
    pivot = bpy.data.objects.new("pivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    for ob in curves:
        data = ob.data
        closed = all(s.use_cyclic_u for s in data.splines)
        if closed and data.fill_mode != "NONE":
            data.extrude = o["--depth"] * width / 2           # filled shapes get depth
        else:
            data.bevel_depth = width * 0.012                   # open strokes become round tubes
            data.extrude = 0
        data.bevel_resolution = 4
        wanted = colours.get(ob.name.split(".")[0])               # the importer names objects after the SVG ids
        if wanted:
            mat = bpy.data.materials.new(f"{ob.name}-svg")
            mat.diffuse_color = wanted
            ob.data.materials.clear()
            ob.data.materials.append(mat)
        elif not ob.data.materials:
            mat = bpy.data.materials.new(f"{ob.name}-grey")
            mat.diffuse_color = (0.55, 0.55, 0.55, 1)
            ob.data.materials.append(mat)
        for mat in ob.data.materials:                          # the importer's flat colour, made into a soft satin
            mat.use_nodes = True
            bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf:
                bsdf.inputs["Base Color"].default_value = mat.diffuse_color
                bsdf.inputs["Roughness"].default_value = 0.35
        ob.location -= centre
        ob.parent = pivot
    scale = 2.0 / width                                         # the logo becomes 2 units wide
    pivot.scale = (scale, scale, scale)
    pivot.rotation_euler = (math.radians(90), 0, 0)            # stand it up, facing the camera

    turntable = bpy.data.objects.new("turntable", None)
    bpy.context.scene.collection.objects.link(turntable)
    pivot.parent = turntable
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = 1, o["--frames"]
    scene.render.fps = o["--fps"]
    turntable.rotation_euler = (0, 0, 0)
    turntable.keyframe_insert("rotation_euler", frame=1)
    turntable.rotation_euler = (0, 0, math.radians(o["--turn"]))
    turntable.keyframe_insert("rotation_euler", frame=o["--frames"] + 1)   # +1: frame N+1 = frame 1, so a full turn loops
    for fc in turntable.animation_data.action.fcurves if hasattr(turntable.animation_data.action, "fcurves") else []:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"

    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 70
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    tilt = math.radians(o["--tilt"])
    dist = 7.5
    cam.location = (0, -dist * math.cos(tilt), dist * math.sin(tilt))
    cam.rotation_euler = (math.radians(90) - tilt, 0, 0)
    scene.camera = cam
    for name, loc, energy, size in (("key", (3, -4, 4), 900, 3), ("fill", (-4, -3, 1), 300, 4), ("rim", (0, 4, 3), 600, 2)):
        light = bpy.data.lights.new(name, "AREA")
        light.energy, light.size = energy, size
        lob = bpy.data.objects.new(name, light)
        lob.location = loc
        lob.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        scene.collection.objects.link(lob)

    scene.render.engine = "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = o["--samples"]
    except AttributeError:
        pass
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = o["--size"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(out / "frame_")
    bpy.ops.render.render(animation=True)

    frames = sorted(out.glob("frame_*.png"))
    pattern = str(out / "frame_%04d.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(o["--fps"]), "-start_number", "1", "-i", pattern,
                    "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", str(out / "logo.mov")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(o["--fps"]), "-start_number", "1", "-i", pattern,
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30", "-auto-alt-ref", "0", str(out / "logo.webm")], check=True)
    print(f"blender_logo: {len(frames)} frames, {o['--size']}px, {o['--turn']:.0f} degree turn -> {out}/logo.mov and logo.webm")


main()
