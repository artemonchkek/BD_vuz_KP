"""Описание простых таблиц (подразделения и справочники) для общих форм
«таблица» и «редактирование записи»."""
from dataclasses import dataclass, field


@dataclass
class Field:
    name: str                 # столбец таблицы БД
    label: str                # подпись на форме
    kind: str = "text"        # text | select | checkbox
    required: bool = True
    maxlen: int = 150
    options_sql: str | None = None   # для select: SELECT id, title ...
    hint: str = ""


@dataclass
class Entity:
    slug: str
    table: str
    pk: str
    title: str                # заголовок списка (мн. ч.)
    one: str                  # «отдел», «кафедру» — для «Добавить ...», «Изменить ...»
    group: str                # structure | dict
    fields: list[Field]
    list_sql: str             # SELECT id, ... — столбцы списка
    columns: list[tuple[str, str]]
    unit_type: str | None = None    # тип подразделения для карточки
    parent_param: str | None = None  # поле-родитель (подставляется из ?parent=)
    child_slug: str | None = None
    child_one: str | None = None
    extra: dict = field(default_factory=dict)


ENTITIES: dict[str, Entity] = {}


def _add(e: Entity):
    ENTITIES[e.slug] = e


_add(Entity(
    slug="otdel", table="отдел", pk="номер_отдела", title="Отделы", one="отдел", group="structure",
    unit_type="отдел", child_slug="fakultet", child_one="факультет",
    fields=[Field("название_отдела", "Название отдела", hint="Например: «Отдел кадров», «Энергетический институт»")],
    list_sql="""SELECT o.номер_отдела AS id, o.название_отдела AS название,
                       (SELECT count(*) FROM факультет f WHERE f.номер_отдела = o.номер_отдела) AS дочерних,
                       (SELECT count(*) FROM v_сотрудник v WHERE v.отдел_ид = o.номер_отдела) AS сотрудников
                FROM отдел o""",
    columns=[("id", "№ отдела"), ("название", "Название отдела"), ("дочерних", "Факультетов"),
             ("сотрудников", "Сотрудников (всего)")],
))

_add(Entity(
    slug="fakultet", table="факультет", pk="код_факультета", title="Факультеты", one="факультет",
    group="structure", unit_type="факультет", parent_param="номер_отдела",
    child_slug="kafedra", child_one="кафедру",
    fields=[
        Field("название_факультета", "Название факультета"),
        Field("номер_отдела", "Отдел (институт)", kind="select",
              options_sql="SELECT номер_отдела AS id, название_отдела AS title FROM отдел ORDER BY 2"),
    ],
    list_sql="""SELECT f.код_факультета AS id, f.название_факультета AS название, o.название_отдела AS родитель,
                       (SELECT count(*) FROM кафедра k WHERE k.код_факультета = f.код_факультета) AS дочерних,
                       (SELECT count(*) FROM v_сотрудник v WHERE v.факультет_ид = f.код_факультета) AS сотрудников
                FROM факультет f JOIN отдел o ON o.номер_отдела = f.номер_отдела""",
    columns=[("id", "Код факультета"), ("название", "Название факультета"), ("родитель", "Отдел (институт)"),
             ("дочерних", "Кафедр"), ("сотрудников", "Сотрудников (всего)")],
))

_add(Entity(
    slug="kafedra", table="кафедра", pk="номер_кафедры", title="Кафедры", one="кафедру",
    group="structure", unit_type="кафедра", parent_param="код_факультета",
    child_slug="laboratoriya", child_one="лабораторию",
    fields=[
        Field("название_кафедры", "Название кафедры"),
        Field("код_факультета", "Факультет", kind="select",
              options_sql="SELECT код_факультета AS id, название_факультета AS title FROM факультет ORDER BY 2"),
    ],
    list_sql="""SELECT k.номер_кафедры AS id, k.название_кафедры AS название, f.название_факультета AS родитель,
                       (SELECT count(*) FROM лаборатория l WHERE l.номер_кафедры = k.номер_кафедры) AS дочерних,
                       (SELECT count(*) FROM v_сотрудник v WHERE v.кафедра_ид = k.номер_кафедры) AS сотрудников
                FROM кафедра k JOIN факультет f ON f.код_факультета = k.код_факультета""",
    columns=[("id", "№ кафедры"), ("название", "Название кафедры"), ("родитель", "Факультет"),
             ("дочерних", "Лабораторий"), ("сотрудников", "Сотрудников (всего)")],
))

_add(Entity(
    slug="laboratoriya", table="лаборатория", pk="номер_лаборатории", title="Лаборатории", one="лабораторию",
    group="structure", unit_type="лаборатория", parent_param="номер_кафедры",
    fields=[
        Field("название_лаборатории", "Название лаборатории"),
        Field("номер_кафедры", "Кафедра", kind="select",
              options_sql="SELECT номер_кафедры AS id, название_кафедры AS title FROM кафедра ORDER BY 2"),
    ],
    list_sql="""SELECT l.номер_лаборатории AS id, l.название_лаборатории AS название, k.название_кафедры AS родитель,
                       (SELECT count(*) FROM сотрудник s WHERE s.номер_лаборатории = l.номер_лаборатории) AS сотрудников
                FROM лаборатория l JOIN кафедра k ON k.номер_кафедры = l.номер_кафедры""",
    columns=[("id", "№ лаборатории"), ("название", "Название лаборатории"), ("родитель", "Кафедра"),
             ("сотрудников", "Сотрудников")],
))

_add(Entity(
    slug="dolzhnost", table="должность", pk="код_должности", title="Должности", one="должность", group="dict",
    fields=[
        Field("название_должности", "Название должности", maxlen=100),
        Field("преподавательская", "Относится к профессорско-преподавательскому составу", kind="checkbox",
              required=False, hint="Такие сотрудники попадают в «Сведения о лицах с учёными степенями и званиями»"),
    ],
    list_sql="""SELECT d.код_должности AS id, d.название_должности AS название,
                       CASE WHEN d.преподавательская THEN 'да' ELSE 'нет' END AS ппс,
                       (SELECT count(*) FROM сотрудник s WHERE s.код_должности = d.код_должности) AS сотрудников
                FROM должность d""",
    columns=[("id", "Код"), ("название", "Должность"), ("ппс", "Преподавательская"), ("сотрудников", "Сотрудников")],
))

_add(Entity(
    slug="stepen", table="ученая_степень", pk="код_степени", title="Учёные степени", one="учёную степень",
    group="dict",
    fields=[Field("название_степени", "Учёная степень", maxlen=100, hint="Например: «Кандидат технических наук»")],
    list_sql="""SELECT x.код_степени AS id, x.название_степени AS название,
                       (SELECT count(*) FROM сотрудник s WHERE s.код_степени = x.код_степени) AS сотрудников
                FROM ученая_степень x""",
    columns=[("id", "Код"), ("название", "Учёная степень"), ("сотрудников", "Сотрудников")],
))

_add(Entity(
    slug="zvanie", table="ученое_звание", pk="код_звания", title="Учёные звания", one="учёное звание",
    group="dict",
    fields=[Field("название_звания", "Учёное звание", maxlen=100, hint="Например: «Доцент», «Профессор»")],
    list_sql="""SELECT x.код_звания AS id, x.название_звания AS название,
                       (SELECT count(*) FROM сотрудник s WHERE s.код_звания = x.код_звания) AS сотрудников
                FROM ученое_звание x""",
    columns=[("id", "Код"), ("название", "Учёное звание"), ("сотрудников", "Сотрудников")],
))

_add(Entity(
    slug="tip-telefona", table="тип_телефона", pk="код_типа", title="Типы телефонов", one="тип телефона",
    group="dict",
    fields=[Field("название_типа", "Тип телефона", maxlen=50, hint="Например: «Рабочий», «Сотовый», «Домашний»")],
    list_sql="""SELECT x.код_типа AS id, x.название_типа AS название,
                       (SELECT count(*) FROM телефон t WHERE t.код_типа = x.код_типа) AS телефонов
                FROM тип_телефона x""",
    columns=[("id", "Код"), ("название", "Тип телефона"), ("телефонов", "Телефонов")],
))

# Соответствие типа подразделения и описания таблицы
UNIT_ENTITY = {e.unit_type: e for e in ENTITIES.values() if e.unit_type}
UNIT_TITLES = {"отдел": "Отдел", "факультет": "Факультет", "кафедра": "Кафедра", "лаборатория": "Лаборатория"}
