# -*- coding: utf-8 -*-
"""
Blender 4.4+ のレイヤード Action (layers -> strips -> channelbags -> fcurves)
に対応するための互換ヘルパー。
"""


def iter_action_fcurves(action):
    """action配下の全fcurveを列挙する(新旧どちらのAction構造にも対応)。"""
    if action is None:
        return
    if hasattr(action, "fcurves"):
        # 旧APIが残っている場合はそのまま使う
        for fc in action.fcurves:
            yield fc
        return
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type != "KEYFRAME":
                continue
            for channelbag in strip.channelbags:
                for fc in channelbag.fcurves:
                    yield fc


def set_all_keyframes_interpolation(obj, interpolation="QUAD", easing="EASE_IN"):
    """オブジェクトのアクション上の全キーフレームの補間方法を一括設定する。

    interpolationは 'CONSTANT'/'LINEAR'/'BEZIER'/'SINE'/'QUAD'/... のカーブ形状、
    easingは 'EASE_IN'/'EASE_OUT'/'EASE_IN_OUT' の適用方向。
    """
    if not obj.animation_data or not obj.animation_data.action:
        return
    for fc in iter_action_fcurves(obj.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = interpolation
            kp.easing = easing
