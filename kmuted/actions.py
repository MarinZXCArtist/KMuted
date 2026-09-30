"""Every global action that can be bound to a hotkey."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    key: str  # also: GeneralSettings.<key>_hotkey
    title: str  # Russian source; pass through tr() for display
    description: str
    icon: str
    group: str


ACTIONS: list[Action] = [
    Action("input", "Окно ввода текста", "Поле по центру экрана: пишете, Enter — звучит", "keyboard", "Речь"),
    Action("repeat", "Повторить последнюю фразу", "Ещё раз говорит то, что прозвучало последним", "history", "Речь"),
    Action("stop", "Остановить всё", "Обрывает речь и звуки, очищает очередь", "stop", "Речь"),
    Action("stop_sounds", "Остановить звуки", "Только звуки саундборда, речь продолжается", "volume", "Звуки"),
    Action("next_voice", "Следующий голос", "Переключает основной голос по кругу", "voices", "Голоса"),
    Action("prev_voice", "Предыдущий голос", "Переключает голос назад", "voices", "Голоса"),
    Action("mute", "Выключить звук в микрофон", "KMuted перестаёт звучать в микрофоне (живой микрофон не трогается)", "mic", "Звук"),
    Action("monitor", "Прослушка вкл/выкл", "Слышать или не слышать озвучку в наушниках", "headset", "Звук"),
    Action("passthrough", "Живой микрофон вкл/выкл", "Подмешивание настоящего микрофона", "radio", "Звук"),
    Action("volume_up", "Громче в микрофоне", "+10% к громкости озвучки", "volume", "Звук"),
    Action("volume_down", "Тише в микрофоне", "−10% к громкости озвучки", "volume", "Звук"),
    Action("toggle_hotkeys", "Пауза горячих клавиш", "Включает и выключает все остальные клавиши", "power", "Приложение"),
    Action("show_window", "Показать / скрыть KMuted", "Открывает главное окно или прячет его в трей", "home", "Приложение"),
]

ACTION_KEYS = [a.key for a in ACTIONS]


def attr(key: str) -> str:
    return f"{key}_hotkey"
