# Инструменты разработки

[Назад к проекту](../README.md)

Команды ниже выполняются из корня репозитория. Сборку и нативные UI-проверки запускайте Windows Python.

## Ресурсы и сборка

```powershell
python tools\prepare_assets.py
python tools\build_client.py
```

Первая команда создаёт копии ресурсов и адаптированные страницы в `client/frontend/`, обновляет `assets/manifest.json`. Вторая уже включает подготовку ресурсов и собирает `dist/Mogobe/`. Исходные ресурсы в `assets/` и готовые адаптеры нужны в Git; копии frontend и результаты сборки игнорируются.

После изменения `tools/host/MogobeHost.as` пересоберите адаптер с Java 17 и JPEXS 26.3:

```powershell
python tools\build_host.py --java path\to\java.exe --ffdec path\to\ffdec.jar
python tools\build_client.py
```

`build_loading_stub.py` создаёт служебный класс загрузочного экрана; `extract_original_preloader.py` извлекает оригинальную заставку; `build_map_additions.py` извлекает исходную кнопку и остров Бумагленда. Эти шаги не нужны при обычной сборке. `prepare_icon.py` требует Pillow; `verify_exe_icon.py` — Pillow и pefile.

После замены SWF комнаты геометрия извлекается отдельно, с Pillow, Java и JPEXS:

```powershell
python tools\export_room_geometry.py --room FearCaveGate --java path\to\java.exe --ffdec path\to\ffdec.jar
python tools\prepare_room_navigation.py --room FearCaveGate --render-dir tools\exports\room-geometry\renders
```

Без `--room` обрабатываются все комнаты. Однокомнатное обновление сохраняет остальные записи и ID. После импорта проверьте маршруты, метаданные источника и отчёт `assets/original/room-import.json`.

## Проверки настоящего окна Windows

Нужны Python с `httpx` и Pillow и тестовая сборка:

```powershell
python tools\build_client.py --ui-test
python tools\verify_client.py
python tools\verify_client.py --suite spawns
```

| Сценарий `--suite` | Что проверяется |
| --- | --- |
| `world` (по умолчанию) | Один могоби: Новоград, ходьба, `/exit`, повторный вход |
| `spawns` | Стороны перехода, ворота страха, F5 из двух комнат |
| `room-links` | Терем, выставка, дерево, пещера и корабль |
| `map-timing`, `map-ui` | Первый кадр карты, Бумагленд, магазины, бассейн |
| `rooms`, `rooms-all` | Карта и переходы с двумя игроками; дополнительно все 50 комнат |
| `layout` | Профили без мерцания, подсказки, чат и расположение элементов |
| `presence` | Онлайн друзей, экран сервера и `/online` |
| `friends-ui`, `friends` | Интерфейс друзей, мгновенный мут и F5; либо только друзья и мут |
| `social` | Эмоции, магия на другом игроке, друзья и мут |
| `profiles`, `multiplayer` | Карточки; либо два игрока, чат и запрет второго входа |
| `registration` | Полная регистрация и сообщения об ошибках |
| `accounts` | Долгая проверка шести сохранённых могоби |
| `all` | Все сценарии, только при явной необходимости |

Выбирайте проверку по изменению. Обычная сборка не запускает UI-тесты. Сценарии используют временные SQLite и профили, отчёты и снимки создаются в `verification/<suite>/`. Мост управления окном есть только в EXE с тегом `uitest`.

Запускайте UI-сценарии последовательно, без других действий Windows, отнимающих фокус. Кнопка входа оригинального SWF имеет задержку 5 секунд: проверка должна ждать её готовности.
