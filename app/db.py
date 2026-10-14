"""Доступ к серверу БД и перевод ошибок СУБД в сообщения приложения.

Пользователь никогда не видит системных сообщений PostgreSQL: все ошибки
переводятся в понятные сообщения на русском языке (класс AppError).
"""
from contextlib import contextmanager

import psycopg
from psycopg import errors as pgerr
from psycopg.rows import dict_row

from .config import DB


class AppError(Exception):
    """Ошибка, сообщение которой можно показать пользователю."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field


class DBUnavailable(AppError):
    def __init__(self):
        super().__init__(
            "Нет соединения с сервером базы данных. Убедитесь, что PostgreSQL запущен, "
            "база данных создана (init_db) и параметры подключения в app/config.py верны."
        )


# Сообщения для именованных ограничений целостности
UNIQUE_MESSAGES = {
    "uq_отдел_название": ("Отдел с таким названием уже существует", "название_отдела"),
    "uq_факультет_название": ("Факультет с таким названием уже существует", "название_факультета"),
    "uq_кафедра_название": ("Кафедра с таким названием уже существует", "название_кафедры"),
    "uq_лаборатория_название": ("Лаборатория с таким названием уже существует", "название_лаборатории"),
    "uq_должность_название": ("Такая должность уже есть в справочнике", "название_должности"),
    "uq_ученая_степень_название": ("Такая учёная степень уже есть в справочнике", "название_степени"),
    "uq_ученое_звание_название": ("Такое учёное звание уже есть в справочнике", "название_звания"),
    "uq_тип_телефона_название": ("Такой тип телефона уже есть в справочнике", "название_типа"),
    "uq_телефон_сотрудник_номер": ("У сотрудника указан один и тот же номер телефона дважды", "телефон"),
}

# Кто ссылается на запись (для сообщения при удалении)
FK_REFERRERS = {
    "fk_факультет_отдел": "к отделу относятся факультеты",
    "fk_кафедра_факультет": "к факультету относятся кафедры",
    "fk_лаборатория_кафедра": "к кафедре относятся лаборатории",
    "fk_сотрудник_должность": "эта должность назначена сотрудникам",
    "fk_сотрудник_степень": "эта учёная степень указана у сотрудников",
    "fk_сотрудник_звание": "это учёное звание указано у сотрудников",
    "fk_сотрудник_отдел": "в подразделении работают сотрудники",
    "fk_сотрудник_факультет": "в подразделении работают сотрудники",
    "fk_сотрудник_кафедра": "в подразделении работают сотрудники",
    "fk_сотрудник_лаборатория": "в подразделении работают сотрудники",
    "fk_телефон_тип": "этот тип указан у телефонов сотрудников",
}

CHECK_MESSAGES = {
    "ck_сотрудник_одно_подразделение": ("Сотрудник должен быть закреплён ровно за одним подразделением", "подразделение"),
    "ck_сотрудник_стаж": ("Стаж научно-педагогической работы не может превышать общий стаж", "стаж_нпр"),
}


def translate(e: Exception, op: str = "save") -> AppError:
    """Преобразовать исключение драйвера/СУБД в AppError."""
    if isinstance(e, AppError):
        return e
    if isinstance(e, psycopg.OperationalError):
        return DBUnavailable()
    diag = getattr(e, "diag", None)
    cname = getattr(diag, "constraint_name", None) if diag else None

    if isinstance(e, pgerr.RaiseException):  # исключения, выданные триггерами/процедурами
        return AppError(diag.message_primary, diag.message_hint)
    if isinstance(e, pgerr.UniqueViolation):
        msg, field = UNIQUE_MESSAGES.get(cname, ("Такая запись уже существует", None))
        return AppError(msg, field)
    if isinstance(e, pgerr.ForeignKeyViolation):
        if op == "delete":
            reason = FK_REFERRERS.get(cname, "на неё ссылаются другие данные")
            return AppError(f"Запись нельзя удалить: {reason}.")
        return AppError("Выбранное значение не найдено в справочнике (возможно, оно было удалено). Обновите страницу.")
    if isinstance(e, pgerr.CheckViolation):
        msg, field = CHECK_MESSAGES.get(cname, ("Введённые данные не прошли проверку", None))
        return AppError(msg, field)
    if isinstance(e, pgerr.NotNullViolation):
        return AppError("Не заполнено обязательное поле", getattr(diag, "column_name", None))
    if isinstance(e, pgerr.StringDataRightTruncation):
        return AppError("Введено слишком длинное значение")
    if isinstance(e, pgerr.NumericValueOutOfRange):
        return AppError("Числовое значение вне допустимого диапазона")
    if isinstance(e, pgerr.UndefinedTable) or isinstance(e, pgerr.UndefinedFunction):
        return AppError("Структура базы данных не создана или устарела. Выполните инициализацию (init_db).")
    return AppError("Ошибка при работе с базой данных. Операция не выполнена.")


@contextmanager
def transaction(op: str = "save"):
    """Соединение с открытой транзакцией; ошибки переводятся в AppError."""
    try:
        conn = psycopg.connect(**DB, row_factory=dict_row, connect_timeout=5)
    except psycopg.Error:
        raise DBUnavailable()
    try:
        yield conn
        conn.commit()
    except psycopg.Error as e:
        conn.rollback()
        raise translate(e, op) from e
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, params=None) -> list[dict]:
    with transaction("read") as c:
        return c.execute(sql, params).fetchall()


def query_one(sql, params=None) -> dict | None:
    with transaction("read") as c:
        return c.execute(sql, params).fetchone()


def execute(sql, params=None, op: str = "save"):
    with transaction(op) as c:
        cur = c.execute(sql, params)
        return cur.fetchone() if cur.description else None
