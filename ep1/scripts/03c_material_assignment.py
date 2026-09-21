# -*- coding: utf-8 -*-
"""
Stage 3.6: 孤立マテリアルの割り当て + 降着円盤の色調変更

調査の結果、没ファイルの時点で AccretionDiskMaterial / EventHorizonMaterial /
SpacesuitMaterial / VisorMaterial / PhotonRingMaterial はどのオブジェクトにも
リンクされていない孤立データ(users=0)だった。これまで「オレンジに光って見えていた」
のは、マテリアル未設定のデフォルト面が周辺ライトに照らされていただけ(Black Holeと同じ現象)。

各マテリアルを意図されたオブジェクトに割り当てる:
- SpacesuitMaterial -> 宇宙服パーツ一式
- VisorMaterial      -> Dark Visor
- AccretionDiskMaterial -> Accretion Disk (色調を目標画像に合わせてオレンジ系→白/青系に変更)
- PhotonRingMaterial -> Event Horizon Ring (強い発光の細いリング)

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python ep1/scripts/03c_material_assignment.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import SOURCE_BLEND, WIP_BLEND

SPACESUIT_PARTS = [
    "Astronaut Body", "Chest Plate", "Helmet",
    "Left Arm", "Left Glove", "Left Leg", "Left Boot",
    "Right Arm", "Right Glove", "Right Leg", "Right Boot",
    "Life Support Pack",
]


def import_orphan_material(name):
    """WIP側で既に消えている孤立マテリアルを、没ファイルからノードごと複製して持ち込む。"""
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    with bpy.data.libraries.load(SOURCE_BLEND, link=False) as (data_from, data_to):
        if name in data_from.materials:
            data_to.materials = [name]
    return bpy.data.materials.get(name)


def assign(obj_name, mat):
    obj = bpy.data.objects[obj_name]
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def adjust_accretion_disk_color(mat):
    """降着円盤を目標画像に合わせてオレンジ系→白〜青系の色調に変更する。"""
    ramp_node = next(n for n in mat.node_tree.nodes if n.type == "VALTORGB")
    ramp = ramp_node.color_ramp
    ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)       # 内側: 純白に近い高温部
    ramp.elements[1].color = (0.55, 0.7, 1.0, 1.0)       # 外側: 青白い低温部
    emission_node = next(n for n in mat.node_tree.nodes if n.type == "EMISSION")
    emission_node.inputs["Strength"].default_value = 6.0  # 9.0だと白飛びしやすいので少し抑える


def adjust_photon_ring_color(mat):
    """光子リングも青みがかった白に寄せる。"""
    emission_node = next(n for n in mat.node_tree.nodes if n.type == "EMISSION")
    emission_node.inputs["Color"].default_value = (0.85, 0.92, 1.0, 1.0)
    emission_node.inputs["Strength"].default_value = 10.0


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)

    spacesuit_mat = import_orphan_material("SpacesuitMaterial")
    visor_mat = import_orphan_material("VisorMaterial")
    accretion_mat = import_orphan_material("AccretionDiskMaterial")
    photon_mat = import_orphan_material("PhotonRingMaterial")

    for part in SPACESUIT_PARTS:
        assign(part, spacesuit_mat)
    assign("Dark Visor", visor_mat)
    assign("Accretion Disk", accretion_mat)
    assign("Event Horizon Ring", photon_mat)

    adjust_accretion_disk_color(accretion_mat)
    adjust_photon_ring_color(photon_mat)

    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage3.6] materials assigned, saved WIP file: {WIP_BLEND}")


if __name__ == "__main__":
    main()
