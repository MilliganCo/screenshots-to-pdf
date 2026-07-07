# Screenshots to PDF

Python GUI/utility для сборки длинного PDF из набора скриншотов или изображений. Поддерживает нормализацию ширины, вертикальную склейку, двухколоночный режим и разбиение слишком длинного полотна на несколько PDF-страниц.

## Статус аудита

`merge_screenshots_to_pdf.py` — актуальная версия. Старый файл `merge_screenshots_to_pdf_v1.py` удалён из текущей ветки.

Проект подходит как небольшой public portfolio utility после full-history scan и добавления screenshot/demo.

## Возможности

- выбор набора изображений;
- поддержка `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tif`, `.tiff`;
- crop по минимальной ширине;
- вертикальная склейка;
- двухколоночный режим;
- разбиение длинного полотна на PDF-страницы;
- безопасная очистка имени файла от недопустимых Windows-символов;
- запуск как Python-скрипт или собранный `.exe`.

## Стек

- Python;
- Pillow;
- Tkinter.

## Запуск

```bash
python merge_screenshots_to_pdf.py
```

## Перед публикацией

1. Выполнить full-history secret/data scan.
2. Добавить sample images или synthetic fixtures.
3. Добавить screenshot/GIF интерфейса.
4. Проверить сборку `.exe`, если она заявляется в README.

## License recommendation

MIT.
