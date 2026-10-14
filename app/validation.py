"""Контроль вводимых данных на стороне приложения (до обращения к БД).

Те же правила продублированы на сервере БД в триггерах, поэтому данные
защищены и при вводе в обход приложения.
"""
import re
from datetime import date

NAME_RE = re.compile(r"^[А-ЯЁа-яёA-Za-z]+([- ][А-ЯЁа-яёA-Za-z]+)*$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9() -]*[0-9]$")

EMPLOYEE_LABELS = {
    "фамилия": "Фамилия",
    "имя": "Имя",
    "отчество": "Отчество",
    "год_рождения": "Год рождения",
    "код_должности": "Должность",
    "специальность_по_диплому": "Специальность по диплому",
    "квалификация_по_диплому": "Квалификация по диплому",
    "вуз_по_диплому": "Вуз (по диплому)",
    "общий_стаж": "Общий стаж работы",
    "стаж_нпр": "Стаж научно-педагогической работы",
    "код_степени": "Учёная степень",
    "код_звания": "Учёное звание",
    "основное_место_работы": "Основное место работы",
    "подразделение": "Подразделение",
    "телефон": "Телефоны",
}


def years_word(n) -> str:
    """Склонение слова «год»: 1 год, 2 года, 5 лет."""
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} год"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} года"
    return f"{n} лет"


def min_birth_year() -> int:
    return 1940


def max_birth_year() -> int:
    return date.today().year - 18


def parse_int(value: str | None):
    value = (value or "").strip()
    if not value:
        return None
    if not re.fullmatch(r"-?\d+", value):
        raise ValueError
    return int(value)


def normalize_phone(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def check_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value)
    if not PHONE_RE.match(value) or not 5 <= len(digits) <= 15:
        return (f"Неверный формат телефона «{value}»: допускаются цифры, пробел, дефис, "
                f"скобки и «+» в начале (5–15 цифр)")
    return None


def validate_employee(form: dict, phones: list[tuple[str, str]], valid_ids: dict) -> tuple[dict, dict]:
    """Проверить карточку сотрудника.

    form    — значения полей (строки);
    phones  — список (код_типа, номер);
    valid_ids — допустимые значения справочников {поле: set(id)} и 'units': set(ключей).
    Возвращает (очищенные данные, ошибки {поле: сообщение}).
    """
    err: dict[str, str] = {}
    data: dict = {}

    for f, maxlen in (("фамилия", 50), ("имя", 50), ("отчество", 50)):
        v = (form.get(f) or "").strip()
        data[f] = v or None
        if not v:
            if f != "отчество":
                err[f] = f"Поле «{EMPLOYEE_LABELS[f]}» обязательно для заполнения"
        elif len(v) > maxlen:
            err[f] = f"Не более {maxlen} символов"
        elif not NAME_RE.match(v):
            err[f] = "Допускаются только буквы, дефис и пробел"

    for f, maxlen, required in (("специальность_по_диплому", 150, True),
                                ("квалификация_по_диплому", 100, True),
                                ("вуз_по_диплому", 200, False),
                                ("основное_место_работы", 200, True)):
        v = (form.get(f) or "").strip()
        data[f] = v or None
        if not v and required:
            err[f] = f"Поле «{EMPLOYEE_LABELS[f]}» обязательно для заполнения"
        elif len(v) > maxlen:
            err[f] = f"Не более {maxlen} символов"

    # Год рождения
    try:
        year = parse_int(form.get("год_рождения"))
        if year is None:
            err["год_рождения"] = "Укажите год рождения"
        elif not min_birth_year() <= year <= max_birth_year():
            err["год_рождения"] = (f"Неверно введен год рождения! "
                                   f"Допустимый диапазон: {min_birth_year()}–{max_birth_year()}")
        data["год_рождения"] = year
    except ValueError:
        err["год_рождения"] = "Год рождения должен быть целым числом"
        data["год_рождения"] = None

    # Стаж
    for f in ("общий_стаж", "стаж_нпр"):
        try:
            v = parse_int(form.get(f))
            data[f] = 0 if v is None else v
            if data[f] < 0:
                err[f] = "Стаж не может быть отрицательным"
        except ValueError:
            err[f] = "Стаж указывается целым числом лет"
            data[f] = 0
    if data.get("год_рождения") and "год_рождения" not in err and "общий_стаж" not in err:
        age = date.today().year - data["год_рождения"]
        if data["общий_стаж"] > age - 14:
            err["общий_стаж"] = (f"Общий стаж не может превышать возраст минус 14 лет: "
                                 f"не более {years_word(max(age - 14, 0))} (возраст сотрудника {years_word(age)})")
    if "общий_стаж" not in err and "стаж_нпр" not in err and data["стаж_нпр"] > data["общий_стаж"]:
        err["стаж_нпр"] = "Стаж научно-педагогической работы не может превышать общий стаж"

    # Значения из справочников
    for f, required in (("код_должности", True), ("код_степени", False), ("код_звания", False)):
        try:
            v = parse_int(form.get(f))
        except ValueError:
            v = -1
        data[f] = v
        if v is None:
            if required:
                err[f] = f"Выберите значение в поле «{EMPLOYEE_LABELS[f]}»"
        elif v not in valid_ids[f]:
            err[f] = "Выбранное значение отсутствует в справочнике"

    unit = (form.get("подразделение") or "").strip()
    data["подразделение"] = unit
    if not unit:
        err["подразделение"] = "Выберите подразделение, в котором работает сотрудник"
    elif unit not in valid_ids["units"]:
        err["подразделение"] = "Выбранное подразделение не найдено"

    # Телефоны
    clean_phones = []
    seen = set()
    phone_errors = []
    for type_id, number in phones:
        number = normalize_phone(number or "")
        if not number and not type_id:
            continue  # пустая строка формы
        if not number:
            phone_errors.append("Не указан номер телефона")
            continue
        msg = check_phone(number)
        if msg:
            phone_errors.append(msg)
            continue
        try:
            t = parse_int(type_id)
        except ValueError:
            t = None
        if t is None or t not in valid_ids["типы"]:
            phone_errors.append(f"Для номера «{number}» не выбран тип телефона")
            continue
        key = re.sub(r"\D", "", number)
        if key in seen:
            phone_errors.append(f"Номер «{number}» указан дважды")
            continue
        seen.add(key)
        clean_phones.append((t, number))
    if phone_errors:
        err["телефон"] = "; ".join(phone_errors)
    data["телефоны"] = clean_phones
    return data, err
