from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from PIL import Image


@dataclass(frozen=True)
class CropSpec:
    target_width: int
    anchor: str  # "center" | "left" | "right"


SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")


def _is_supported_image(path: str) -> bool:
    return os.path.isfile(path) and path.lower().endswith(SUPPORTED_EXTS)


def _open_image_rgb(path: str) -> Image.Image:
    im = Image.open(path)
    try:
        if im.mode != "RGB":
            im = im.convert("RGB")
        return im
    except Exception:
        im.close()
        raise


def _compute_min_width(paths: Sequence[str]) -> int:
    min_w = None
    for p in paths:
        with Image.open(p) as im:
            w, _h = im.size
            min_w = w if min_w is None else min(min_w, w)
    if min_w is None:
        raise ValueError("Нет изображений для обработки.")
    if min_w <= 0:
        raise ValueError("Некорректная ширина изображения.")
    return int(min_w)


def _crop_to_width(im: Image.Image, spec: CropSpec) -> Image.Image:
    w, h = im.size
    tw = spec.target_width
    if tw >= w:
        return im

    if spec.anchor == "left":
        left = 0
    elif spec.anchor == "right":
        left = w - tw
    else:  # center
        left = (w - tw) // 2
    right = left + tw
    return im.crop((left, 0, right, h))


def _concat_vertical(images: Sequence[Image.Image], background_rgb=(255, 255, 255)) -> Image.Image:
    if not images:
        raise ValueError("Список изображений пуст.")
    w = images[0].size[0]
    total_h = sum(im.size[1] for im in images)
    out = Image.new("RGB", (w, total_h), background_rgb)
    y = 0
    for im in images:
        out.paste(im, (0, y))
        y += im.size[1]
    return out


def _concat_horizontal(
    left: Image.Image,
    right: Image.Image,
    background_rgb=(255, 255, 255),
) -> Image.Image:
    total_w = left.size[0] + right.size[0]
    total_h = max(left.size[1], right.size[1])
    out = Image.new("RGB", (total_w, total_h), background_rgb)
    out.paste(left, (0, 0))
    out.paste(right, (left.size[0], 0))
    return out


def _split_into_pages(long_image: Image.Image, max_page_height: int) -> List[Image.Image]:
    w, h = long_image.size
    if h <= max_page_height:
        return [long_image]
    pages: List[Image.Image] = []
    top = 0
    while top < h:
        bottom = min(top + max_page_height, h)
        pages.append(long_image.crop((0, top, w, bottom)))
        top = bottom
    return pages


def build_pdf(
    first_path: str,
    left_paths: Sequence[str],
    right_paths: Sequence[str],
    output_pdf_path: str,
    *,
    crop_anchor: str = "center",
    max_page_height: int = 65000,
) -> Tuple[str, int]:
    left_all = [first_path, *left_paths]
    bad = [p for p in left_all if not _is_supported_image(p)]
    if bad:
        raise ValueError("Некоторые файлы левой колонки не похожи на изображения:\n" + "\n".join(bad))
    n_left = len(left_all)
    if right_paths:
        if len(right_paths) != n_left:
            raise ValueError(
                f"Количество изображений правой колонки ({len(right_paths)}) должно совпадать "
                f"с количеством слева ({n_left} = первый + низ левой колонки)."
            )
        bad_r = [p for p in right_paths if not _is_supported_image(p)]
        if bad_r:
            raise ValueError("Некоторые файлы правой колонки не похожи на изображения:\n" + "\n".join(bad_r))

    min_w_left = _compute_min_width(left_all)
    spec_left = CropSpec(target_width=min_w_left, anchor=crop_anchor)
    bg = (255, 255, 255)

    opened: List[Image.Image] = []
    try:
        left_images: List[Image.Image] = []
        for p in left_all:
            im = _open_image_rgb(p)
            left_images.append(_crop_to_width(im, spec_left))
            opened.append(left_images[-1])

        if right_paths:
            min_w_right = _compute_min_width(right_paths)
            spec_right = CropSpec(target_width=min_w_right, anchor=crop_anchor)
            right_images: List[Image.Image] = []
            for p in right_paths:
                im = _open_image_rgb(p)
                right_images.append(_crop_to_width(im, spec_right))
                opened.append(right_images[-1])

            right_cells: List[Image.Image] = []
            for i in range(n_left):
                lh = left_images[i].size[1]
                rimg = right_images[i]
                rw, rh = rimg.size
                scaled_w = max(1, round(rw * lh / rh)) if rh > 0 else rw
                scaled = rimg.resize((scaled_w, lh), Image.Resampling.LANCZOS)
                right_cells.append(scaled)
                opened.append(scaled)

            w_right = max(c.size[0] for c in right_cells)
            rows: List[Image.Image] = []
            for i in range(n_left):
                cell = Image.new("RGB", (w_right, left_images[i].size[1]), bg)
                rc = right_cells[i]
                x = (w_right - rc.size[0]) // 2
                cell.paste(rc, (x, 0))
                row = _concat_horizontal(left_images[i], cell, bg)
                rows.append(row)
            long_page = _concat_vertical(rows)
        else:
            long_page = _concat_vertical(left_images)

        pages = _split_into_pages(long_page, max_page_height=max_page_height)

        os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)) or ".", exist_ok=True)
        first = pages[0]
        rest = pages[1:]
        first.save(output_pdf_path, "PDF", save_all=True, append_images=rest)
        return output_pdf_path, len(pages)
    finally:
        for im in opened:
            try:
                im.close()
            except Exception:
                pass


def _sanitize_article_to_basename(article: str) -> str:
    a = (article or "").strip()
    if not a:
        raise ValueError("Артикул пустой.")
    # Windows-friendly filename: keep letters/digits/_/-
    a = re.sub(r"[^0-9A-Za-z_-]+", "_", a)
    a = a.strip("._-")
    if not a:
        raise ValueError("Артикул после очистки пустой.")
    return a


def _ask_article_gui(root) -> str:
    import tkinter as tk
    from tkinter import messagebox

    win = tk.Toplevel(root)
    win.title("Артикул")
    win.resizable(False, False)
    win.attributes("-topmost", True)

    tk.Label(win, text="Введите артикул (имя PDF):").grid(row=0, column=0, padx=12, pady=(12, 6), sticky="w")
    entry = tk.Entry(win, width=32)
    entry.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="we")
    entry.focus_set()

    result = {"value": None}

    def submit() -> None:
        try:
            result["value"] = _sanitize_article_to_basename(entry.get())
            win.destroy()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=win)

    def cancel() -> None:
        result["value"] = None
        win.destroy()

    btns = tk.Frame(win)
    btns.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="e")
    tk.Button(btns, text="OK", width=10, command=submit).pack(side="right", padx=(6, 0))
    tk.Button(btns, text="Отмена", width=10, command=cancel).pack(side="right")

    win.protocol("WM_DELETE_WINDOW", cancel)
    win.bind("<Return>", lambda _e: submit())
    win.bind("<Escape>", lambda _e: cancel())

    win.grab_set()
    root.wait_window(win)
    if not result["value"]:
        raise SystemExit("Отменено: артикул не введён.")
    return str(result["value"])


def _pick_files_gui() -> Tuple[str, List[str], List[str], str]:
    # Tkinter is bundled with the standard Python install on Windows (python.org).
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    paths = list(
        filedialog.askopenfilenames(
            title="Выберите скриншоты по порядку: левая 1, правая 1, левая 2, правая 2, ... (чётное кол-во)",
            filetypes=[("Изображения", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff"), ("Все файлы", "*.*")],
        )
    )
    if not paths:
        raise SystemExit("Отменено: файлы не выбраны.")

    if len(paths) % 2 != 0:
        messagebox.showerror(
            "Ошибка",
            f"Выбрано {len(paths)} файлов. Нужно чётное количество:\n"
            "левая 1, правая 1, левая 2, правая 2, …",
            parent=root,
        )
        raise SystemExit("Нужно чётное количество изображений.")

    left_paths = paths[0::2]
    right_paths = paths[1::2]
    first = left_paths[0]
    left_rest = left_paths[1:]

    article = _ask_article_gui(root)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{article}.pdf")
    if os.path.exists(out):
        if not messagebox.askyesno(
            "Файл уже существует",
            f"Файл уже существует:\n{out}\n\nПерезаписать?",
        ):
            raise SystemExit("Отменено: файл уже существует.")

    return first, left_rest, right_paths, out


def main() -> int:
    try:
        first, left_paths, right_paths, out_pdf = _pick_files_gui()
        out_path, pages = build_pdf(first, left_paths, right_paths, out_pdf, crop_anchor="center")
        print(f"Готово: {out_path}")
        if pages > 1:
            print(
                "Примечание: итоговая «длинная страница» оказалась слишком высокой, "
                "поэтому PDF был автоматически разбит на несколько страниц."
            )
        return 0
    except SystemExit as e:
        msg = str(e)
        if msg:
            print(msg)
        return 2
    except Exception as e:
        print("Ошибка:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
