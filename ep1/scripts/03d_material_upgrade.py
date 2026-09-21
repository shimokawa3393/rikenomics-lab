# -*- coding: utf-8 -*-
"""
Stage 3.7: 中間的な質感向上

モデル自体の作り直しはスコープ外だが、以下は比較的低コストで質感を底上げできる:
- Cyclesレンダラーへの切り替え(EEVEEより反射・陰影が物理的に正確)
- 低ポリすぎるパーツ(腕・脚・ライフサポートパック、34〜6ポリ)にSubdivision Surfaceを追加
- 装備品(グローブ・ブーツ・チェストプレート・ライフサポートパック)を金属質感の
  専用マテリアルに分離し、スーツ本体(布)との質感差を強調
- スーツ本体にノイズベースのラフネスむらを足し、のっぺり感を緩和

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python ep1/scripts/03d_material_upgrade.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import WIP_BLEND

LOW_POLY_PARTS = ["Left Arm", "Right Arm", "Left Leg", "Right Leg", "Life Support Pack"]
HARDWARE_PARTS = ["Chest Plate", "Life Support Pack", "Left Glove", "Right Glove", "Left Boot", "Right Boot"]


def switch_to_cycles():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 128
    scene.cycles.use_denoising = True
    print("[Stage3.7] render engine ->", scene.render.engine, "samples=", scene.cycles.samples)


def add_subdivision(name, levels=2):
    obj = bpy.data.objects[name]
    if any(m.type == "SUBSURF" for m in obj.modifiers):
        return
    mod = obj.modifiers.new("Subdivision", "SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
    print(f"[Stage3.7] subsurf added to {name} (levels={levels})")


def create_hardware_material():
    mat = bpy.data.materials.get("HardwareMaterial")
    if mat is None:
        mat = bpy.data.materials.new("HardwareMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (200, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    bsdf.inputs["Base Color"].default_value = (0.55, 0.57, 0.6, 1.0)
    bsdf.inputs["Metallic"].default_value = 0.85
    bsdf.inputs["Roughness"].default_value = 0.35
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return mat


def add_fabric_roughness_variation(mat):
    """SpacesuitMaterialに布地っぽいラフネスのムラを追加する。"""
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")

    for n in list(nodes):
        if n.get("rikenomics_fabric_detail"):
            nodes.remove(n)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (bsdf.location.x - 400, bsdf.location.y - 200)
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 4.0
    noise["rikenomics_fabric_detail"] = True

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.location = (bsdf.location.x - 200, bsdf.location.y - 200)
    ramp.color_ramp.elements[0].position = 0.4
    ramp.color_ramp.elements[0].color = (0.65, 0.65, 0.65, 1)
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = (0.95, 0.95, 0.95, 1)
    ramp["rikenomics_fabric_detail"] = True

    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    print("[Stage3.7] fabric roughness variation added to SpacesuitMaterial")


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    switch_to_cycles()

    for name in LOW_POLY_PARTS:
        add_subdivision(name, levels=2)

    hardware_mat = create_hardware_material()
    for name in HARDWARE_PARTS:
        obj = bpy.data.objects[name]
        obj.data.materials.clear()
        obj.data.materials.append(hardware_mat)

    spacesuit_mat = bpy.data.materials["SpacesuitMaterial"]
    add_fabric_roughness_variation(spacesuit_mat)

    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage3.7] saved WIP file: {WIP_BLEND}")


if __name__ == "__main__":
    main()
