// Сотрудники вуза — клиентская логика: меню, подтверждения, телефоны, контроль ввода
(function () {
  "use strict";

  // ---- Меню ----
  const toggle = document.querySelector(".menu-toggle");
  const menu = document.querySelector(".menu");
  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = menu.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open);
    });
  }
  document.querySelectorAll(".dropdown > button").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const dd = btn.parentElement;
      document.querySelectorAll(".dropdown.open").forEach((o) => o !== dd && o.classList.remove("open"));
      dd.classList.toggle("open");
    });
  });
  document.addEventListener("click", () => document.querySelectorAll(".dropdown.open").forEach((o) => o.classList.remove("open")));

  // ---- Закрытие сообщений и очистка адресной строки ----
  document.querySelectorAll(".flash-close").forEach((b) => b.addEventListener("click", () => b.parentElement.remove()));
  const url = new URL(window.location.href);
  if (url.searchParams.has("ok") || url.searchParams.has("err")) {
    url.searchParams.delete("ok"); url.searchParams.delete("err");
    window.history.replaceState(null, "", url.pathname + (url.search || ""));
  }

  // ---- Подтверждение действий (собственное окно вместо системного) ----
  const modal = document.getElementById("confirm-modal");
  const modalText = document.getElementById("confirm-text");
  const btnOk = document.getElementById("confirm-ok");
  const btnCancel = document.getElementById("confirm-cancel");
  let pendingForm = null;
  function closeModal() { modal.hidden = true; pendingForm = null; }
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (form.dataset.confirmed === "1") return;
      if (form.hasAttribute("data-validate") && !validateForm(form)) { e.preventDefault(); return; }
      e.preventDefault();
      pendingForm = form;
      modalText.textContent = form.dataset.confirm;
      btnOk.textContent = form.dataset.confirmOk || "Удалить";
      btnOk.title = "Подтвердить действие";
      modal.hidden = false;
      btnCancel.focus();
    });
  });
  if (modal) {
    btnCancel.addEventListener("click", closeModal);
    modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !modal.hidden) closeModal(); });
    btnOk.addEventListener("click", () => {
      if (!pendingForm) return;
      pendingForm.dataset.confirmed = "1";
      pendingForm.submit();
    });
  }

  // ---- Телефоны в личной карточке ----
  const phones = document.getElementById("phones");
  const addPhone = document.getElementById("add-phone");
  function bindRemove(row) {
    row.querySelector("[data-remove-phone]").addEventListener("click", () => {
      if (phones.querySelectorAll(".phone-row").length > 1) row.remove();
      else { row.querySelector("input").value = ""; }
    });
  }
  if (phones && addPhone) {
    phones.querySelectorAll(".phone-row").forEach(bindRemove);
    addPhone.addEventListener("click", () => {
      const rows = phones.querySelectorAll(".phone-row");
      const clone = rows[rows.length - 1].cloneNode(true);
      clone.querySelector("input").value = "";
      const sel = clone.querySelector("select");
      if (sel.selectedIndex < sel.options.length - 1) sel.selectedIndex += 1;
      phones.appendChild(clone);
      bindRemove(clone);
      clone.querySelector("input").focus();
    });
  }

  // ---- Контроль ввода на стороне клиента ----
  const NAME_RE = /^[А-ЯЁа-яёA-Za-z]+([- ][А-ЯЁа-яёA-Za-z]+)*$/;
  const PHONE_RE = /^\+?[0-9][0-9() -]*[0-9]$/;

  function yearsWord(n) {
    const a = Math.abs(n) % 100, b = a % 10;
    if (b === 1 && a !== 11) return n + " год";
    if (b >= 2 && b <= 4 && (a < 12 || a > 14)) return n + " года";
    return n + " лет";
  }

  function setError(el, msg) {
    const field = el.closest(".field") || el.parentElement;
    let box = field.querySelector(".field-error.client");
    if (!msg) { if (box) box.remove(); field.classList.remove("has-error"); return; }
    if (!box) { box = document.createElement("div"); box.className = "field-error client"; box.setAttribute("role", "alert"); field.appendChild(box); }
    box.textContent = msg;
    field.classList.add("has-error");
  }

  function checkEl(el) {
    const label = el.dataset.label || el.title || "Поле";
    const v = (el.value || "").trim();
    if (el.required && !v) return el.tagName === "SELECT" ? `Выберите значение в поле «${label}»` : `Поле «${label}» обязательно для заполнения`;
    if (!v) return "";
    if (el.type === "number") {
      if (!/^-?\d+$/.test(v)) return `Поле «${label}»: введите целое число`;
      const n = parseInt(v, 10);
      if (el.name === "год_рождения" && ((el.min !== "" && n < +el.min) || (el.max !== "" && n > +el.max)))
        return `Неверно введен год рождения! Допустимый диапазон: ${el.min}–${el.max}`;
      if (el.min !== "" && n < +el.min) return `Поле «${label}»: значение не меньше ${el.min}`;
      if (el.max !== "" && n > +el.max) return `Поле «${label}»: значение не больше ${el.max}`;
    }
    if (el.minLength > 0 && v.length < el.minLength) return `Поле «${label}»: слишком короткое значение`;
    if (["фамилия", "имя", "отчество"].includes(el.name) && !NAME_RE.test(v)) return "Допускаются только буквы, дефис и пробел";
    return "";
  }

  function validateForm(form) {
    let firstBad = null;
    form.querySelectorAll("input[data-label], select[data-label]").forEach((el) => {
      const msg = checkEl(el);
      setError(el, msg);
      if (msg && !firstBad) firstBad = el;
    });
    // Связанные проверки карточки сотрудника
    const year = form.querySelector("[name=год_рождения]");
    const total = form.querySelector("[name=общий_стаж]");
    const npr = form.querySelector("[name=стаж_нпр]");
    if (year && total && !checkEl(year) && !checkEl(total) && year.value && total.value) {
      const age = new Date().getFullYear() - parseInt(year.value, 10);
      if (parseInt(total.value, 10) > age - 14) {
        setError(total, `Общий стаж не может превышать возраст минус 14 лет: не более ${yearsWord(Math.max(age - 14, 0))} (возраст сотрудника ${yearsWord(age)})`);
        firstBad = firstBad || total;
      }
    }
    if (total && npr && !checkEl(total) && !checkEl(npr) && parseInt(npr.value || "0", 10) > parseInt(total.value || "0", 10)) {
      setError(npr, "Стаж научно-педагогической работы не может превышать общий стаж");
      firstBad = firstBad || npr;
    }
    if (phones) {
      const errs = [];
      phones.querySelectorAll("input[name=phone_number]").forEach((inp) => {
        const v = inp.value.trim();
        const digits = v.replace(/\D/g, "").length;
        const bad = v && (!PHONE_RE.test(v) || digits < 5 || digits > 15);
        inp.classList.toggle("bad", !!bad);
        inp.style.borderColor = bad ? "var(--err)" : "";
        if (bad) errs.push(`Неверный формат телефона «${v}»`);
      });
      setError(addPhone, errs.join("; "));
      if (errs.length && !firstBad) firstBad = phones.querySelector("input.bad");
    }
    if (firstBad) { firstBad.focus(); return false; }
    return true;
  }

  document.querySelectorAll("form[data-validate]:not([data-confirm])").forEach((form) => {
    form.addEventListener("submit", (e) => { if (!validateForm(form)) e.preventDefault(); });
  });
  document.querySelectorAll("form[data-validate] input[data-label], form[data-validate] select[data-label]").forEach((el) => {
    el.addEventListener("blur", () => setError(el, checkEl(el)));
  });
})();
