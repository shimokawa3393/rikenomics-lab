# -*- coding: utf-8 -*-
"""
Stage 3: カメラワーク + 軌跡リビール(描画)アニメーション

Stage 2の静止画ゲートを通過した後に実行する。
- 各カーブの bevel_factor_end を、ショット境目の階段状ではなく shots.reveal_at_frame()
  による1本の指数カーブ(イーズイン)で毎フレームキーフレーム化し、なめらかに加速しながら
  伸びていく動きを作る(実際の分岐タイミングに合わせて校正済み。詳細はshots.py参照)
- 先端マーカーの座標を、bevel_factor_endと全く同じインデックス計算(point_at_reveal)で
  Python側から直接キーフレーム化し、チューブの描画先端と完全に一致させる
  (Follow Pathは弧長基準に再計算されズレるため不使用)
- カメラ: 系統A単体の軌跡でも reveal<=0.15 の時点で既にアトラクター全体とほぼ同じ
  空間的広がり(bounding box)を動き回ることが判明したため、「点を密に追従するカメラ」
  は採用しない(渦を巻く動きに振り回されて画面が安定しない上、そもそも点だけ追っても
  『何を描いているか』の文脈が画面に残らない)。原点を注視点に、球面座標(方位角/仰角/
  距離)で毎フレーム位置を計算し、①→④結にかけてゆっくり周回しながら一段引く。
  Track Toコンストレイントは使わない(up_axisをワールドYに固定するため水平を向く
  ことしかできずロールが出せない)。代わりにmathutilsで注視方向からクォータニオンを
  作り、視線軸まわりに明示的なロール角を合成することで、③転(カオスが広がる瞬間)
  だけ煽り(バンク)を入れ、④結の最終カットで水平に収める。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep2/scripts/03_camera_timeline.py"
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import math

import bpy
import mathutils
from shots import (
    SHOTS, FPS, WIP_BLEND, STILLCHECK_DIR,
    X0, Y0, Z0, EPSILON, compute_trajectory, point_at_reveal, reveal_at_frame,
)
from blender_compat import set_all_keyframes_interpolation

# ④結の最終カメラ位置(Stage2の静止画ゲートと同じ = 絵作り確認済みの構図)。
# 球面座標(距離/方位角/仰角)はこの位置から逆算する。
WIDE_CAMERA_LOCATION = (6.0, -8.5, 3.5)
WIDE_TARGET_LOCATION = (0.0, 0.0, 0.0)

# 序盤の距離(ワイドショットの85%=同じ方向でやや寄り)。
# 軌跡はreveal<=0.15の時点で既に全体とほぼ同じ広がりを動き回るため、これ以上寄せると
# 序盤から絵がフレームアウトする。ここでは「④結でさらに一段引く」余地を残す程度に留める。
_MID_SCALE = 0.85
# 方位角(ヨー)・仰角(ピッチ)は、①→④結にかけて対象の周りを回り込む振れ幅。
# 360度(一周)まわることで、複雑な3D構造(両翼の奥行き・絡み合い)を全方位から見せる。
AZIMUTH_SWEEP = math.radians(360)
ELEVATION_SWEEP = math.radians(20)
# ロール(バンク)の最大角。③転(=3a+3b)の間だけ煽り、それ以外は水平。
ROLL_MAX = math.radians(7)


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def spherical_to_cartesian(distance, azimuth, elevation):
    return (
        distance * math.cos(elevation) * math.cos(azimuth),
        distance * math.cos(elevation) * math.sin(azimuth),
        distance * math.sin(elevation),
    )


def look_at_quaternion(location, target, roll):
    """注視方向からクォータニオンを作り、視線軸(-Z)まわりにroll[rad]だけ回転を合成する。"""
    direction = mathutils.Vector(target) - mathutils.Vector(location)
    quat = direction.to_track_quat('-Z', 'Y')
    if roll:
        quat = quat @ mathutils.Quaternion((0.0, 0.0, 1.0), roll)
    return quat


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene

    curve_a = bpy.data.objects["TrajectoryA"]
    curve_b = bpy.data.objects["TrajectoryB"]
    marker_a = bpy.data.objects["TipMarkerA"]
    marker_b = bpy.data.objects["TipMarkerB"]
    camera = bpy.data.objects["MainCamera"]
    target = bpy.data.objects["AttractorCenter"]

    # 既存のアニメーションをクリア(再実行に備える)
    for obj in (curve_a.data, curve_b.data, marker_a, marker_b, camera, target):
        obj.animation_data_clear()

    # Stage1と同じ座標列を再計算(01と03で同一ロジックをshots.pyに共通化済み)
    points_a = compute_trajectory(X0, Y0, Z0)
    points_b = compute_trajectory(X0 + EPSILON, Y0, Z0)

    # ------------------------------------------------------------
    # 1. フレームレンジ
    # ------------------------------------------------------------
    scene.frame_start = 1
    scene.frame_end = SHOTS[-1]["frame_end"]
    scene.render.fps = FPS

    # ------------------------------------------------------------
    # 2. bevel_factor_end(軌跡のリビール)+ 2b. 先端マーカー
    # どちらも shots.reveal_at_frame() の同じ値から毎フレーム計算する。
    # reveal(frame)は指数カーブ(なめらかな加速)のため、ショット境目だけの疎な
    # キーフレームでは形が再現できない → 毎フレーム打つ。
    # マーカー座標はbevel_factor_endと全く同じインデックス計算(point_at_reveal)で
    # Python側から直接求め、チューブの描画先端と完全に一致させる
    # (Follow Pathは弧長基準に再計算されズレるため不使用)。
    # ------------------------------------------------------------
    total_frames = SHOTS[-1]["frame_end"]
    for frame in range(1, total_frames + 1):
        reveal = reveal_at_frame(frame, total_frames)

        curve_a.data.bevel_factor_end = reveal
        curve_a.data.keyframe_insert(data_path="bevel_factor_end", frame=frame)
        curve_b.data.bevel_factor_end = reveal
        curve_b.data.keyframe_insert(data_path="bevel_factor_end", frame=frame)

        marker_a.location = point_at_reveal(points_a, reveal)
        marker_a.keyframe_insert(data_path="location", frame=frame)
        marker_b.location = point_at_reveal(points_b, reveal)
        marker_b.keyframe_insert(data_path="location", frame=frame)

    set_all_keyframes_interpolation(curve_a.data, interpolation="LINEAR", easing="EASE_IN_OUT")
    set_all_keyframes_interpolation(curve_b.data, interpolation="LINEAR", easing="EASE_IN_OUT")
    set_all_keyframes_interpolation(marker_a, interpolation="LINEAR", easing="EASE_IN_OUT")
    set_all_keyframes_interpolation(marker_b, interpolation="LINEAR", easing="EASE_IN_OUT")

    # ------------------------------------------------------------
    # 3. カメラ(位置はヨー/ピッチ/距離の球面座標、向きはクォータニオン+ロール)
    # AttractorCenterはもう注視点としては使わない(Track Toを外したため)。
    # ------------------------------------------------------------
    for c in list(camera.constraints):
        camera.constraints.remove(c)
    camera.rotation_mode = 'QUATERNION'

    wx, wy, wz = WIDE_CAMERA_LOCATION
    dist_final = math.sqrt(wx * wx + wy * wy + wz * wz)
    az_final = math.atan2(wy, wx)
    el_final = math.asin(wz / dist_final)
    dist_mid = dist_final * _MID_SCALE
    az_start = az_final - AZIMUTH_SWEEP
    el_start = el_final - ELEVATION_SWEEP

    roll_start_frame = next(s["frame_start"] for s in SHOTS if s["id"] == "3a")  # 91
    roll_end_frame = next(s["frame_end"] for s in SHOTS if s["id"] == "3b")  # 210

    for frame in range(1, total_frames + 1):
        t = (frame - 1) / (total_frames - 1)
        az = az_start + (az_final - az_start) * smoothstep(t)
        el = el_start + (el_final - el_start) * smoothstep(t)
        # 距離: 序盤は寄り気味を維持し、終盤(④結)で一気に引く(t**2.5でイーズイン)
        dist = dist_mid + (dist_final - dist_mid) * (t ** 2.5)
        loc = spherical_to_cartesian(dist, az, el)

        if roll_start_frame <= frame <= roll_end_frame:
            u = (frame - roll_start_frame) / (roll_end_frame - roll_start_frame)
            roll = ROLL_MAX * math.sin(math.pi * u)
        else:
            roll = 0.0

        camera.location = loc
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.rotation_quaternion = look_at_quaternion(loc, WIDE_TARGET_LOCATION, roll)
        camera.keyframe_insert(data_path="rotation_quaternion", frame=frame)

    set_all_keyframes_interpolation(camera, interpolation="BEZIER", easing="EASE_IN_OUT")

    # ------------------------------------------------------------
    # 4. 保存
    # ------------------------------------------------------------
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print("[Stage3] animation keyframes set. frame range:", scene.frame_start, "-", scene.frame_end)

    # ------------------------------------------------------------
    # 5. 各ショット末尾フレームのプレビュー静止画(アニメーション全体レンダー前の確認用)
    # ------------------------------------------------------------
    engine_ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_ids else 'BLENDER_EEVEE'
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.image_settings.file_format = 'PNG'

    os.makedirs(STILLCHECK_DIR, exist_ok=True)
    for shot in SHOTS:
        scene.frame_set(shot["frame_end"])
        output_path = os.path.join(STILLCHECK_DIR, f"ep2_preview_{shot['id']}.png")
        scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)
        print(f"[Stage3] preview rendered: {shot['id']} -> {output_path}")

    scene.frame_set(1)


if __name__ == "__main__":
    main()
