from __future__ import annotations

from pathlib import Path
import random
import argparse

from PIL import Image, ImageChops, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
DECK = Path(__file__).resolve().parents[1]
OUT_DIR = DECK / "origin_image"

W, H = 2160, 1215
PAPER = (248, 244, 235)
INK = (11, 58, 102)
INDIGO = (47, 97, 122)
CINNABAR = (200, 76, 53)
PALE_INK = (205, 213, 209)

TITLE_FONT = Path(r"C:\Windows\Fonts\方正粗黑宋简体.ttf")
SERIF_FONT = Path(r"C:\Windows\Fonts\STZHONGS.TTF")
BODY_FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
BODY_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size=size)


def paper_canvas() -> Image.Image:
    image = Image.new("RGB", (W, H), PAPER)
    pixels = image.load()
    rng = random.Random(20260716)
    for _ in range(36000):
        x = rng.randrange(W)
        y = rng.randrange(H)
        delta = rng.choice((-4, -3, -2, 2, 3, 4))
        r, g, b = pixels[x, y]
        pixels[x, y] = (
            max(0, min(255, r + delta)),
            max(0, min(255, g + delta)),
            max(0, min(255, b + delta)),
        )
    return image


def draw_mountains(draw: ImageDraw.ImageDraw) -> None:
    layers = [
        [(1350, 166), (1430, 78), (1510, 156), (1600, 94), (1710, 168), (1830, 102), (1980, 184), (2159, 110)],
        [(0, 1100), (120, 1000), (240, 1120), (360, 1025), (500, 1155), (650, 1072)],
    ]
    for pts in layers:
        draw.line(pts, fill=PALE_INK, width=3)
        shifted = [(x, y + 10) for x, y in pts]
        draw.line(shifted, fill=(224, 225, 216), width=2)


def draw_header(draw: ImageDraw.ImageDraw, title: str) -> None:
    brush = [
        (38, 27), (405, 27), (432, 33), (468, 29), (452, 40), (487, 49),
        (452, 56), (468, 69), (430, 66), (406, 80), (42, 80), (31, 67),
        (35, 51), (30, 39),
    ]
    draw.polygon(brush, fill=CINNABAR)
    draw.line((390, 35, 500, 44), fill=CINNABAR, width=3)
    draw.line((402, 65, 484, 58), fill=CINNABAR, width=2)
    draw.text((62, 34), "A5—景区导览服务 AI 数字人", font=font(SERIF_FONT, 25), fill=(255, 251, 241))
    draw.text((55, 94), title, font=font(TITLE_FONT, 60), fill=INK)
    draw.line((55, 176, 2070, 176), fill=INK, width=2)


def paste_native(canvas: Image.Image, source_path: Path, xy: tuple[int, int]) -> tuple[Image.Image, tuple[int, int, int, int]]:
    source = Image.open(source_path).convert("RGB")
    x, y = xy
    canvas.paste(source, (x, y))
    box = (x, y, x + source.width, y + source.height)
    copied = canvas.crop(box)
    if ImageChops.difference(source, copied).getbbox() is not None:
        raise RuntimeError(f"Pixel fidelity assertion failed for {source_path}")
    return source, box


def compose_slide_07() -> Path:
    desktop_path = ROOT / "reports" / "visual" / "ui-after" / "desktop-1440x900.png"
    mobile_path = ROOT / "reports" / "visual" / "ui-after" / "mobile-390x844.png"

    canvas = paper_canvas()
    draw = ImageDraw.Draw(canvas)
    draw_mountains(draw)
    draw_header(draw, "游客端：一位安静、可信的随身导游")

    desktop_xy = (55, 230)
    mobile_xy = (1675, 230)
    _, desktop_box = paste_native(canvas, desktop_path, desktop_xy)
    _, mobile_box = paste_native(canvas, mobile_path, mobile_xy)

    draw.rectangle((desktop_box[0] - 3, desktop_box[1] - 3, desktop_box[2] + 3, desktop_box[3] + 3), outline=INK, width=3)
    draw.rectangle((mobile_box[0] - 3, mobile_box[1] - 3, mobile_box[2] + 3, mobile_box[3] + 3), outline=INK, width=3)

    label_font = font(SERIF_FONT, 24)
    draw.ellipse((56, 191, 72, 207), fill=CINNABAR)
    draw.text((82, 185), "桌面端｜数字人、对话与当前游线同屏", font=label_font, fill=INK)
    draw.ellipse((1676, 191, 1692, 207), fill=CINNABAR)
    draw.text((1702, 185), "移动端｜单列响应式", font=label_font, fill=INK)

    note_font = font(BODY_FONT, 21)
    draw.ellipse((57, 1155, 73, 1171), fill=CINNABAR)
    draw.text((84, 1148), "数字人是陪伴者，不遮挡任务", font=note_font, fill=INK)
    draw.ellipse((830, 1155, 846, 1171), fill=CINNABAR)
    draw.text((857, 1148), "桌面与移动端保持对话、字幕与核心操作", font=note_font, fill=INK)

    out = OUT_DIR / "slide_07.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG", optimize=True)

    final = Image.open(out).convert("RGB")
    desktop = Image.open(desktop_path).convert("RGB")
    mobile = Image.open(mobile_path).convert("RGB")
    if ImageChops.difference(desktop, final.crop(desktop_box)).getbbox() is not None:
        raise RuntimeError("Final desktop screenshot pixels differ from source")
    if ImageChops.difference(mobile, final.crop(mobile_box)).getbbox() is not None:
        raise RuntimeError("Final mobile screenshot pixels differ from source")
    return out


def draw_down_arrow(draw: ImageDraw.ImageDraw, x: int, y1: int, y2: int) -> None:
    draw.line((x, y1, x, y2 - 12), fill=INK, width=4)
    draw.polygon([(x - 9, y2 - 18), (x + 9, y2 - 18), (x, y2)], fill=INK)


def compose_slide_08() -> Path:
    admin_path = ROOT / "reports" / "visual" / "ui-after" / "admin-1440x900.png"

    canvas = paper_canvas()
    draw = ImageDraw.Draw(canvas)
    draw_mountains(draw)
    draw_header(draw, "运营后台：让每一次服务持续变好")

    admin_xy = (55, 230)
    _, admin_box = paste_native(canvas, admin_path, admin_xy)
    draw.rectangle((admin_box[0] - 3, admin_box[1] - 3, admin_box[2] + 3, admin_box[3] + 3), outline=INK, width=3)

    label_font = font(SERIF_FONT, 24)
    draw.ellipse((56, 191, 72, 207), fill=CINNABAR)
    draw.text((82, 185), "运营概览｜真实景区管理后台", font=label_font, fill=INK)

    panel = (1545, 226, 2105, 1080)
    draw.rounded_rectangle(panel, radius=26, outline=(193, 202, 202), width=2, fill=(251, 248, 240))
    draw.text((1600, 255), "知识—服务—反馈—优化", font=font(TITLE_FONT, 34), fill=CINNABAR)
    draw.text((1630, 305), "把每一次问答变成下一次服务优化的依据", font=font(BODY_FONT, 20), fill=INDIGO)

    stops = [
        (405, "知识", "资料维护｜索引重建"),
        (585, "服务", "形象声音｜热门问答"),
        (765, "反馈", "满意度｜问题处理"),
        (945, "优化", "质量报告｜运营决策"),
    ]
    node_x = 1675
    for idx, (y, name, detail) in enumerate(stops):
        draw.ellipse((node_x - 54, y - 54, node_x + 54, y + 54), outline=INK, width=4, fill=PAPER)
        bbox = draw.textbbox((0, 0), name, font=font(TITLE_FONT, 31))
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((node_x - tw / 2, y - th / 2 - 4), name, font=font(TITLE_FONT, 31), fill=INK)
        draw.text((1760, y - 15), detail, font=font(BODY_FONT, 22), fill=INK)
        if idx < len(stops) - 1:
            draw_down_arrow(draw, node_x, y + 62, stops[idx + 1][0] - 62)

    draw.line((2055, 945, 2055, 405), fill=CINNABAR, width=3)
    draw.line((2055, 405, 2015, 405), fill=CINNABAR, width=3)
    draw.polygon([(2015, 405), (2032, 396), (2032, 414)], fill=CINNABAR)
    draw.text((2018, 600), "持\n续\n迭\n代", font=font(SERIF_FONT, 22), fill=CINNABAR, spacing=3)

    note_font = font(BODY_FONT, 21)
    draw.ellipse((57, 1155, 73, 1171), fill=CINNABAR)
    draw.text((84, 1148), "游客端解决即时服务，运营端负责持续优化", font=note_font, fill=INK)

    out = OUT_DIR / "slide_08.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG", optimize=True)

    final = Image.open(out).convert("RGB")
    admin = Image.open(admin_path).convert("RGB")
    if ImageChops.difference(admin, final.crop(admin_box)).getbbox() is not None:
        raise RuntimeError("Final admin screenshot pixels differ from source")
    return out


def metric_box(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    ratio: str,
    percent: str,
) -> None:
    draw.rounded_rectangle(box, radius=22, outline=INK, width=3, fill=(251, 248, 240))
    x1, y1, x2, y2 = box
    draw.text((x1 + 28, y1 + 20), label, font=font(SERIF_FONT, 26), fill=INK)
    draw.text((x1 + 28, y1 + 62), ratio, font=font(TITLE_FONT, 54), fill=INK)
    pct_bbox = draw.textbbox((0, 0), percent, font=font(TITLE_FONT, 45))
    pct_w = pct_bbox[2] - pct_bbox[0]
    draw.text((x2 - pct_w - 34, y1 + 72), percent, font=font(TITLE_FONT, 45), fill=CINNABAR)
    draw.rounded_rectangle((x2 - 105, y1 + 20, x2 - 25, y1 + 53), radius=12, fill=INK)
    draw.text((x2 - 93, y1 + 24), "已证实", font=font(BODY_BOLD, 17), fill=(255, 251, 241))


def compose_slide_09() -> Path:
    before_path = ROOT / "reports" / "quality" / "opentalking-webrtc-evidence" / "mouth-before.png"
    peak_path = ROOT / "reports" / "quality" / "opentalking-webrtc-evidence" / "mouth-motion-peak.png"

    canvas = paper_canvas()
    draw = ImageDraw.Draw(canvas)
    draw_mountains(draw)
    draw_header(draw, "测试数据：准确率与实时交互双重验证")

    section_font = font(SERIF_FONT, 28)
    draw.ellipse((56, 196, 72, 212), fill=CINNABAR)
    draw.text((82, 188), "项目知识问答准确率", font=section_font, fill=INK)
    draw.ellipse((701, 196, 717, 212), fill=CINNABAR)
    draw.text((727, 188), "口型运动证据｜WebRTC 连续帧检测", font=section_font, fill=INK)

    metric_box(draw, (55, 250, 640, 425), "固定 17 题", "17/17", "100%")
    metric_box(draw, (55, 445, 640, 620), "隐藏 30 题", "28/30", "93.33%")
    draw.text((75, 635), "基于 3 份资料｜22 个景点｜66 个知识分片｜113 条 FAQ", font=font(BODY_FONT, 20), fill=INDIGO)

    draw.text((55, 690), "实时链路关键时延", font=section_font, fill=INK)
    timings = [
        (750, "会话创建到首个视频帧", "0.76s"),
        (850, "音频到 speaking 状态", "0.19s"),
        (950, "音频到可见口型运动", "2.93s"),
    ]
    for y, label, value in timings:
        draw.line((55, y + 78, 640, y + 78), fill=(202, 209, 205), width=2)
        draw.text((75, y), label, font=font(BODY_FONT, 22), fill=INK)
        value_bbox = draw.textbbox((0, 0), value, font=font(TITLE_FONT, 43))
        value_w = value_bbox[2] - value_bbox[0]
        draw.text((615 - value_w, y + 25), value, font=font(TITLE_FONT, 43), fill=CINNABAR)

    before_xy = (680, 280)
    peak_xy = (1425, 280)
    _, before_box = paste_native(canvas, before_path, before_xy)
    _, peak_box = paste_native(canvas, peak_path, peak_xy)
    draw.rectangle((before_box[0] - 3, before_box[1] - 3, before_box[2] + 3, before_box[3] + 3), outline=INK, width=3)
    draw.rectangle((peak_box[0] - 3, peak_box[1] - 3, peak_box[2] + 3, peak_box[3] + 3), outline=INK, width=3)
    draw.text((910, 1018), "口型运动前", font=font(SERIF_FONT, 26), fill=INK)
    draw.text((1620, 1018), "口型运动峰值", font=font(SERIF_FONT, 26), fill=INK)

    draw.rounded_rectangle((55, 1080, 2105, 1190), radius=22, outline=INK, width=2, fill=(251, 248, 240))
    draw.text((85, 1097), "知识问答达到项目目标", font=font(TITLE_FONT, 28), fill=INK)
    draw.text((85, 1144), "固定题集 100%｜隐藏题集 93.33%", font=font(BODY_BOLD, 19), fill=INDIGO)
    draw.line((715, 1095, 715, 1175), fill=(193, 202, 202), width=2)
    draw.text((755, 1097), "实时链路关键检查通过", font=font(TITLE_FONT, 28), fill=INK)
    draw.text((755, 1144), "音视频轨｜speaking 状态｜可见口型运动", font=font(BODY_BOLD, 19), fill=INDIGO)
    draw.line((1480, 1095, 1480, 1175), fill=(193, 202, 202), width=2)
    draw.text((1520, 1097), "证据完整可复核", font=font(TITLE_FONT, 28), fill=CINNABAR)
    draw.text((1520, 1144), "逐项报告｜关键时延｜原始证据帧", font=font(BODY_BOLD, 19), fill=CINNABAR)

    out = OUT_DIR / "slide_09.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG", optimize=True)

    final = Image.open(out).convert("RGB")
    before = Image.open(before_path).convert("RGB")
    peak = Image.open(peak_path).convert("RGB")
    if ImageChops.difference(before, final.crop(before_box)).getbbox() is not None:
        raise RuntimeError("Final before-frame pixels differ from source")
    if ImageChops.difference(peak, final.crop(peak_box)).getbbox() is not None:
        raise RuntimeError("Final peak-frame pixels differ from source")
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slide", choices=("7", "8", "9"), default="7")
    args = parser.parse_args()
    if args.slide == "7":
        print(compose_slide_07())
    elif args.slide == "8":
        print(compose_slide_08())
    else:
        print(compose_slide_09())
