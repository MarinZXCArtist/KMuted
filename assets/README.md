# Свои картинки для KMuted

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
