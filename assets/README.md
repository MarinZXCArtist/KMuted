# Свои картинки для KMuted

**Русский** · [English](#custom-pictures-for-kmuted)

`banner.jpg` и `wheel_center.png` в этой папке нарисованы программно скриптом
`python tools/make_assets.py` (никаких чужих картинок) — можно перерисовать или заменить своими.

Положите файлы в эту папку — KMuted подхватит их сам, код менять не нужно.
Поддерживаются `.svg`, `.png`, `.webp`, `.jpg`, `.ico`. Если файла нет — используется
встроенная картинка.

| Файл | Где используется | Рекомендуемый размер |
|---|---|---|
| `logo.png` (или `.svg`) | Логотип: окно, боковая панель, панель задач, exe | квадрат, от 256×256, прозрачный фон |
| `tray.png` / `tray.ico` | Значок в трее (если нужен отдельный) | 64×64 |
| `banner.jpg` (или `.png`, `.webp`) | Фон большого баннера на «Главной» | ~1600×400, тёмная левая часть |
| `wheel_center.png` | Картинка в центре колеса фраз | квадрат 256×256 |
| `icons/<имя>.svg` | Замена любой иконки интерфейса | 24×24, `stroke="currentColor"` |

Имена иконок: `home`, `phrases`, `wheel`, `voices`, `audio`, `settings`, `play`, `stop`,
`plus`, `edit`, `trash`, `mic`, `keyboard`, `headset`, `download`, `folder`, `refresh`,
`sparkles`, `send`, `star`, `copy`, `globe`, `cpu`, `windows`, `wand`, `gamepad`, `mouse`,
`search`, `zap`, `volume`, `history`, `info`, `alert`, `check`, `x`, `power`, `radio`, `link`,
`translate`, `swap`, `key`.

В SVG-иконках пишите цвет как `currentColor` — KMuted перекрасит их под тему
(серые в покое, белые на выбранном пункте).

Кроме этой папки KMuted смотрит ещё в `assets` рядом с `KMuted.exe` и в
`%APPDATA%\KMuted\assets` — там удобно держать картинки, не пересобирая программу.
Картинки из `%APPDATA%\KMuted\assets` важнее всех остальных.

---

# Custom pictures for KMuted

[Русский](#свои-картинки-для-kmuted) · **English**

`banner.jpg` and `wheel_center.png` in this folder are drawn by code with
`python tools/make_assets.py` (no third-party images) — redraw them or replace them with your own.

Put files into this folder and KMuted picks them up by itself, no code changes needed.
Supported: `.svg`, `.png`, `.webp`, `.jpg`, `.ico`. If a file is missing, the built-in picture is used.

| File | Where it's used | Recommended size |
|---|---|---|
| `logo.png` (or `.svg`) | Logo: window, sidebar, taskbar, exe | square, 256×256 or more, transparent background |
| `tray.png` / `tray.ico` | Tray icon (if you want a separate one) | 64×64 |
| `banner.jpg` (or `.png`, `.webp`) | Background of the big banner on the Home page | ~1600×400, dark left part |
| `wheel_center.png` | Picture in the center of the phrase wheel | square 256×256 |
| `icons/<name>.svg` | Replaces any interface icon | 24×24, `stroke="currentColor"` |

Icon names are listed above (`home`, `phrases`, `wheel`, … `translate`, `swap`, `key`).

In SVG icons write the color as `currentColor` — KMuted recolors them for the theme
(grey at rest, white on the selected item).

Besides this folder KMuted also looks in `assets` next to `KMuted.exe` and in
`%APPDATA%\KMuted\assets` — handy for keeping pictures without rebuilding the app.
Pictures in `%APPDATA%\KMuted\assets` win over all others.
