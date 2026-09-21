# -*- coding: utf-8 -*-
"""
Stage 2.5: ブラックホールのマテリアル修正

「Black Hole」オブジェクトにマテリアルが割り当てられておらず、デフォルトの
白っぽいdiffuseのまま周囲の発光体(降着円盤・事象の地平線リング)の光を
そのまま反射してしまい、オレンジに光る球体に見えてしまっていた。
台本は「光すら飲み込む黒い球体」なので、光を反射しない真っ黒なマテリアルを作って割り当てる。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python ep1/scripts/02b_blackhole_material.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import WIP_BLEND


def create_black_hole_material():
    mat = bpy.data.materials.get("BlackHoleMaterial")
    if mat is None:
        mat = bpy.data.materials.new("BlackHoleMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (200, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)

    bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Metallic"].default_value = 0.0
    for specular_key in ("Specular IOR Level", "Specular"):
        if specular_key in bsdf.inputs:
            bsdf.inputs[specular_key].default_value = 0.0
            break

    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def apply_to_black_hole():
    bh = bpy.data.objects["Black Hole"]
    mat = create_black_hole_material()
    bh.data.materials.clear()
    bh.data.materials.append(mat)
    print(f"[Stage2.5] assigned {mat.name} to {bh.name}")


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    apply_to_black_hole()
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage2.5] saved WIP file: {WIP_BLEND}")


if __name__ == "__main__":
    main()
