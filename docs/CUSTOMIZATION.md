# Настройка Codex Prism

Prism отделяет данные от представления: настройка цвета или сворачивание блока не меняют сохранённую команду, reasoning или результат. Текст можно целиком скопировать и экспортировать.

## Конфигурация

`codex-prism --init-config` создаёт `~/.config/codex-prism/config.toml`. Если задан `XDG_CONFIG_HOME`, используется этот каталог. Можно передать отдельный файл: `codex-prism --config ./my-theme.toml`.

Измените файл и нажмите `Ctrl+R`. Ошибка в TOML или значениях оставляет прежнее оформление. Пользовательский CSS, подключённый при запуске, дополнительно отслеживается на диске автоматически; изменение самого пути к CSS требует перезапуска. Изменения recording-настроек применяются при следующем запуске.

```toml
[appearance]
theme = "prism"
syntax_theme = "monokai"
line_numbers = true
wrap = true
show_sidebar = true
output_preview_lines = 4
page_lines = 160
reasoning = "both"

[colors]
background = "#10141c"
surface = "#171d28"
panel = "#1d2533"
foreground = "#dce4f2"
muted = "#8c9cb5"
accent = "#72d5ce"
reasoning = "#c4a7e7"
command = "#e8c07d"
output = "#99b7d7"
assistant = "#8bd5ad"
user = "#8aadf4"
error = "#f28b96"

[syntax]
"Token.Name.Function" = "bold #72d5ce"  # command names
"Token.Name.Attribute" = "#c4a7e7"      # shell flags
"Token.Name.Namespace" = "#99b7d7"      # paths
"Token.Literal.String" = "#a8d49a"
"Token.Literal.Number" = "#efb879"
"Token.Comment" = "italic #71829d"

[keys]
next = "j"
previous = "k"
input = "i"
search = "slash"
toggle_output = "o"
expand_all = "shift+o"
copy_command = "y"
copy_output = "shift+y"
follow = "f"

[behavior]
record = true
compress_recordings = true
css = "custom.tcss"
```

`reasoning = "content"` показывает только доступное поле content, `"summary"` — только summary, `"both"` — оба с отдельными подписями. Это фильтр представления: оба поля остаются в записи и экспорте. Демо использует специально написанные примеры, а не фактические рассуждения модели.

`output_preview_lines`: от 1 до 50. `page_lines`: от 20 до 2000. Постраничная отрисовка предотвращает загрузку десятков тысяч строк в один виджет. Превью не заменяет исходный текст; поиск всегда проходит по всему полученному содержимому. При отключённых переносах код прокручивается горизонтально.

Для подсветки применяются Pygments и отдельный shell-lexer: кавычки и строки разбираются как Bash, а флаги и пути получают собственные токены. Строка `'--literal'` остаётся строкой, а не флагом. Markdown оформляет prose-блоки; его вложенные code fences используют выбранную `syntax_theme`.

Математические блоки используют цвет `reasoning` из палитры. Формулы преобразуются только для отображения: Copy и экспорт сохраняют исходный LaTeX. Для корректных математических символов нужен шрифт терминала с соответствующими Unicode-глифами.

## Собственный CSS

Создайте `custom.tcss` рядом с конфигом:

```css
/* Более плотная лента. */
.trace-card {
    padding: 0 1;
    margin-bottom: 1;
}

/* Больше пространства для длинных команд. */
#sidebar {
    width: 23;
}

/* Свои рамки и цвет подписи reasoning. */
.kind-reasoning {
    border-left: thick #b8a0ee;
}
.reasoning-content-label {
    color: #d7c3ff;
    text-style: bold;
}

/* Увеличить редактор запроса. */
#composer {
    height: 7;
}
```

Полный набор базовых селекторов находится в [app.tcss](../src/codex_prism/app.tcss). Палитра доступна в CSS как `$background`, `$surface`, `$panel`, `$foreground`, `$accent`, `$reasoning`, `$command`, `$output`, `$assistant`, `$user`, `$error`, `$text-muted`.

Это Textual CSS, с размерами в терминальных ячейках. Шрифт и размер символов задаются в настройках вашего терминала. Для true color нужен терминал с поддержкой 24-битного цвета. `NO_COLOR` намеренно отключает цвета.

## Новые возможности в коде

- Новый тип события: нормализуйте его в `model.py`, затем задайте блок в `widgets.py`.
- Новый lexer или правила подсветки: `rendering.py`.
- Новая клавиша/команда: actions и `slash_command` в `app.py`, подсказки в `commands.py`.
- Выбор бесед: `sessions.py`; новые правила формул: `math_rendering.py`.
- Выделение и представление Rich-блоков: `selectable.py`; геометрия областей прокрутки — `.page-scroll` в CSS.
- Новая возможность движка: вызов JSON-RPC в `transport.py` / `app.py`, с проверкой схемы установленной версии.

Модули данных и транспорта не зависят от Textual: позднее поверх них можно сделать другой интерфейс, сохранив записи и редуктор событий.
