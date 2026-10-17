"""Available chat commands; the UI retrieves this only when /help is opened."""

COMMON = (
    ("/help", "Справка по командам"),
    ("/room ключ", "Перейти в локацию"),
    ("/shop ключ", "Открыть магазин"),
    ("/online", "Узнать число игроков"),
    ("/exit", "Вернуться к выбору могоби"),
)
ADMIN = (
    ("/alert текст", "Объявление всем игрокам"),
    ("/give item ID [ник]", "Выдать вещь"),
    ("/give exp N [ник]", "Начислить опыт"),
    ("/give coins N [ник]", "Начислить монеты"),
)


def available(is_admin):
    commands = [
        {"syntax": syntax, "description": description, "admin_only": False}
        for syntax, description in COMMON
    ]
    if is_admin:
        commands += [
            {"syntax": syntax, "description": description, "admin_only": True}
            for syntax, description in ADMIN
        ]
    return {
        "commands": commands,
        "shortcuts": [{"syntax": "F5", "description": "Переподключиться"}],
        "notes": ["Часть магазинов доступна только администраторам."]
        + (["В /give ник необязателен: без ника выдача себе."] if is_admin else []),
    }
