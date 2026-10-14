"""Web-приложение «Сотрудники высшего учебного заведения».

Запуск:  uvicorn app.main:app --reload   (из корня проекта)
"""
from datetime import date
from itertools import groupby
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg import sql

from . import db
from .config import APP_TITLE, UNIVERSITY
from .db import AppError
from .entities import ENTITIES, UNIT_ENTITY, UNIT_TITLES, Entity
from .validation import EMPLOYEE_LABELS, years_word, max_birth_year, min_birth_year, parse_int, validate_employee

BASE = Path(__file__).resolve().parent
app = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["years"] = years_word
templates.env.globals.update(APP_TITLE=APP_TITLE, UNIVERSITY=UNIVERSITY, ENTITIES=ENTITIES,
                             UNIT_TITLES=UNIT_TITLES, today=date.today)


def render(request: Request, name: str, status_code: int = 200, **ctx):
    ctx["request"] = request
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def redirect(url: str, ok: str | None = None, err: str | None = None):
    if ok or err:
        sep = "&" if "?" in url else "?"
        url += f"{sep}{'ok' if ok else 'err'}={quote(ok or err)}"
    return RedirectResponse(url, status_code=303)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return render(request, "error.html", status_code=503 if isinstance(exc, db.DBUnavailable) else 400,
                  message=exc.message)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return render(request, "error.html", status_code=404, message="Страница не найдена.")


# ---------------------------------------------------------------------
#  Вспомогательные выборки
# ---------------------------------------------------------------------
def all_units() -> list[dict]:
    return db.query("SELECT ключ, тип, уровень, название, путь FROM v_подразделение ORDER BY путь")


def unit_slug(unit_type: str) -> str:
    return UNIT_ENTITY[unit_type].slug


templates.env.globals["unit_slug"] = unit_slug


def get_entity(slug: str) -> Entity:
    ent = ENTITIES.get(slug)
    if not ent:
        raise AppError("Раздел не найден.")
    return ent


# ---------------------------------------------------------------------
#  Главная страница
# ---------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    stats = db.query("SELECT * FROM fn_статистика()")
    return render(request, "index.html", stats=stats)


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return render(request, "about.html")


# ---------------------------------------------------------------------
#  Подразделения и справочники: форма-таблица и форма редактирования
# ---------------------------------------------------------------------
@app.get("/ref/{slug}", response_class=HTMLResponse)
def ref_list(request: Request, slug: str, q: str = "", sort: str = "название", dir: str = "asc"):
    ent = get_entity(slug)
    keys = [c[0] for c in ent.columns]
    if sort not in keys:
        sort = "название"
    direction = sql.SQL("DESC") if dir == "desc" else sql.SQL("ASC")
    stmt = sql.SQL("SELECT * FROM ({src}) t WHERE (%(q)s = '' OR t.название ILIKE %(like)s"
                   "{parent_cond}) ORDER BY {col} {dir}, t.id").format(
        src=sql.SQL(ent.list_sql),
        parent_cond=sql.SQL(" OR t.родитель ILIKE %(like)s" if any(k == "родитель" for k in keys) else ""),
        col=sql.Identifier(sort), dir=direction)
    rows = db.query(stmt, {"q": q.strip(), "like": f"%{q.strip()}%"})
    return render(request, "ref_list.html", ent=ent, rows=rows, q=q, sort=sort, dir=dir)


def _ref_options(ent: Entity) -> dict[str, list[dict]]:
    return {f.name: db.query(f.options_sql) for f in ent.fields if f.kind == "select"}


@app.get("/ref/{slug}/new", response_class=HTMLResponse)
def ref_new(request: Request, slug: str, parent: int | None = None):
    ent = get_entity(slug)
    values = {}
    if parent and ent.parent_param:
        values[ent.parent_param] = parent
    return render(request, "ref_form.html", ent=ent, values=values, errors={}, item_id=None,
                  options=_ref_options(ent))


@app.get("/ref/{slug}/{item_id}/edit", response_class=HTMLResponse)
def ref_edit(request: Request, slug: str, item_id: int):
    ent = get_entity(slug)
    row = db.query_one(sql.SQL("SELECT * FROM {t} WHERE {pk} = %s").format(
        t=sql.Identifier(ent.table), pk=sql.Identifier(ent.pk)), (item_id,))
    if not row:
        return redirect(f"/ref/{slug}", err="Запись не найдена (возможно, удалена).")
    return render(request, "ref_form.html", ent=ent, values=row, errors={}, item_id=item_id,
                  options=_ref_options(ent))


@app.post("/ref/{slug}/save", response_class=HTMLResponse)
async def ref_save(request: Request, slug: str):
    ent = get_entity(slug)
    form = await request.form()
    item_id = parse_int(form.get("item_id")) if form.get("item_id") else None
    options = _ref_options(ent)
    values, errors = {}, {}
    for f in ent.fields:
        raw = form.get(f.name)
        if f.kind == "checkbox":
            values[f.name] = raw == "on"
            continue
        raw = (raw or "").strip()
        if f.kind == "select":
            ids = {o["id"] for o in options[f.name]}
            try:
                v = parse_int(raw)
            except ValueError:
                v = -1
            values[f.name] = v
            if v is None and f.required:
                errors[f.name] = f"Выберите значение в поле «{f.label}»"
            elif v is not None and v not in ids:
                errors[f.name] = "Выбранное значение отсутствует в списке"
        else:
            values[f.name] = raw
            if not raw and f.required:
                errors[f.name] = f"Поле «{f.label}» обязательно для заполнения"
            elif len(raw) > f.maxlen:
                errors[f.name] = f"Не более {f.maxlen} символов"
            elif raw and len(raw) < 2:
                errors[f.name] = "Слишком короткое значение"
    if not errors:
        cols = [f.name for f in ent.fields]
        try:
            if item_id is None:
                stmt = sql.SQL("INSERT INTO {t} ({c}) VALUES ({v})").format(
                    t=sql.Identifier(ent.table), c=sql.SQL(", ").join(map(sql.Identifier, cols)),
                    v=sql.SQL(", ").join(sql.Placeholder(c) for c in cols))
                db.execute(stmt, values)
                return redirect(f"/ref/{slug}", ok=f"Запись «{values[cols[0]]}» добавлена.")
            stmt = sql.SQL("UPDATE {t} SET {s} WHERE {pk} = %(__id)s").format(
                t=sql.Identifier(ent.table), pk=sql.Identifier(ent.pk),
                s=sql.SQL(", ").join(sql.SQL("{} = {}").format(sql.Identifier(c), sql.Placeholder(c)) for c in cols))
            db.execute(stmt, {**values, "__id": item_id})
            return redirect(f"/ref/{slug}", ok=f"Изменения в записи «{values[cols[0]]}» сохранены.")
        except AppError as e:
            if isinstance(e, db.DBUnavailable):
                raise
            errors[e.field if e.field in cols else "_form"] = e.message
    return render(request, "ref_form.html", status_code=422, ent=ent, values=values, errors=errors,
                  item_id=item_id, options=options)


@app.post("/ref/{slug}/{item_id}/delete")
def ref_delete(request: Request, slug: str, item_id: int):
    ent = get_entity(slug)
    back = request.headers.get("referer") or f"/ref/{slug}"
    back = back.split("?")[0]
    try:
        row = db.execute(sql.SQL("DELETE FROM {t} WHERE {pk} = %s RETURNING {name}").format(
            t=sql.Identifier(ent.table), pk=sql.Identifier(ent.pk),
            name=sql.Identifier(ent.fields[0].name)), (item_id,), op="delete")
    except AppError as e:
        if isinstance(e, db.DBUnavailable):
            raise
        return redirect(back, err=e.message)
    if not row:
        return redirect(back, err="Запись не найдена (возможно, уже удалена).")
    if ent.unit_type and f"/unit/{slug}/{item_id}" in back:
        back = "/structure"
    return redirect(back, ok=f"Запись «{row[ent.fields[0].name]}» удалена.")


# ---------------------------------------------------------------------
#  Структура вуза (дерево) и карточка подразделения (родитель — дочерние)
# ---------------------------------------------------------------------
@app.get("/structure", response_class=HTMLResponse)
def structure(request: Request):
    rows = db.query("""
        SELECT p.*,
               (SELECT count(*) FROM v_сотрудник v WHERE v.ключ_подразделения = p.ключ) AS своих,
               (SELECT count(*) FROM v_сотрудник v
                 WHERE fn_в_подразделении(p.ключ, v.отдел_ид, v.факультет_ид, v.кафедра_ид, v.лаборатория_ид)) AS всего
        FROM v_подразделение p ORDER BY p.путь""")
    return render(request, "structure.html", rows=rows)


@app.get("/unit/{slug}/{item_id}", response_class=HTMLResponse)
def unit_card(request: Request, slug: str, item_id: int, all: int = 0):
    ent = get_entity(slug)
    if not ent.unit_type:
        raise AppError("Раздел не найден.")
    key = f"{ent.unit_type}:{item_id}"
    unit = db.query_one("SELECT * FROM v_подразделение WHERE ключ = %s", (key,))
    if not unit:
        return redirect(f"/ref/{slug}", err="Подразделение не найдено (возможно, удалено).")
    # цепочка вышестоящих подразделений
    chain = []
    for t, col in (("отдел", "номер_отдела"), ("факультет", "код_факультета"),
                   ("кафедра", "номер_кафедры"), ("лаборатория", "номер_лаборатории")):
        if unit[col] is not None:
            p = db.query_one("SELECT ключ, тип, ид, название FROM v_подразделение WHERE ключ = %s",
                             (f"{t}:{unit[col]}",))
            chain.append(p)
    children = []
    if ent.child_slug:
        child = ENTITIES[ent.child_slug]
        children = db.query(
            """SELECT p.ид, p.название, p.ключ,
                      (SELECT count(*) FROM v_сотрудник v WHERE v.ключ_подразделения = p.ключ) AS сотрудников
               FROM v_подразделение p WHERE p.тип = %s AND p.уровень = %s
                 AND fn_в_подразделении(%s, p.номер_отдела, p.код_факультета, p.номер_кафедры, p.номер_лаборатории)
               ORDER BY p.название""", (child.unit_type, unit["уровень"] + 1, key))
    if all:
        emps = db.query("""SELECT * FROM v_сотрудник v
                           WHERE fn_в_подразделении(%s, v.отдел_ид, v.факультет_ид, v.кафедра_ид, v.лаборатория_ид)
                           ORDER BY v.путь_подразделения, v.фамилия, v.имя""", (key,))
    else:
        emps = db.query("SELECT * FROM v_сотрудник WHERE ключ_подразделения = %s ORDER BY фамилия, имя", (key,))
    return render(request, "unit.html", ent=ent, unit=unit, chain=chain, children=children,
                  child=ENTITIES.get(ent.child_slug) if ent.child_slug else None, emps=emps, show_all=all)


# ---------------------------------------------------------------------
#  Сотрудники
# ---------------------------------------------------------------------
EMP_SORT = {"фио": "v.фамилия, v.имя, v.отчество", "должность": "v.должность", "подразделение": "v.путь_подразделения",
            "стаж": "v.общий_стаж", "год": "v.год_рождения", "номер": "v.табельный_номер"}


@app.get("/employees", response_class=HTMLResponse)
def employees(request: Request, q: str = "", unit: str = "", post: str = "", degree: str = "",
              sort: str = "фио", dir: str = "asc"):
    if sort not in EMP_SORT:
        sort = "фио"
    cond = ["(%(q)s = '' OR v.фио ILIKE %(like)s OR v.телефоны ILIKE %(like)s)",
            "fn_в_подразделении(%(unit)s, v.отдел_ид, v.факультет_ид, v.кафедра_ид, v.лаборатория_ид)"]
    try:
        post_id = parse_int(post)
    except ValueError:
        post_id = None
    if post_id:
        cond.append("v.код_должности = %(post)s")
    if degree == "yes":
        cond.append("(v.код_степени IS NOT NULL OR v.код_звания IS NOT NULL)")
    elif degree == "no":
        cond.append("v.код_степени IS NULL AND v.код_звания IS NULL")
    order = ", ".join(f"{c} {'DESC' if dir == 'desc' else 'ASC'}" for c in EMP_SORT[sort].split(", "))
    stmt = f"SELECT * FROM v_сотрудник v WHERE {' AND '.join(cond)} ORDER BY {order}, v.табельный_номер"
    rows = db.query(stmt, {"q": q.strip(), "like": f"%{q.strip()}%", "unit": unit or None, "post": post_id})
    posts = db.query("SELECT код_должности AS id, название_должности AS title FROM должность ORDER BY 2")
    return render(request, "employees.html", rows=rows, units=all_units(), posts=posts,
                  f={"q": q, "unit": unit, "post": post, "degree": degree}, sort=sort, dir=dir)


def _emp_refs() -> dict:
    return {
        "posts": db.query("SELECT код_должности AS id, название_должности AS title, преподавательская FROM должность ORDER BY 2"),
        "degrees": db.query("SELECT код_степени AS id, название_степени AS title FROM ученая_степень ORDER BY 2"),
        "titles": db.query("SELECT код_звания AS id, название_звания AS title FROM ученое_звание ORDER BY 2"),
        "phone_types": db.query("SELECT код_типа AS id, название_типа AS title FROM тип_телефона ORDER BY 1"),
        "units": all_units(),
    }


def _emp_form(request, values, phones, errors, item_id, status_code=200):
    return render(request, "employee_form.html", status_code=status_code, values=values, phones=phones,
                  errors=errors, item_id=item_id, labels=EMPLOYEE_LABELS, refs=_emp_refs(),
                  min_year=min_birth_year(), max_year=max_birth_year())


@app.get("/employees/new", response_class=HTMLResponse)
def employee_new(request: Request, unit: str = ""):
    values = {"основное_место_работы": "ИРНИТУ", "общий_стаж": 0, "стаж_нпр": 0, "подразделение": unit}
    return _emp_form(request, values, [{"код_типа": 1, "номер": ""}], {}, None)


@app.get("/employees/{item_id}", response_class=HTMLResponse)
def employee_card(request: Request, item_id: int):
    emp = db.query_one("SELECT * FROM v_сотрудник WHERE табельный_номер = %s", (item_id,))
    if not emp:
        return redirect("/employees", err="Сотрудник не найден (возможно, удалён).")
    phones = db.query("""SELECT tt.название_типа AS тип, t.номер FROM телефон t
                         JOIN тип_телефона tt ON tt.код_типа = t.код_типа
                         WHERE t.табельный_номер = %s ORDER BY tt.код_типа, t.код_телефона""", (item_id,))
    return render(request, "employee_card.html", e=emp, phones=phones)


@app.get("/employees/{item_id}/edit", response_class=HTMLResponse)
def employee_edit(request: Request, item_id: int):
    emp = db.query_one("SELECT s.*, v.ключ_подразделения AS подразделение FROM сотрудник s "
                       "JOIN v_сотрудник v USING (табельный_номер) WHERE s.табельный_номер = %s", (item_id,))
    if not emp:
        return redirect("/employees", err="Сотрудник не найден (возможно, удалён).")
    phones = db.query("SELECT код_типа, номер FROM телефон WHERE табельный_номер = %s ORDER BY код_типа, код_телефона",
                      (item_id,))
    return _emp_form(request, emp, phones or [{"код_типа": 1, "номер": ""}], {}, item_id)


@app.post("/employees/save", response_class=HTMLResponse)
async def employee_save(request: Request):
    form = await request.form()
    item_id = parse_int(form.get("item_id")) if form.get("item_id") else None
    phones = list(zip(form.getlist("phone_type"), form.getlist("phone_number")))
    refs = _emp_refs()
    valid = {
        "код_должности": {r["id"] for r in refs["posts"]},
        "код_степени": {r["id"] for r in refs["degrees"]},
        "код_звания": {r["id"] for r in refs["titles"]},
        "типы": {r["id"] for r in refs["phone_types"]},
        "units": {u["ключ"] for u in refs["units"]},
    }
    data, errors = validate_employee(dict(form), phones, valid)
    if not errors:
        unit_type, unit_id = data["подразделение"].split(":")
        unit_cols = {"отдел": "номер_отдела", "факультет": "код_факультета",
                     "кафедра": "номер_кафедры", "лаборатория": "номер_лаборатории"}
        row = {k: v for k, v in data.items() if k not in ("подразделение", "телефоны")}
        for t, col in unit_cols.items():
            row[col] = int(unit_id) if t == unit_type else None
        cols = list(row)
        try:
            with db.transaction() as c:
                if item_id is None:
                    stmt = sql.SQL("INSERT INTO сотрудник ({c}) VALUES ({v}) RETURNING табельный_номер").format(
                        c=sql.SQL(", ").join(map(sql.Identifier, cols)),
                        v=sql.SQL(", ").join(sql.Placeholder(k) for k in cols))
                    item_id_new = c.execute(stmt, row).fetchone()["табельный_номер"]
                else:
                    stmt = sql.SQL("UPDATE сотрудник SET {s} WHERE табельный_номер = %(__id)s RETURNING табельный_номер").format(
                        s=sql.SQL(", ").join(sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder(k)) for k in cols))
                    r = c.execute(stmt, {**row, "__id": item_id}).fetchone()
                    if not r:
                        raise AppError("Сотрудник не найден (возможно, удалён другим пользователем).")
                    item_id_new = item_id
                    c.execute("DELETE FROM телефон WHERE табельный_номер = %s", (item_id,))
                for t, number in data["телефоны"]:
                    c.execute("INSERT INTO телефон (табельный_номер, код_типа, номер) VALUES (%s, %s, %s)",
                              (item_id_new, t, number))
            fio = f"{data['фамилия']} {data['имя']}"
            msg = "Сотрудник «%s» добавлен." if item_id is None else "Изменения в карточке «%s» сохранены."
            return redirect(f"/employees/{item_id_new}", ok=msg % fio)
        except AppError as e:
            if isinstance(e, db.DBUnavailable):
                raise
            errors[e.field if e.field in EMPLOYEE_LABELS else "_form"] = e.message
    values = {k: form.get(k) for k in EMPLOYEE_LABELS}
    phone_rows = [{"код_типа": parse_int(t) if (t or "").isdigit() else None, "номер": n} for t, n in phones] \
        or [{"код_типа": 1, "номер": ""}]
    return _emp_form(request, values, phone_rows, errors, item_id, status_code=422)


@app.post("/employees/{item_id}/delete")
def employee_delete(item_id: int):
    try:
        row = db.execute("DELETE FROM сотрудник WHERE табельный_номер = %s RETURNING фамилия, имя",
                         (item_id,), op="delete")
    except AppError as e:
        if isinstance(e, db.DBUnavailable):
            raise
        return redirect("/employees", err=e.message)
    if not row:
        return redirect("/employees", err="Сотрудник не найден (возможно, уже удалён).")
    return redirect("/employees", ok=f"Сотрудник «{row['фамилия']} {row['имя']}» удалён.")


@app.post("/employees/{item_id}/move")
async def employee_move(request: Request, item_id: int):
    form = await request.form()
    try:
        db.execute("CALL sp_перевести_сотрудника(%s, %s)", (item_id, form.get("unit") or ""))
    except AppError as e:
        if isinstance(e, db.DBUnavailable):
            raise
        return redirect(f"/employees/{item_id}", err=e.message)
    return redirect(f"/employees/{item_id}", ok="Сотрудник переведён в другое подразделение.")


templates.env.globals["all_units"] = all_units


# ---------------------------------------------------------------------
#  Выходные документы
# ---------------------------------------------------------------------
@app.get("/reports/phones", response_class=HTMLResponse)
def report_phones(request: Request, unit: str = "", hide_empty: int = 0):
    rows = db.query("SELECT * FROM fn_телефонный_справочник(%s)", (unit or None,))
    groups = []
    for (path, name, typ, lvl), items in groupby(rows, key=lambda r: (r["путь"], r["подразделение"], r["тип"], r["уровень"])):
        emps = [i for i in items if i["табельный_номер"] is not None]
        if hide_empty and not emps:
            continue
        for e in emps:
            e["телефоны_список"] = (e["телефоны"] or "").split("; ") if e["телефоны"] else []
        groups.append({"путь": path, "название": name, "тип": typ, "уровень": lvl, "сотрудники": emps})
    total = sum(len(g["сотрудники"]) for g in groups)
    return render(request, "report_phones.html", groups=groups, units=all_units(), unit=unit,
                  hide_empty=hide_empty, total=total)


@app.get("/reports/experience", response_class=HTMLResponse)
def report_experience(request: Request, max: str | None = None, unit: str = ""):
    error, groups, total, limit = None, [], 0, None
    if max is not None:
        try:
            limit = parse_int(max)
            if limit is None:
                error = "Введите предельный стаж работы (целое число лет)"
            elif not 0 <= limit <= 70:
                error = "Предельный стаж должен быть целым числом от 0 до 70 лет"
        except ValueError:
            error = "Предельный стаж должен быть целым числом от 0 до 70 лет"
        if not error:
            try:
                rows = db.query("SELECT * FROM fn_сотрудники_по_стажу(%s, %s)", (limit, unit or None))
            except AppError as e:
                if isinstance(e, db.DBUnavailable):
                    raise
                error, rows = e.message, []
            for dept, items in groupby(rows, key=lambda r: r["отдел"]):
                items = list(items)
                groups.append({"отдел": dept, "сотрудники": items})
                total += len(items)
    return render(request, "report_experience.html", groups=groups, total=total, units=all_units(),
                  unit=unit, max=max if max is not None else "", limit=limit, error=error,
                  searched=max is not None and not error)


@app.get("/reports/degrees", response_class=HTMLResponse)
def report_degrees(request: Request, unit: str = "", profile: str = "", prorector: str | None = None,
                   only: int = 0):
    rows = db.query("SELECT * FROM fn_сведения_нпр(%s, %s)", (unit or None, bool(only)))
    teachers_total = db.query_one("SELECT count(*) AS n FROM fn_сведения_нпр(%s, false)", (unit or None,))["n"]
    with_degree = db.query_one("SELECT count(*) AS n FROM fn_сведения_нпр(%s, true)", (unit or None,))["n"]
    if prorector is None:
        p = db.query_one("SELECT фио_кратко FROM v_сотрудник WHERE должность = 'Проректор по учебной работе' LIMIT 1")
        prorector = p["фио_кратко"] if p else ""
    unit_name = ""
    if unit:
        u = db.query_one("SELECT название FROM v_подразделение WHERE ключ = %s", (unit,))
        unit_name = u["название"] if u else ""
    return render(request, "report_degrees.html", rows=rows, units=all_units(), unit=unit, unit_name=unit_name,
                  profile=profile, prorector=prorector, only=only, teachers_total=teachers_total,
                  with_degree=with_degree)


# ---------------------------------------------------------------------
#  Сервис
# ---------------------------------------------------------------------
@app.get("/service/experience", response_class=HTMLResponse)
def service_experience(request: Request):
    return render(request, "service_experience.html", years="1", error=None)


@app.post("/service/experience", response_class=HTMLResponse)
async def service_experience_run(request: Request):
    form = await request.form()
    years = (form.get("years") or "").strip()
    error = None
    try:
        n = parse_int(years)
        if n is None or not 1 <= n <= 5:
            error = "Количество лет должно быть целым числом от 1 до 5"
    except ValueError:
        error = "Количество лет должно быть целым числом от 1 до 5"
    if not error:
        try:
            r = db.execute("CALL sp_начислить_стаж(%s, 0)", (n,))
            return redirect("/employees", ok=f"Стаж увеличен на {n} г. у {r['p_обновлено']} сотрудников.")
        except AppError as e:
            if isinstance(e, db.DBUnavailable):
                raise
            error = e.message
    return render(request, "service_experience.html", status_code=422, years=years, error=error)
