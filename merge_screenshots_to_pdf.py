from __future__ import annotations

import os
import re
import sys


def _get_base_dir() -> str:
    """Папка рядом с программой (скрипт или exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
from dataclasses import dataclass
from tkinter import filedialog, messagebox
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageTk


@dataclass(frozen=True)
class CropSpec:
    target_width: int
    anchor: str


SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
THUMB_SIZE = (320, 240)
HIGHLIGHT_BG = "#cce5ff"
NORMAL_BG = "#f0f0f0"
BORDER_HIGHLIGHT = 3


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
    return max(1, int(min_w))


def _crop_to_width(im: Image.Image, spec: CropSpec) -> Image.Image:
    w, h = im.size
    tw = spec.target_width
    if tw >= w:
        return im
    left = (w - tw) // 2 if spec.anchor == "center" else (0 if spec.anchor == "left" else w - tw)
    return im.crop((left, 0, left + tw, h))


def _concat_vertical(images: Sequence[Image.Image], bg=(255, 255, 255)) -> Image.Image:
    w = images[0].size[0]
    total_h = sum(im.size[1] for im in images)
    out = Image.new("RGB", (w, total_h), bg)
    y = 0
    for im in images:
        out.paste(im, (0, y))
        y += im.size[1]
    return out


def _concat_horizontal(left: Image.Image, right: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    total_w = left.size[0] + right.size[0]
    total_h = max(left.size[1], right.size[1])
    out = Image.new("RGB", (total_w, total_h), bg)
    out.paste(left, (0, 0))
    out.paste(right, (left.size[0], 0))
    return out


def _split_into_pages(img: Image.Image, max_h: int) -> List[Image.Image]:
    w, h = img.size
    if h <= max_h:
        return [img]
    pages: List[Image.Image] = []
    top = 0
    while top < h:
        bottom = min(top + max_h, h)
        pages.append(img.crop((0, top, w, bottom)))
        top = bottom
    return pages


def build_pdf(
    left_paths: Sequence[str],
    right_paths: Sequence[str],
    output_pdf_path: str,
    *,
    crop_anchor: str = "center",
    max_page_height: int = 65000,
) -> Tuple[str, int]:
    if not left_paths:
        raise ValueError("Нет изображений.")
    if right_paths and len(right_paths) != len(left_paths):
        raise ValueError(f"Кол-во слева ({len(left_paths)}) и справа ({len(right_paths)}) должно совпадать.")
    bad = [p for p in left_paths + list(right_paths) if not _is_supported_image(p)]
    if bad:
        raise ValueError("Некорректные файлы:\n" + "\n".join(bad[:5]))

    spec_left = CropSpec(target_width=_compute_min_width(left_paths), anchor=crop_anchor)
    spec_right = CropSpec(target_width=_compute_min_width(right_paths), anchor=crop_anchor) if right_paths else None
    bg = (255, 255, 255)
    opened: List[Image.Image] = []

    try:
        left_ims = []
        for p in left_paths:
            im = _open_image_rgb(p)
            left_ims.append(_crop_to_width(im, spec_left))
            opened.append(left_ims[-1])

        if right_paths:
            right_ims = []
            for p in right_paths:
                im = _open_image_rgb(p)
                right_ims.append(_crop_to_width(im, spec_right))
                opened.append(right_ims[-1])
            right_cells = []
            for i in range(len(left_ims)):
                lh = left_ims[i].size[1]
                rimg = right_ims[i]
                rw, rh = rimg.size
                sw = max(1, round(rw * lh / rh)) if rh > 0 else rw
                scaled = rimg.resize((sw, lh), Image.Resampling.LANCZOS)
                right_cells.append(scaled)
                opened.append(scaled)
            w_right = max(c.size[0] for c in right_cells)
            rows = []
            for i in range(len(left_ims)):
                cell = Image.new("RGB", (w_right, left_ims[i].size[1]), bg)
                rc = right_cells[i]
                x = (w_right - rc.size[0]) // 2
                cell.paste(rc, (x, 0))
                row = _concat_horizontal(left_ims[i], cell, bg)
                rows.append(row)
            long_page = _concat_vertical(rows)
        else:
            long_page = _concat_vertical(left_ims)

        pages = _split_into_pages(long_page, max_page_height)
        out_dir = os.path.dirname(os.path.abspath(output_pdf_path)) or "."
        os.makedirs(out_dir, exist_ok=True)
        first, rest = pages[0], pages[1:]
        first.save(output_pdf_path, "PDF", save_all=True, append_images=rest)
        return output_pdf_path, len(pages)
    finally:
        for im in opened:
            try:
                im.close()
            except Exception:
                pass


# Недопустимые символы в имени файла Windows: \ / : * ? " < > |
_INVALID_FILENAME_CHARS = r'[\\/:*?"<>|]'


def _sanitize_article(s: str) -> str:
    a = (s or "").strip()
    a = re.sub(_INVALID_FILENAME_CHARS, "_", a)
    a = re.sub(r"_+", "_", a).strip("._-\t")  # схлопнуть подчёркивания, обрезать края (пробелы в названии сохраняем)
    if not a:
        raise ValueError("Артикул пустой.")
    return a


def _make_thumbnail(path: str) -> ImageTk.PhotoImage:
    im = Image.open(path)
    im.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
    if im.mode != "RGB":
        im = im.convert("RGB")
    return ImageTk.PhotoImage(im)


_PLACEHOLDER: Optional[ImageTk.PhotoImage] = None


def _make_placeholder() -> ImageTk.PhotoImage:
    global _PLACEHOLDER
    if _PLACEHOLDER is None:
        im = Image.new("RGB", THUMB_SIZE, (240, 240, 240))
        _PLACEHOLDER = ImageTk.PhotoImage(im)
    return _PLACEHOLDER


class ImageSlot:
    def __init__(self, parent, index: int, path: Optional[str], on_replace, on_delete, on_drag_start, on_drag_end):
        self.index = index
        self.path = path
        self.on_replace = on_replace
        self.on_delete = on_delete
        self.on_drag_start = on_drag_start
        self.on_drag_end = on_drag_end
        self.photo: Optional[ImageTk.PhotoImage] = None

        self._container = None
        self._img_label = None
        self._filename_label = None
        self._delete_btn = None
        self._widget = None
        self._hover = False

    def _show_overlay(self) -> None:
        if self._filename_label:
            self._filename_label.place(relx=0, rely=1, x=0, y=-1, anchor="sw")
        if self._delete_btn and self.path:
            self._delete_btn.place(relx=1, rely=0, x=-1, y=1, anchor="ne")

    def _hide_overlay(self) -> None:
        if self._filename_label:
            self._filename_label.place_forget()
        if self._delete_btn:
            self._delete_btn.place_forget()

    def build(self, master, col: int, row: int):
        t = __import__("tkinter")
        container = t.Frame(master, bg=NORMAL_BG, highlightthickness=1, highlightbackground="#999")
        self._container = container
        self._widget = img_label = t.Label(container, image="", text="", bg=NORMAL_BG, cursor="hand2")
        self._img_label = img_label
        img_label.pack()

        self._filename_label = t.Label(
            container, text="", bg="#333", fg="white", font=("", 8), padx=4, pady=2,
        )
        self._filename_label.place(relx=0, rely=1, x=0, y=-1, anchor="sw")

        self._delete_btn = t.Label(
            container, text=" ✕ ", bg="#c00", fg="white", font=("", 10, "bold"), cursor="hand2",
        )
        self._delete_btn.place(relx=1, rely=0, x=-1, y=1, anchor="ne")
        self._delete_btn.bind("<Button-1>", self._on_delete_click)

        self._update_display()
        self._update_filename()
        self._hide_overlay()

        container.bind("<Enter>", self._on_enter)
        container.bind("<Leave>", self._on_leave)
        img_label.bind("<Double-Button-1>", self._on_dbl)
        img_label.bind("<ButtonPress-1>", self._on_press)
        img_label.bind("<ButtonRelease-1>", self._on_release)
        img_label.bind("<Button-3>", self._on_right)
        img_label.bind("<Delete>", self._on_delete)
        return container

    def _update_display(self) -> None:
        w = self._widget
        if not w:
            return
        if self.path and os.path.isfile(self.path):
            try:
                self.photo = _make_thumbnail(self.path)
                w.configure(image=self.photo, text="")
            except Exception:
                self.photo = _make_placeholder()
                w.configure(image=self.photo, text="")
        else:
            self.photo = _make_placeholder()
            w.configure(image=self.photo, text="")

    def _on_enter(self, e=None) -> None:
        self._hover = True
        if self._container:
            self._container.configure(bg=HIGHLIGHT_BG, highlightthickness=BORDER_HIGHLIGHT, highlightbackground="#0066cc")
        self._show_overlay()

    def _on_leave(self, e=None) -> None:
        self._hover = False
        if self._container:
            self._container.configure(bg=NORMAL_BG, highlightthickness=1, highlightbackground="#999")
        self._hide_overlay()

    def _on_delete_click(self, e=None) -> None:
        self.on_delete(self.index)
        return "break"

    def _update_filename(self) -> None:
        if self._filename_label:
            name = os.path.basename(self.path) if self.path else "—"
            self._filename_label.configure(text=name)

    def _on_dbl(self, e=None) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите изображение",
            filetypes=[("Изображения", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff"), ("Все файлы", "*.*")],
        )
        if paths:
            self.on_replace(self.index, paths[0])

    def _on_press(self, e) -> None:
        self._widget.focus_set()
        self.on_drag_start(self.index, e)

    def _on_release(self, e) -> None:
        self.on_drag_end(self.index, e)

    def _on_right(self, e) -> None:
        menu = __import__("tkinter").Menu(self._widget, tearoff=0)
        menu.add_command(label="Заменить (двойной клик)", command=lambda: self._on_dbl())
        menu.add_command(label="Удалить", command=lambda: self.on_delete(self.index))
        menu.tk_popup(e.x_root, e.y_root)

    def _on_delete(self, e=None) -> None:
        self.on_delete(self.index)

    def refresh(self) -> None:
        self._update_display()
        self._update_filename()


class App:
    def __init__(self):
        import tkinter as tk
        self.tk = tk
        self.root = tk.Tk()
        self.root.title("Скриншоты → PDF")
        self.root.minsize(500, 400)
        self.root.geometry("900x700")

        self.paths: List[Optional[str]] = []
        self.slots: List[ImageSlot] = []
        self.drag_index: Optional[int] = None
        self._thumb_refs: List[ImageTk.PhotoImage] = []

        self._build_ui()

    def _build_ui(self) -> None:
        t = self.tk
        top = t.Frame(self.root, padx=8, pady=8)
        top.pack(fill="x")

        t.Label(top, text="Артикул:").pack(side="left", padx=(0, 6))
        self.article_entry = t.Entry(top, width=24)
        self.article_entry.pack(side="left", padx=(0, 12))
        self.article_entry.insert(0, "MJMFUT000195U")

        t.Button(top, text="Выбрать файлы", command=self._add_files).pack(side="left", padx=2)
        t.Button(top, text="Экспорт PDF", command=self._export).pack(side="left", padx=2)
        t.Button(top, text="Очистить", command=self._clear).pack(side="left", padx=2)

        hint_frame = t.Frame(self.root)
        hint_frame.pack(fill="x", padx=8)
        t.Label(hint_frame, text="Двойной клик = заменить | ПКМ = меню | Delete = удалить | Перетаскивание = поменять местами", font=("", 8), fg="gray").pack(anchor="w")

        canvas_frame = t.Frame(self.root)
        canvas_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.canvas = t.Canvas(canvas_frame, bg="#e8e8e8")
        sb_y = t.Scrollbar(canvas_frame)
        sb_x = t.Scrollbar(canvas_frame, orient="horizontal")

        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        sb_y.config(command=self.canvas.yview)
        sb_x.config(command=self.canvas.xview)
        self.canvas.config(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        self.grid_frame = t.Frame(self.canvas)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        self.grid_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_frame_configure(self, e=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e=None) -> None:
        self.canvas.itemconfig(self.canvas_window, width=self.canvas.winfo_width())

    def _clear(self) -> None:
        self.paths.clear()
        self._rebuild_grid()

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Выберите скриншоты: левая 1, правая 1, левая 2, правая 2, …",
            filetypes=[("Изображения", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff"), ("Все файлы", "*.*")],
        )
        if paths:
            for p in paths:
                if _is_supported_image(p):
                    self.paths.append(p)
            self._rebuild_grid()

    def _rebuild_grid(self) -> None:
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.slots.clear()
        self._thumb_refs.clear()

        t = self.tk
        n = len(self.paths)
        n_slots = max(2, (n + 1) // 2 * 2) if n else 0
        rows = n_slots // 2

        if n == 0:
            t.Label(self.grid_frame, text="Нажмите «Выбрать файлы» для загрузки скриншотов", fg="gray", font=("", 11)).grid(row=0, column=0, columnspan=2, pady=40)
            self._on_frame_configure()
            return

        if rows > 0:
            t.Label(self.grid_frame, text="Левая", font=("", 9, "bold")).grid(row=0, column=0, pady=(0, 2))
            t.Label(self.grid_frame, text="Правая", font=("", 9, "bold")).grid(row=0, column=1, pady=(0, 2))
            row_offset = 1
        else:
            row_offset = 0

        for i in range(n_slots):
            path = self.paths[i] if i < n else None
            slot = ImageSlot(
                self.grid_frame, i,
                path,
                on_replace=self._replace,
                on_delete=self._delete,
                on_drag_start=self._drag_start,
                on_drag_end=self._drag_end,
            )
            self.slots.append(slot)
            row, col = i // 2 + row_offset, i % 2
            container = slot.build(self.grid_frame, col, row)
            container.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

        for c in range(2):
            self.grid_frame.columnconfigure(c, weight=1)
        for r in range(max(1, row_offset + rows)):
            self.grid_frame.rowconfigure(r, weight=1)

        self._on_frame_configure()

    def _replace(self, index: int, new_path: str) -> None:
        if index >= len(self.paths):
            self.paths.append(new_path)
            self._rebuild_grid()
        else:
            self.paths[index] = new_path
            if index < len(self.slots):
                self.slots[index].path = new_path
                self.slots[index].refresh()

    def _delete(self, index: int) -> None:
        if 0 <= index < len(self.paths):
            self.paths.pop(index)
            self._rebuild_grid()

    def _drag_start(self, index: int, e) -> None:
        self.drag_index = index

    def _drag_end(self, index: int, e) -> None:
        if self.drag_index is None:
            return
        src = self.drag_index
        self.drag_index = None
        root = self.root
        sx, sy = root.winfo_pointerxy()
        target_idx = None
        for i, s in enumerate(self.slots):
            w = s._container if s._container else s._widget
            if w and w.winfo_ismapped():
                try:
                    wx = w.winfo_rootx()
                    wy = w.winfo_rooty()
                    ww = w.winfo_width()
                    wh = w.winfo_height()
                    if wx <= sx <= wx + ww and wy <= sy <= wy + wh:
                        target_idx = i
                        break
                except Exception:
                    pass
        if target_idx is not None and src != target_idx:
            n = len(self.paths)
            a, b = src, target_idx
            if a < n and b < n:
                self.paths[a], self.paths[b] = self.paths[b], self.paths[a]
                self.slots[a].path = self.paths[a]
                self.slots[b].path = self.paths[b]
                self.slots[a].refresh()
                self.slots[b].refresh()
            elif a < n and b >= n:
                self.paths.append(self.paths[a])
                self.paths.pop(a)
                self._rebuild_grid()

    def _export(self) -> None:
        valid = [p for p in self.paths if p and _is_supported_image(p)]
        if not valid:
            messagebox.showwarning("Ошибка", "Нет изображений для экспорта.", parent=self.root)
            return
        if len(valid) % 2 != 0:
            messagebox.showerror("Ошибка", "Нужно чётное количество изображений (левая 1, правая 1, …).", parent=self.root)
            return
        try:
            name = _sanitize_article(self.article_entry.get())
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e), parent=self.root)
            return
        out = os.path.join(_get_base_dir(), f"{name}.pdf")
        if os.path.exists(out):
            if not messagebox.askyesno("Перезаписать?", f"Файл существует:\n{out}\nПерезаписать?", parent=self.root):
                return
        left = valid[0::2]
        right = valid[1::2]
        try:
            path, pages = build_pdf(left, right, out, crop_anchor="center")
            messagebox.showinfo("Готово", f"PDF сохранён:\n{path}\nСтраниц: {pages}", parent=self.root)
        except Exception as ex:
            messagebox.showerror("Ошибка", str(ex), parent=self.root)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    try:
        App().run()
        return 0
    except SystemExit as e:
        print(str(e) or "Выход")
        return 2
    except Exception as e:
        print("Ошибка:", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
