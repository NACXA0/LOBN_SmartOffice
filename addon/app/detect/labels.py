from __future__ import annotations

# COCO 80 类（与 Frigate/YOLO 常见标签对齐）；总管默认只追踪人与行李类
COCO_LABELS: list[str] = [
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
    "leftover",  # 总管扩展：遗留物
]

DEFAULT_TRACK_LABELS = ["person", "backpack", "handbag", "suitcase", "leftover"]

# Frigate UI 常见中文名（展示用；内部仍用 COCO 英文 id）
LABEL_ZH: dict[str, str] = {
    "person": "人",
    "bicycle": "自行车",
    "car": "汽车",
    "motorcycle": "摩托车",
    "airplane": "飞机",
    "bus": "公交车",
    "train": "火车",
    "truck": "卡车",
    "boat": "船",
    "traffic light": "交通灯",
    "fire hydrant": "消防栓",
    "stop sign": "停车标志",
    "parking meter": "停车计时器",
    "bench": "长椅",
    "bird": "鸟",
    "cat": "猫",
    "dog": "狗",
    "horse": "马",
    "sheep": "绵羊",
    "cow": "牛",
    "elephant": "大象",
    "bear": "熊",
    "zebra": "斑马",
    "giraffe": "长颈鹿",
    "backpack": "背包",
    "umbrella": "雨伞",
    "handbag": "手提包",
    "tie": "领带",
    "suitcase": "手提箱",
    "frisbee": "飞盘",
    "skis": "滑雪板",
    "snowboard": "滑雪板",
    "sports ball": "运动球",
    "kite": "风筝",
    "baseball bat": "棒球棒",
    "baseball glove": "棒球手套",
    "skateboard": "滑板",
    "surfboard": "冲浪板",
    "tennis racket": "网球拍",
    "bottle": "瓶子",
    "wine glass": "酒杯",
    "cup": "杯子",
    "fork": "叉子",
    "knife": "刀",
    "spoon": "勺子",
    "bowl": "碗",
    "banana": "香蕉",
    "apple": "苹果",
    "sandwich": "三明治",
    "orange": "橙子",
    "broccoli": "西兰花",
    "carrot": "胡萝卜",
    "hot dog": "热狗",
    "pizza": "披萨",
    "donut": "甜甜圈",
    "cake": "蛋糕",
    "chair": "椅子",
    "couch": "沙发",
    "potted plant": "盆栽植物",
    "bed": "床",
    "dining table": "餐桌",
    "toilet": "厕所",
    "tv": "电视",
    "laptop": "笔记本电脑",
    "mouse": "鼠标",
    "remote": "遥控器",
    "keyboard": "键盘",
    "cell phone": "手机",
    "microwave": "微波炉",
    "oven": "烤箱",
    "toaster": "烤面包机",
    "sink": "水槽",
    "refrigerator": "冰箱",
    "book": "书",
    "clock": "时钟",
    "vase": "花瓶",
    "scissors": "剪刀",
    "teddy bear": "泰迪熊",
    "hair drier": "吹风机",
    "toothbrush": "牙刷",
    "leftover": "遗留物",
}


def label_display(label: str) -> str:
    return LABEL_ZH.get(label, label)


def default_track_config() -> dict:
    return {
        "labels": list(DEFAULT_TRACK_LABELS),
        "filters": {
            "person": {"min_score": 0.5, "min_area": 0.002},
            "leftover": {"min_score": 0.4, "min_area": 0.001},
        },
    }


def default_audio_config() -> dict:
    return {
        "enabled": False,
        "min_rms": 0.02,
        "cooldown_sec": 30.0,
    }


def filter_detections(
    dets: list,
    *,
    labels: list[str],
    filters: dict | None = None,
    object_masks: list[list] | None = None,
) -> list:
    """按追踪标签、分数/面积过滤；中心点落在目标遮罩内则丢弃。"""
    from .person import Detection, _point_in_poly

    allowed = {str(x) for x in (labels or [])}
    filters = filters or {}
    out = []
    for d in dets:
        label = getattr(d, "label", None) or (d.get("label") if isinstance(d, dict) else None)
        if label not in allowed:
            continue
        score = float(getattr(d, "score", 0) if not isinstance(d, dict) else d.get("score", 0))
        box = getattr(d, "box", None) if not isinstance(d, dict) else d.get("box")
        if not box or len(box) != 4:
            continue
        x1, y1, x2, y2 = [float(v) for v in box]
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        f = filters.get(label) or {}
        if score < float(f.get("min_score", 0.0)):
            continue
        if area < float(f.get("min_area", 0.0)):
            continue
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        masked = False
        for poly in object_masks or []:
            if poly and len(poly) >= 3 and _point_in_poly(cx, cy, poly):
                masked = True
                break
        if masked:
            continue
        if isinstance(d, Detection):
            out.append(d)
        else:
            out.append(Detection(label=label, score=score, box=(x1, y1, x2, y2), in_polygon=True))
    return out
