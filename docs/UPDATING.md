# Обновления Codex без переноса патчей

Prism — отдельный клиент к `codex app-server`. Обновление движка не требует merge исходников OpenAI. Рабочая версия движка выбирается через PATH или `codex-prism --codex /absolute/path/to/package/bin/codex`.

## Ежедневная проверка

Workflow [Check upstream Codex](../.github/workflows/codex-update.yml) запускается ежедневно в **06:37 UTC** (GitHub может задерживать cron), вручную через Actions → Run workflow и при изменении самого механизма проверки в `main`.

1. Получает последний опубликованный стабильный релиз `openai/codex`; prerelease, неизвестные теги и версии ниже эталона/уже принятого отчета отклоняются.
2. Скачивает **полный standalone-пакет Linux x86_64 musl**, проверяет SHA-256 из GitHub API, manifest и версию исполняемого файла. Неполный пакет вместо полного автоматически не подставляется.
3. Выполняет линтер, форматирование, offline-тесты, сборку, структурную проверку протокола и handshake. Движок получает временный профиль без токенов пользователя/GitHub; ходы модели не запускаются.
4. В отдельной задаче с правами записи создает/обновляет PR из `automation/codex-update`, меняющий только `docs/codex-candidate.json`. Не включает auto-merge и не заменяет установленный движок.

После merge отчета ежедневная проверка пропускает этот релиз. Ручной запуск и изменение механизма проверки повторно проверяют текущую версию. До merge один PR обновляется, дубликаты веток не создаются. При ошибке PR не создается, workflow красный, диагностика доступна в артефакте `codex-check-report` (30 дней). Включите уведомления об ошибках Actions в своем GitHub, если нужны оповещения.

**Однократная настройка GitHub:** Settings → Actions → General → Workflow permissions → **Allow GitHub Actions to create and approve pull requests**. Workflow сам запрашивает `contents: write` и `pull-requests: write` только для задачи создания PR. Если политика организации запрещает это, отчет останется артефактом, а шаг создания PR завершится ошибкой. Личный PAT или OpenAI API key не требуются.

PR, созданный через `GITHUB_TOKEN`, может не запускать обычные `pull_request` workflows. Поэтому тесты и сборка выполняются **до** создания PR; ссылка на проверенный запуск есть в его описании. Если branch protection требует отдельного PR check, настройте его отдельно — этот workflow не обходит защиту ветки. [Ограничения GITHUB_TOKEN](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token).

## Проверить вручную без модели

```bash
uv sync --locked
uv run python scripts/check_codex_update.py
# Или повторно проверить конкретный стабильный релиз:
uv run python scripts/check_codex_update.py --version 0.154.0 --force
```

Отчеты сохраняются в игнорируемый `private/codex-update/`. Временный пакет удаляется после проверки. `--force` разрешает повторную проверку, но не downgrade. Скрипт самостоятельно проверяет пакет/протокол/handshake; полный offline-набор отдельно: `uv run pytest -q` и `uv build`.

## Переключить рабочий движок

1. Сохраните **полный** старый пакет вместе с ресурсами и вспомогательными исполняемыми файлами. Установите кандидат отдельно штатным способом; запишите абсолютные пути к обоим `bin/codex`.
2. Выполните проверки кандидата, явно указывая его путь:

```bash
codex-prism --codex /path/to/candidate/bin/codex --doctor
uv run python scripts/check_protocol.py --codex /path/to/candidate/bin/codex
codex-prism --codex /path/to/candidate/bin/codex
```

3. В отдельной тестовой беседе проверьте полный вывод команды, оба реально доступных reasoning-потока, подтверждение и отказ, Ctrl+X, возобновление беседы после перезапуска. Схема и handshake не доказывают эти свойства. Дополнительный `uv run python scripts/smoke_live.py --codex /path/to/candidate/bin/codex` расходует **один настоящий ход модели** на `printf`; он не покрывает весь этот список и в CI не запускается.
4. После успешной проверки используйте кандидат в своем launcher/PATH. Для отката запускайте Prism с путем к сохраненному старому пакету. Merge автоматического PR сам по себе ничего локально не переключает.

## Если поменялся протокол

Проверка сравнивает структуры используемых полей, включая определения за `$ref`, типы/enum/ограничения, доступность методов и обязательные поля запросов. Новые необязательные поля верхнего уровня допускаются. Измененные вложенные структуры требуют разбора, даже если изменение совместимо. Полное покрытие upstream API не заявляется.

Посмотрите `protocol.json` из артефакта, адаптируйте `transport.py`, `model.py`, `app.py` или `widgets.py` по необходимости и добавьте регрессионную проверку конкретного изменения. После ручного разбора и проверки поведения обновите эталон отдельным коммитом:

```bash
uv run python scripts/check_protocol.py --codex /path/to/reviewed/bin/codex --capture-baseline
git diff -- docs/protocol-baseline.json
uv run python scripts/check_protocol.py --codex /path/to/reviewed/bin/codex
uv run pytest -q
```

CI никогда не выполняет `--capture-baseline`. Это позволяет обнаруживать изменения, а не автоматически объявлять любую новую схему совместимой. Команда `--write` обновляет только отчет структурной проверки `docs/compatibility.json`, без утверждения о проверке модели.
