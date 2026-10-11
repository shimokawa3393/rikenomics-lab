# -*- coding: utf-8 -*-
"""
本番の車のボディ(レンダーする形そのもの)を、計算用に書き出す: 三角形の頂点(ワールド座標)と、三角形ごとの材質番号。
材質1(ガラス)だけが電気を通さない。ほかの材質(塗装・黒いBピラー・隙間・グリル・ランプなど)は、下は金属のボディ。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep5/scripts/03_export_car_mesh.py"
出力: ep5/cache/car_body.npz(verts, tris, mat)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import numpy as np
from shots import EP5, WIP_BLEND

CACHE = os.path.join(EP5, "cache", "car_body.npz")


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    body = bpy.data.objects["CarBody"]
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    bm = bmesh.new()
    bm.from_mesh(ev.to_mesh())
    bm.transform(body.matrix_world)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)  # 面の切れ目で離れている頂点をつなぐ(電流がつながって流れるように)
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    verts = np.array([v.co[:] for v in bm.verts])
    tris = np.array([[v.index for v in f.verts] for f in bm.faces])
    mat = np.array([f.material_index for f in bm.faces])
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    np.savez(CACHE, verts=verts, tris=tris, mat=mat)
    print(f"[Export] {CACHE}: {len(verts)} verts, {len(tris)} tris, glass {int((mat == 1).sum())} tris, "
          f"x {verts[:, 0].min():.2f}..{verts[:, 0].max():.2f} y {verts[:, 1].min():.2f}..{verts[:, 1].max():.2f} "
          f"z {verts[:, 2].min():.2f}..{verts[:, 2].max():.2f}")


if __name__ == "__main__":
    main()
