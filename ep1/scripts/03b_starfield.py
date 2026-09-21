# -*- coding: utf-8 -*-
"""
Stage 3.5: 星空(宇宙観)の追加

ワールドの背景が単色グレー(0.05,0.05,0.05)のみで、星が一つも無く
宇宙空間らしさが乏しかった(没ファイル時点の「Stars」コレクションも中身は空)。
ワールドシェーダーにVoronoiベースのプロシージャル星空を追加し、視差なしの
遠方の恒星として全カット共通の背景に効かせる。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python ep1/scripts/03b_starfield.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import WIP_BLEND


def build_starfield_world():
    world = bpy.context.scene.world
    world.use_nodes = True
    nt = world.node_tree
    nodes = nt.nodes
    links = nt.links

    background = next(n for n in nodes if n.type == "BACKGROUND")

    # 既存の星生成ノードがあれば一度片付けてから作り直す(冪等に再実行できるように)
    for n in list(nodes):
        if n.get("rikenomics_starfield"):
            nodes.remove(n)

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-1000, -400)
    tex_coord["rikenomics_starfield"] = True

    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-800, -400)
    mapping.inputs["Scale"].default_value = (400.0, 400.0, 400.0)
    mapping["rikenomics_starfield"] = True

    voronoi = nodes.new("ShaderNodeTexVoronoi")
    voronoi.location = (-600, -400)
    voronoi.voronoi_dimensions = "3D"
    voronoi.feature = "F1"
    voronoi.inputs["Randomness"].default_value = 1.0
    voronoi["rikenomics_starfield"] = True

    # Voronoi Distance: 各点(星)の中心付近だけ値が0に近づくので、
    # 0付近だけを白くして残りを黒にすると星のような点在になる。
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (-400, -400)
    ramp.color_ramp.interpolation = "CONSTANT"  # シャープな点にする(にじませない)
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1, 1, 1, 1)
    ramp.color_ramp.elements[1].position = 0.045
    ramp.color_ramp.elements[1].color = (0, 0, 0, 1)
    ramp["rikenomics_starfield"] = True

    star_brightness = nodes.new("ShaderNodeMixRGB")
    star_brightness.location = (-200, -400)
    star_brightness.blend_type = "MULTIPLY"
    star_brightness.inputs["Fac"].default_value = 1.0
    star_brightness.inputs["Color2"].default_value = (4.0, 4.0, 4.0, 1.0)
    star_brightness["rikenomics_starfield"] = True

    mix_into_bg = nodes.new("ShaderNodeMixRGB")
    mix_into_bg.location = (0, -200)
    mix_into_bg.blend_type = "ADD"
    mix_into_bg.inputs["Fac"].default_value = 1.0
    mix_into_bg["rikenomics_starfield"] = True

    links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], voronoi.inputs["Vector"])
    links.new(voronoi.outputs["Distance"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], star_brightness.inputs["Color1"])

    # 元のBackground Colorを土台にして星を加算する
    base_color = background.inputs["Color"].default_value[:]
    mix_into_bg.inputs["Color1"].default_value = base_color
    links.new(star_brightness.outputs["Color"], mix_into_bg.inputs["Color2"])
    links.new(mix_into_bg.outputs["Color"], background.inputs["Color"])

    print("[Stage3.5] starfield nodes added to world:", world.name)


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    build_starfield_world()
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage3.5] saved WIP file: {WIP_BLEND}")


if __name__ == "__main__":
    main()
