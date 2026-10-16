# -*- coding: utf-8 -*-
"""
تطبيق تسيير روضة أطفال - Python + PySide6 + SQLite
تشغيل:  py main.py
"""
import html
import shutil
import sqlite3
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QDate, QMarginsF, QUrl, Qt
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QImage, QPageLayout,
                           QPageSize, QPdfWriter, QPixmap, QTextDocument, QTextOption)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox,
                               QColorDialog, QComboBox, QDateEdit, QDialog, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

# ============================ الإعدادات الافتراضية (تُعدَّل من صفحة ⚙️ الإعدادات داخل البرنامج) ============================
DEFAULTS = {
    "kg_name": "روضة البراعم",
    "address": "العنوان: ........",
    "phone": "الهاتف: 05 50 00 00 00",
    "currency": "دج",
    "primary": "#5B6CFF",
    "sidebar": "#2B2F6B",
    "logo": "",
}
CFG = dict(DEFAULTS)

# ============================ المسارات ============================
APP_DIR = Path.home() / "AppData" / "Local" / "KindergartenApp"
if not (Path.home() / "AppData").exists():          # لغير ويندوز (للتجربة فقط)
    APP_DIR = Path.home() / ".kindergarten_app"
DB_PATH = APP_DIR / "kindergarten_py.db"
DOCS_DIR = Path.home() / "Documents" / "KindergartenApp"

# ============================ قاعدة البيانات ============================
SCHEMA = """
CREATE TABLE IF NOT EXISTS children(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_date TEXT,
    class_name TEXT DEFAULT '',
    parent_name TEXT DEFAULT '',
    parent_phone TEXT DEFAULT '',
    monthly_fee REAL DEFAULT 0,
    notes TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS staff(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    role TEXT DEFAULT '',
    phone TEXT DEFAULT '',
    salary REAL DEFAULT 0,
    hire_date TEXT,
    is_active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS attendance(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_type TEXT NOT NULL,          -- Child أو Staff
    person_id INTEGER NOT NULL,
    att_date TEXT NOT NULL,
    is_present INTEGER NOT NULL,
    note TEXT DEFAULT '',
    UNIQUE(person_type, person_id, att_date)
);
CREATE TABLE IF NOT EXISTS invoices(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT DEFAULT '',
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    month TEXT NOT NULL,                -- YYYY-MM
    description TEXT DEFAULT '',
    amount REAL NOT NULL,
    paid REAL NOT NULL DEFAULT 0,
    issue_date TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def db():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def query(sql, params=()):
    conn = db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def execute(sql, params=()):
    conn = db()
    try:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def load_settings():
    CFG.update(DEFAULTS)
    for r in query("SELECT key, value FROM settings"):
        if r["key"] in DEFAULTS and r["value"] is not None:
            CFG[r["key"]] = r["value"]


def save_settings(values):
    conn = db()
    try:
        conn.executemany("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", list(values.items()))
        conn.commit()
    finally:
        conn.close()


# ============================ دوال مساعدة ============================
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def parse_money(text):
    """يحوّل النص إلى رقم، ويعيد None إذا كان غير صالح. الحقل الفارغ = 0"""
    t = (text or "").strip().translate(AR_DIGITS).replace(",", ".").replace(" ", "")
    if not t:
        return 0.0
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def money(v):
    return f"{v:,.2f}"


def fmt_date(iso):
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def age_of(iso):
    try:
        b = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    t = date.today()
    return t.year - b.year - ((t.month, t.day) < (b.month, b.day))


def to_qdate(iso):
    d = QDate.fromString(iso or "", "yyyy-MM-dd")
    return d if d.isValid() else QDate.currentDate()


def info(parent, msg):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("تنبيه")
    box.setText(msg)
    box.addButton("حسناً", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def confirm(parent, msg):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("تأكيد")
    box.setText(msg)
    yes = box.addButton("نعم", QMessageBox.ButtonRole.YesRole)
    box.addButton("لا", QMessageBox.ButtonRole.NoRole)
    box.exec()
    return box.clickedButton() is yes


def title(text):
    lb = QLabel(text)
    lb.setObjectName("title")
    return lb


def button(text, kind, slot):
    b = QPushButton(text)
    b.setProperty("kind", kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(slot)
    return b


def make_table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(38)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return t


def populate(table, rows, ids):
    table.setRowCount(len(rows))
    for r, (vals, rid) in enumerate(zip(rows, ids)):
        for c, v in enumerate(vals):
            item = QTableWidgetItem(str(v))
            if c == 0:
                item.setData(Qt.ItemDataRole.UserRole, rid)
            table.setItem(r, c, item)


def selected_id(table):
    rows = table.selectionModel().selectedRows()
    if not rows:
        return None
    return table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)


def add_field(layout, label, widget):
    lb = QLabel(label)
    lb.setObjectName("muted")
    layout.addWidget(lb)
    layout.addWidget(widget)


def form_scroll(form):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.Shape.NoFrame)
    sc.setWidget(form)
    sc.setFixedWidth(380)
    sc.viewport().setAutoFillBackground(False)
    return sc


def make_date_edit(fmt="dd/MM/yyyy"):
    d = QDateEdit(QDate.currentDate())
    d.setCalendarPopup(True)
    d.setDisplayFormat(fmt)
    return d


class Page(QWidget):
    def refresh(self, *_):
        pass


# ============================ الصفحة الرئيسية ============================
class DashboardPage(Page):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.addWidget(title("🏠 لوحة التحكم"))
        self.date_label = QLabel()
        self.date_label.setObjectName("muted")
        root.addWidget(self.date_label)

        grid = QGridLayout()
        grid.setSpacing(14)
        self.nums = {}
        cards = [("children", "👶 الأطفال المسجلون"), ("staff", "👩‍🏫 المربون والعمال"),
                 ("present", "✅ أطفال حاضرون اليوم"), ("unpaid", "🧾 مستحقات غير مسددة")]
        for col, (key, text) in enumerate(cards):
            card = QFrame()
            card.setObjectName("card")
            v = QVBoxLayout(card)
            n = QLabel("0")
            n.setObjectName("bignum")
            lb = QLabel(text)
            lb.setObjectName("muted")
            v.addWidget(n)
            v.addWidget(lb)
            grid.addWidget(card, 0, col)
            self.nums[key] = n
        root.addLayout(grid)

        box = QFrame()
        box.setObjectName("card")
        bl = QVBoxLayout(box)
        h = QLabel("توزيع الأطفال حسب القسم")
        h.setStyleSheet("font-size:18px; font-weight:bold;")
        self.classes_label = QLabel()
        bl.addWidget(h)
        bl.addWidget(self.classes_label)
        root.addWidget(box)
        root.addStretch()

    def refresh(self, *_):
        today = date.today().isoformat()
        self.date_label.setText(QDate.currentDate().toString("dddd d MMMM yyyy"))
        self.nums["children"].setText(str(query("SELECT COUNT(*) c FROM children WHERE is_active=1")[0]["c"]))
        self.nums["staff"].setText(str(query("SELECT COUNT(*) c FROM staff WHERE is_active=1")[0]["c"]))
        self.nums["present"].setText(str(query(
            "SELECT COUNT(*) c FROM attendance WHERE person_type='Child' AND att_date=? AND is_present=1",
            (today,))[0]["c"]))
        unpaid = query("SELECT COALESCE(SUM(amount-paid),0) s FROM invoices")[0]["s"]
        self.nums["unpaid"].setText(f"{unpaid:,.0f} {CFG['currency']}")
        rows = query("""SELECT CASE WHEN TRIM(class_name)='' THEN 'بدون قسم' ELSE class_name END AS cls,
                               COUNT(*) AS n FROM children WHERE is_active=1 GROUP BY cls ORDER BY cls""")
        self.classes_label.setText("<br>".join(
            f"{html.escape(r['cls'])}: <b style='color:{CFG['primary']}'>{r['n']}</b>" for r in rows) or "لا يوجد أطفال بعد")


# ============================ صفحة الأطفال ============================
class ChildrenPage(Page):
    HEADERS = ["الاسم الكامل", "العمر", "القسم", "الولي", "الهاتف", "الاشتراك", "نشط"]

    def __init__(self):
        super().__init__()
        self.current_id = None
        self.by_id = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        left = QVBoxLayout()
        left.addWidget(title("👶 الأطفال"))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 بحث بالاسم أو اسم الولي...")
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QCheckBox("إظهار غير النشطين")
        self.show_inactive.stateChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.show_inactive)
        left.addLayout(bar)
        self.table = make_table(self.HEADERS)
        self.table.itemSelectionChanged.connect(self.on_select)
        left.addWidget(self.table, 1)
        root.addLayout(left, 1)

        form = QFrame()
        form.setObjectName("card")
        fl = QVBoxLayout(form)
        self.form_title = QLabel()
        self.form_title.setStyleSheet("font-size:18px; font-weight:bold;")
        fl.addWidget(self.form_title)
        self.f_first, self.f_last = QLineEdit(), QLineEdit()
        self.f_birth = make_date_edit()
        self.f_class = QComboBox()
        self.f_class.setEditable(True)
        self.f_class.addItems(["الحضانة", "الصغار", "المتوسطون", "الكبار (التحضيري)"])
        self.f_parent, self.f_phone, self.f_fee = QLineEdit(), QLineEdit(), QLineEdit()
        self.f_notes = QPlainTextEdit()
        self.f_notes.setFixedHeight(70)
        self.f_active = QCheckBox("نشط (يداوم حالياً)")
        add_field(fl, "الاسم", self.f_first)
        add_field(fl, "اللقب", self.f_last)
        add_field(fl, "تاريخ الميلاد", self.f_birth)
        add_field(fl, "القسم", self.f_class)
        add_field(fl, "اسم الولي", self.f_parent)
        add_field(fl, "هاتف الولي", self.f_phone)
        add_field(fl, "الاشتراك الشهري", self.f_fee)
        add_field(fl, "ملاحظات (حساسية، صحة...)", self.f_notes)
        fl.addWidget(self.f_active)
        btns = QHBoxLayout()
        btns.addWidget(button("💾 حفظ", "primary", self.save))
        btns.addWidget(button("➕ جديد", "secondary", self.new_form))
        btns.addWidget(button("🗑 حذف", "danger", self.delete))
        fl.addLayout(btns)
        fl.addStretch()
        root.addWidget(form_scroll(form))

        self.new_form()

    def refresh(self, *_):
        sql, params = "SELECT * FROM children WHERE 1=1", []
        if not self.show_inactive.isChecked():
            sql += " AND is_active=1"
        s = self.search.text().strip()
        if s:
            sql += " AND (first_name LIKE ? OR last_name LIKE ? OR parent_name LIKE ?)"
            params += [f"%{s}%"] * 3
        sql += " ORDER BY last_name, first_name"
        rows = query(sql, params)
        self.by_id = {r["id"]: r for r in rows}
        populate(self.table,
                 [[f"{r['first_name']} {r['last_name']}", age_of(r["birth_date"]), r["class_name"],
                   r["parent_name"], r["parent_phone"], money(r["monthly_fee"]),
                   "✔" if r["is_active"] else "✖"] for r in rows],
                 [r["id"] for r in rows])

    def on_select(self):
        cid = selected_id(self.table)
        if cid is None or cid not in self.by_id:
            return
        r = self.by_id[cid]
        self.current_id = cid
        self.form_title.setText(f"تعديل: {r['first_name']} {r['last_name']}")
        self.f_first.setText(r["first_name"])
        self.f_last.setText(r["last_name"])
        self.f_birth.setDate(to_qdate(r["birth_date"]))
        self.f_class.setCurrentText(r["class_name"] or "")
        self.f_parent.setText(r["parent_name"] or "")
        self.f_phone.setText(r["parent_phone"] or "")
        self.f_fee.setText(f"{r['monthly_fee']:g}")
        self.f_notes.setPlainText(r["notes"] or "")
        self.f_active.setChecked(bool(r["is_active"]))

    def new_form(self, *_):
        self.current_id = None
        self.form_title.setText("طفل جديد")
        for w in (self.f_first, self.f_last, self.f_parent, self.f_phone, self.f_fee):
            w.clear()
        self.f_notes.clear()
        self.f_class.setCurrentText("")
        self.f_birth.setDate(QDate.currentDate().addYears(-4))
        self.f_active.setChecked(True)
        self.table.clearSelection()

    def save(self, *_):
        first, last = self.f_first.text().strip(), self.f_last.text().strip()
        if not first or not last:
            info(self, "أدخل اسم الطفل ولقبه.")
            return
        fee = parse_money(self.f_fee.text())
        if fee is None:
            info(self, "الاشتراك الشهري يجب أن يكون رقماً.")
            return
        data = (first, last, self.f_birth.date().toString("yyyy-MM-dd"), self.f_class.currentText().strip(),
                self.f_parent.text().strip(), self.f_phone.text().strip(), fee,
                self.f_notes.toPlainText().strip(), 1 if self.f_active.isChecked() else 0)
        if self.current_id:
            execute("""UPDATE children SET first_name=?, last_name=?, birth_date=?, class_name=?,
                       parent_name=?, parent_phone=?, monthly_fee=?, notes=?, is_active=? WHERE id=?""",
                    data + (self.current_id,))
        else:
            execute("""INSERT INTO children(first_name,last_name,birth_date,class_name,parent_name,
                       parent_phone,monthly_fee,notes,is_active) VALUES(?,?,?,?,?,?,?,?,?)""", data)
        self.new_form()
        self.refresh()

    def delete(self, *_):
        if not self.current_id:
            info(self, "اختر طفلاً من القائمة أولاً.")
            return
        if not confirm(self, "سيتم حذف الطفل وفواتيره وسجل حضوره نهائياً. هل أنت متأكد؟"):
            return
        execute("DELETE FROM attendance WHERE person_type='Child' AND person_id=?", (self.current_id,))
        execute("DELETE FROM children WHERE id=?", (self.current_id,))
        self.new_form()
        self.refresh()


# ============================ صفحة المربين والعمال ============================
class StaffPage(Page):
    HEADERS = ["الاسم الكامل", "الوظيفة", "الهاتف", "الراتب", "تاريخ التوظيف", "نشط"]

    def __init__(self):
        super().__init__()
        self.current_id = None
        self.by_id = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        left = QVBoxLayout()
        left.addWidget(title("👩‍🏫 المربون والعمال"))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 بحث بالاسم أو الوظيفة...")
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QCheckBox("إظهار غير النشطين")
        self.show_inactive.stateChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.show_inactive)
        left.addLayout(bar)
        self.table = make_table(self.HEADERS)
        self.table.itemSelectionChanged.connect(self.on_select)
        left.addWidget(self.table, 1)
        root.addLayout(left, 1)

        form = QFrame()
        form.setObjectName("card")
        fl = QVBoxLayout(form)
        self.form_title = QLabel()
        self.form_title.setStyleSheet("font-size:18px; font-weight:bold;")
        fl.addWidget(self.form_title)
        self.f_name, self.f_phone, self.f_salary = QLineEdit(), QLineEdit(), QLineEdit()
        self.f_role = QComboBox()
        self.f_role.setEditable(True)
        self.f_role.addItems(["مربية", "مساعدة مربية", "مديرة", "سكرتيرة", "طباخة", "سائق", "عاملة نظافة", "حارس"])
        self.f_hire = make_date_edit()
        self.f_active = QCheckBox("نشط (يعمل حالياً)")
        add_field(fl, "الاسم الكامل", self.f_name)
        add_field(fl, "الوظيفة", self.f_role)
        add_field(fl, "الهاتف", self.f_phone)
        add_field(fl, "الراتب الشهري", self.f_salary)
        add_field(fl, "تاريخ التوظيف", self.f_hire)
        fl.addWidget(self.f_active)
        btns = QHBoxLayout()
        btns.addWidget(button("💾 حفظ", "primary", self.save))
        btns.addWidget(button("➕ جديد", "secondary", self.new_form))
        btns.addWidget(button("🗑 حذف", "danger", self.delete))
        fl.addLayout(btns)
        fl.addStretch()
        root.addWidget(form_scroll(form))

        self.new_form()

    def refresh(self, *_):
        sql, params = "SELECT * FROM staff WHERE 1=1", []
        if not self.show_inactive.isChecked():
            sql += " AND is_active=1"
        s = self.search.text().strip()
        if s:
            sql += " AND (full_name LIKE ? OR role LIKE ?)"
            params += [f"%{s}%"] * 2
        sql += " ORDER BY full_name"
        rows = query(sql, params)
        self.by_id = {r["id"]: r for r in rows}
        populate(self.table,
                 [[r["full_name"], r["role"], r["phone"], money(r["salary"]),
                   fmt_date(r["hire_date"]), "✔" if r["is_active"] else "✖"] for r in rows],
                 [r["id"] for r in rows])

    def on_select(self):
        sid = selected_id(self.table)
        if sid is None or sid not in self.by_id:
            return
        r = self.by_id[sid]
        self.current_id = sid
        self.form_title.setText(f"تعديل: {r['full_name']}")
        self.f_name.setText(r["full_name"])
        self.f_role.setCurrentText(r["role"] or "")
        self.f_phone.setText(r["phone"] or "")
        self.f_salary.setText(f"{r['salary']:g}")
        self.f_hire.setDate(to_qdate(r["hire_date"]))
        self.f_active.setChecked(bool(r["is_active"]))

    def new_form(self, *_):
        self.current_id = None
        self.form_title.setText("موظف جديد")
        for w in (self.f_name, self.f_phone, self.f_salary):
            w.clear()
        self.f_role.setCurrentText("")
        self.f_hire.setDate(QDate.currentDate())
        self.f_active.setChecked(True)
        self.table.clearSelection()

    def save(self, *_):
        name = self.f_name.text().strip()
        if not name:
            info(self, "أدخل الاسم الكامل.")
            return
        salary = parse_money(self.f_salary.text())
        if salary is None:
            info(self, "الراتب يجب أن يكون رقماً.")
            return
        data = (name, self.f_role.currentText().strip(), self.f_phone.text().strip(), salary,
                self.f_hire.date().toString("yyyy-MM-dd"), 1 if self.f_active.isChecked() else 0)
        if self.current_id:
            execute("""UPDATE staff SET full_name=?, role=?, phone=?, salary=?, hire_date=?, is_active=?
                       WHERE id=?""", data + (self.current_id,))
        else:
            execute("""INSERT INTO staff(full_name,role,phone,salary,hire_date,is_active)
                       VALUES(?,?,?,?,?,?)""", data)
        self.new_form()
        self.refresh()

    def delete(self, *_):
        if not self.current_id:
            info(self, "اختر موظفاً من القائمة أولاً.")
            return
        if not confirm(self, "سيتم حذف الموظف وسجل حضوره نهائياً. هل أنت متأكد؟"):
            return
        execute("DELETE FROM attendance WHERE person_type='Staff' AND person_id=?", (self.current_id,))
        execute("DELETE FROM staff WHERE id=?", (self.current_id,))
        self.new_form()
        self.refresh()


# ============================ صفحة الحضور والغياب ============================
class AttendancePage(Page):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addWidget(title("✅ الحضور والغياب"))

        bar = QHBoxLayout()
        bar.addWidget(QLabel("التاريخ:"))
        self.date_edit = make_date_edit()
        self.date_edit.setMinimumWidth(150)
        bar.addWidget(self.date_edit)
        bar.addWidget(QLabel("الفئة:"))
        self.type_box = QComboBox()
        self.type_box.addItems(["الأطفال", "المربون والعمال"])
        bar.addWidget(self.type_box)
        bar.addWidget(button("✔ الكل حاضر", "secondary", lambda: self.set_all(True)))
        bar.addWidget(button("✖ الكل غائب", "secondary", lambda: self.set_all(False)))
        bar.addStretch()
        root.addLayout(bar)

        self.table = make_table(["الاسم", "القسم / الوظيفة", "حاضر", "ملاحظة (تأخر، مرض...)"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.itemChanged.connect(self.update_summary)
        root.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(button("💾 حفظ الحضور", "success", self.save))
        self.summary = QLabel()
        self.summary.setStyleSheet("font-size:16px; font-weight:600;")
        bottom.addWidget(self.summary)
        bottom.addStretch()
        root.addLayout(bottom)

        self.date_edit.dateChanged.connect(self.refresh)
        self.type_box.currentIndexChanged.connect(self.refresh)

    def current_type(self):
        return "Child" if self.type_box.currentIndex() == 0 else "Staff"

    def refresh(self, *_):
        d = self.date_edit.date().toString("yyyy-MM-dd")
        typ = self.current_type()
        saved = {r["person_id"]: r for r in query(
            "SELECT * FROM attendance WHERE person_type=? AND att_date=?", (typ, d))}
        if typ == "Child":
            people = [(r["id"], f"{r['first_name']} {r['last_name']}", r["class_name"]) for r in query(
                "SELECT * FROM children WHERE is_active=1 ORDER BY last_name, first_name")]
        else:
            people = [(r["id"], r["full_name"], r["role"]) for r in query(
                "SELECT * FROM staff WHERE is_active=1 ORDER BY full_name")]

        t = self.table
        t.blockSignals(True)
        t.setRowCount(len(people))
        ro = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        for i, (pid, name, group) in enumerate(people):
            old = saved.get(pid)
            n = QTableWidgetItem(name)
            n.setData(Qt.ItemDataRole.UserRole, pid)
            n.setFlags(ro)
            g = QTableWidgetItem(group or "")
            g.setFlags(ro)
            p = QTableWidgetItem()
            p.setFlags(Qt.ItemFlag.ItemIsUserCheckable | ro)
            p.setCheckState(Qt.CheckState.Checked if old and old["is_present"] else Qt.CheckState.Unchecked)
            note = QTableWidgetItem(old["note"] if old else "")
            for col, it in enumerate((n, g, p, note)):
                t.setItem(i, col, it)
        t.blockSignals(False)
        self.update_summary()

    def update_summary(self, *_):
        total = self.table.rowCount()
        present = sum(1 for i in range(total)
                      if self.table.item(i, 2).checkState() == Qt.CheckState.Checked)
        self.summary.setText(f"   الحاضرون: {present} من {total}   |   الغائبون: {total - present}")

    def set_all(self, present):
        state = Qt.CheckState.Checked if present else Qt.CheckState.Unchecked
        self.table.blockSignals(True)
        for i in range(self.table.rowCount()):
            self.table.item(i, 2).setCheckState(state)
        self.table.blockSignals(False)
        self.update_summary()

    def save(self, *_):
        d = self.date_edit.date().toString("yyyy-MM-dd")
        typ = self.current_type()
        data = []
        for i in range(self.table.rowCount()):
            pid = self.table.item(i, 0).data(Qt.ItemDataRole.UserRole)
            present = 1 if self.table.item(i, 2).checkState() == Qt.CheckState.Checked else 0
            data.append((typ, pid, d, present, self.table.item(i, 3).text().strip()))
        conn = db()
        try:
            conn.execute("DELETE FROM attendance WHERE person_type=? AND att_date=?", (typ, d))
            conn.executemany("""INSERT INTO attendance(person_type,person_id,att_date,is_present,note)
                                VALUES(?,?,?,?,?)""", data)
            conn.commit()
        finally:
            conn.close()
        info(self, "تم حفظ الحضور بنجاح ✔")


# ============================ صفحة الفواتير ============================
def invoice_status(inv):
    remaining = round(inv["amount"] - inv["paid"], 2)
    if remaining <= 0:
        return "مسددة"
    return "مسددة جزئياً" if inv["paid"] > 0 else "غير مسددة"


def invoice_html(inv, has_logo=False):
    e = html.escape
    remaining = round(inv["amount"] - inv["paid"], 2)
    color = "#C0392B" if remaining > 0 else "#1E8449"
    month = f"{inv['month'][5:7]}/{inv['month'][:4]}"
    cur = CFG["currency"]
    primary = CFG["primary"]
    contact = " &nbsp;|&nbsp; ".join(e(x) for x in (CFG["address"], CFG["phone"]) if x)
    logo_cell = '<td width="90"><img src="logo" width="80"/></td>' if has_logo else ""
    return f"""
<div dir="rtl">
<table dir="rtl" width="100%" cellspacing="0" cellpadding="4"><tr>
  {logo_cell}
  <td><h1 style="color:{primary};">{e(CFG['kg_name'])}</h1>
      <p style="color:#777777;">{contact}</p></td>
</tr></table>
<hr/>
<h2>فاتورة رقم: {e(inv['number'])}</h2>
<p>التاريخ: {fmt_date(inv['issue_date'])}</p>
<p>الطفل: {e(inv['child_name'])}</p>
<p>الولي: {e(inv['parent_name'] or '')}</p>
<p>الفترة: {month}</p>
<br/>
<table dir="rtl" width="100%" cellspacing="0" cellpadding="6">
  <tr style="background-color:#EEEEEE;"><th align="right">البيان</th><th align="right">المبلغ</th></tr>
  <tr><td>{e(inv['description'] or '')}</td><td>{money(inv['amount'])} {cur}</td></tr>
</table>
<hr/>
<p><b>المجموع:</b> {money(inv['amount'])} {cur}</p>
<p><b>المدفوع:</b> {money(inv['paid'])} {cur}</p>
<p style="color:{color};"><b>المتبقي:</b> {money(remaining)} {cur}</p>
<br/>
<p align="center" style="color:#777777;">شكراً لثقتكم</p>
</div>
"""


def invoice_document(inv):
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Arial", 11))
    opt = QTextOption()
    opt.setTextDirection(Qt.LayoutDirection.RightToLeft)
    doc.setDefaultTextOption(opt)
    has_logo = False
    logo = CFG["logo"]
    if logo and Path(logo).exists():
        img = QImage(logo)
        if not img.isNull():
            img = img.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
            doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl("logo"), img)
            has_logo = True
    doc.setHtml(invoice_html(inv, has_logo))
    return doc


def print_doc(doc, device):
    fn = getattr(doc, "print_", None) or getattr(doc, "print")
    fn(device)


class InvoicesPage(Page):
    HEADERS = ["رقم الفاتورة", "الطفل", "الشهر", "المبلغ", "المدفوع", "المتبقي", "الحالة"]

    def __init__(self):
        super().__init__()
        self.fees = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addWidget(title("🧾 الفواتير والدفعات"))

        # إنشاء فاتورة
        card = QFrame()
        card.setObjectName("card")
        cl = QHBoxLayout(card)
        self.child_box = QComboBox()
        self.child_box.setMinimumWidth(220)
        self.child_box.currentIndexChanged.connect(self.on_child_changed)
        self.month_edit = make_date_edit("MM/yyyy")
        self.amount_edit = QLineEdit()
        self.desc_edit = QLineEdit()
        for label, w in (("الطفل", self.child_box), ("شهر الفاتورة", self.month_edit),
                         ("المبلغ", self.amount_edit), ("البيان (اختياري)", self.desc_edit)):
            col = QVBoxLayout()
            add_field(col, label, w)
            cl.addLayout(col)
        cl.addWidget(button("➕ إنشاء فاتورة", "primary", self.create), 0, Qt.AlignmentFlag.AlignBottom)
        root.addWidget(card)

        # أدوات
        bar = QHBoxLayout()
        self.unpaid_only = QCheckBox("غير المسددة فقط")
        self.unpaid_only.stateChanged.connect(self.load_invoices)
        bar.addWidget(self.unpaid_only)
        bar.addSpacing(20)
        bar.addWidget(QLabel("المبلغ المدفوع:"))
        self.pay_edit = QLineEdit()
        self.pay_edit.setFixedWidth(130)
        bar.addWidget(self.pay_edit)
        bar.addWidget(button("💰 تسجيل دفعة", "success", self.pay))
        bar.addWidget(button("🖨 طباعة", "primary", self.print_invoice))
        bar.addWidget(button("📄 حفظ PDF", "primary", self.save_pdf))
        bar.addWidget(button("🗑 حذف", "danger", self.delete))
        bar.addStretch()
        root.addLayout(bar)

        self.table = make_table(self.HEADERS)
        root.addWidget(self.table, 1)

    def refresh(self, *_):
        self.load_children()
        self.load_invoices()

    def load_children(self):
        current = self.child_box.currentData()
        rows = query("SELECT id, first_name, last_name, monthly_fee FROM children WHERE is_active=1 "
                     "ORDER BY last_name, first_name")
        self.fees = {r["id"]: r["monthly_fee"] for r in rows}
        self.child_box.blockSignals(True)
        self.child_box.clear()
        for r in rows:
            self.child_box.addItem(f"{r['first_name']} {r['last_name']}", r["id"])
        idx = self.child_box.findData(current)
        self.child_box.setCurrentIndex(idx if idx >= 0 else (0 if rows else -1))
        self.child_box.blockSignals(False)
        self.on_child_changed()

    def on_child_changed(self, *_):
        cid = self.child_box.currentData()
        if cid in self.fees:
            self.amount_edit.setText(f"{self.fees[cid]:g}")

    def load_invoices(self, *_):
        rows = query("""SELECT i.*, c.first_name || ' ' || c.last_name AS child_name
                        FROM invoices i JOIN children c ON c.id = i.child_id ORDER BY i.id DESC""")
        if self.unpaid_only.isChecked():
            rows = [r for r in rows if r["amount"] - r["paid"] > 0]
        populate(self.table,
                 [[r["number"], r["child_name"], f"{r['month'][5:7]}/{r['month'][:4]}",
                   money(r["amount"]), money(r["paid"]), money(r["amount"] - r["paid"]),
                   invoice_status(r)] for r in rows],
                 [r["id"] for r in rows])
        colors = {"غير مسددة": "#C0392B", "مسددة": "#1E8449", "مسددة جزئياً": "#D68910"}
        for i, r in enumerate(rows):
            brush = QBrush(QColor(colors[invoice_status(r)]))
            for c in range(self.table.columnCount()):
                self.table.item(i, c).setForeground(brush)

    def create(self, *_):
        cid = self.child_box.currentData()
        if cid is None:
            info(self, "اختر الطفل أولاً (أضف أطفالاً من صفحة الأطفال).")
            return
        amount = parse_money(self.amount_edit.text())
        if not amount or amount <= 0:
            info(self, "أدخل مبلغاً صحيحاً أكبر من الصفر.")
            return
        d = self.month_edit.date()
        month = f"{d.year():04d}-{d.month():02d}"
        if query("SELECT 1 FROM invoices WHERE child_id=? AND month=?", (cid, month)):
            if not confirm(self, "توجد فاتورة لهذا الطفل في نفس الشهر. هل تريد إنشاء فاتورة أخرى؟"):
                return
        desc = self.desc_edit.text().strip() or f"اشتراك شهر {d.month():02d}/{d.year()}"
        new_id = execute("""INSERT INTO invoices(number, child_id, month, description, amount, paid, issue_date)
                            VALUES('', ?, ?, ?, ?, 0, ?)""",
                         (cid, month, desc, amount, date.today().isoformat()))
        execute("UPDATE invoices SET number=? WHERE id=?", (f"F-{new_id:05d}", new_id))
        self.desc_edit.clear()
        self.load_invoices()

    def selected_invoice(self):
        iid = selected_id(self.table)
        if iid is None:
            info(self, "اختر فاتورة من القائمة أولاً.")
            return None
        return iid

    def full_invoice(self, iid):
        return query("""SELECT i.*, c.first_name || ' ' || c.last_name AS child_name, c.parent_name
                        FROM invoices i JOIN children c ON c.id = i.child_id WHERE i.id=?""", (iid,))[0]

    def pay(self, *_):
        iid = self.selected_invoice()
        if iid is None:
            return
        amount = parse_money(self.pay_edit.text())
        if not amount or amount <= 0:
            info(self, "أدخل المبلغ المدفوع (رقم أكبر من الصفر).")
            return
        inv = self.full_invoice(iid)
        remaining = round(inv["amount"] - inv["paid"], 2)
        if amount > remaining:
            info(self, f"المبلغ أكبر من المتبقي ({money(remaining)}).")
            return
        execute("UPDATE invoices SET paid = paid + ? WHERE id=?", (amount, iid))
        self.pay_edit.clear()
        self.load_invoices()

    def print_invoice(self, *_):
        iid = self.selected_invoice()
        if iid is None:
            return
        doc = invoice_document(self.full_invoice(iid))
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A5))
        if QPrintDialog(printer, self).exec() == QDialog.DialogCode.Accepted:
            print_doc(doc, printer)

    def save_pdf(self, *_):
        iid = self.selected_invoice()
        if iid is None:
            return
        inv = self.full_invoice(iid)
        folder = DOCS_DIR / "Invoices"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{inv['number']}.pdf"
        writer = QPdfWriter(str(path))
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A5))
        writer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Unit.Millimeter)
        print_doc(invoice_document(inv), writer)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def delete(self, *_):
        iid = self.selected_invoice()
        if iid is None:
            return
        inv = self.full_invoice(iid)
        if not confirm(self, f"حذف الفاتورة {inv['number']} نهائياً؟"):
            return
        execute("DELETE FROM invoices WHERE id=?", (iid,))
        self.load_invoices()


# ============================ صفحة الإعدادات والتخصيص ============================
class SettingsPage(Page):
    PRESETS = [("بنفسجي", "#5B6CFF", "#2B2F6B"), ("أخضر", "#2FA66A", "#1E4D3A"),
               ("برتقالي", "#F5793A", "#7A3E1D"), ("وردي", "#E85D9F", "#6B2447"),
               ("أزرق", "#1E9BD7", "#14456B"), ("أحمر", "#E5484D", "#6B1F24")]

    def __init__(self, on_apply):
        super().__init__()
        self.on_apply = on_apply
        self.pending_logo = None          # None = بدون تغيير ، "" = إزالة الشعار
        self.colors = {"primary": CFG["primary"], "sidebar": CFG["sidebar"]}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.addWidget(title("⚙️ الإعدادات والتخصيص"))

        cols = QHBoxLayout()
        cols.setSpacing(16)

        # ---- بيانات الروضة والشعار ----
        c1 = QFrame()
        c1.setObjectName("card")
        l1 = QVBoxLayout(c1)
        h1 = QLabel("بيانات الروضة والشعار")
        h1.setStyleSheet("font-size:18px; font-weight:bold;")
        l1.addWidget(h1)
        self.e_name, self.e_addr, self.e_phone, self.e_cur = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        add_field(l1, "اسم الروضة", self.e_name)
        add_field(l1, "العنوان", self.e_addr)
        add_field(l1, "الهاتف", self.e_phone)
        add_field(l1, "العملة (تظهر في الفواتير)", self.e_cur)
        l1.addSpacing(8)
        lb = QLabel("الشعار")
        lb.setObjectName("muted")
        l1.addWidget(lb)
        logo_row = QHBoxLayout()
        self.logo_preview = QLabel("بدون شعار")
        self.logo_preview.setFixedSize(120, 120)
        self.logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_preview.setStyleSheet("border:2px dashed #D5DAE8; border-radius:12px; color:#7A819C;")
        logo_btns = QVBoxLayout()
        logo_btns.addWidget(button("🖼 اختيار شعار...", "primary", self.pick_logo))
        logo_btns.addWidget(button("✖ إزالة الشعار", "secondary", self.remove_logo))
        logo_btns.addStretch()
        logo_row.addWidget(self.logo_preview)
        logo_row.addLayout(logo_btns)
        logo_row.addStretch()
        l1.addLayout(logo_row)
        hint = QLabel("الأفضل صورة PNG مربعة بخلفية شفافة (مثل 512×512).")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        l1.addWidget(hint)
        l1.addStretch()
        cols.addWidget(c1, 1)

        # ---- الألوان ----
        c2 = QFrame()
        c2.setObjectName("card")
        l2 = QVBoxLayout(c2)
        h2 = QLabel("الألوان")
        h2.setStyleSheet("font-size:18px; font-weight:bold;")
        l2.addWidget(h2)
        self.btn_primary, self.btn_sidebar = QPushButton(), QPushButton()
        for b in (self.btn_primary, self.btn_sidebar):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_primary.clicked.connect(lambda _=False: self.pick_color("primary"))
        self.btn_sidebar.clicked.connect(lambda _=False: self.pick_color("sidebar"))
        add_field(l2, "اللون الرئيسي (الأزرار والأرقام والعناوين)", self.btn_primary)
        add_field(l2, "لون القائمة الجانبية", self.btn_sidebar)
        l2.addSpacing(10)
        lp = QLabel("ألوان جاهزة")
        lp.setObjectName("muted")
        l2.addWidget(lp)
        grid = QGridLayout()
        for i, (name, p, s) in enumerate(self.PRESETS):
            b = QPushButton(name)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {s}, stop:1 {p});"
                            "color:white; border:none; border-radius:8px; padding:10px; font-weight:bold;")
            b.clicked.connect(lambda _=False, p=p, s=s: self.set_colors(p, s))
            grid.addWidget(b, i // 3, i % 3)
        l2.addLayout(grid)
        l2.addSpacing(6)
        l2.addWidget(button("↩ الألوان الافتراضية", "secondary",
                            lambda: self.set_colors(DEFAULTS["primary"], DEFAULTS["sidebar"])))
        l2.addStretch()
        cols.addWidget(c2, 1)
        root.addLayout(cols, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(button("💾 حفظ وتطبيق", "success", self.save))
        bottom.addStretch()
        root.addLayout(bottom)

        self.refresh()

    def refresh(self, *_):
        self.pending_logo = None
        self.e_name.setText(CFG["kg_name"])
        self.e_addr.setText(CFG["address"])
        self.e_phone.setText(CFG["phone"])
        self.e_cur.setText(CFG["currency"])
        self.colors = {"primary": CFG["primary"], "sidebar": CFG["sidebar"]}
        self.update_swatches()
        self.show_logo(CFG["logo"])

    def update_swatches(self):
        for key, btn in (("primary", self.btn_primary), ("sidebar", self.btn_sidebar)):
            col = self.colors[key]
            btn.setText(f"{col.upper()}   (اضغط للتغيير)")
            btn.setStyleSheet(f"background:{col}; color:{text_on(col)}; border:1px solid #D5DAE8; "
                              "border-radius:8px; padding:12px; font-weight:bold;")

    def set_colors(self, primary, sidebar):
        self.colors = {"primary": primary, "sidebar": sidebar}
        self.update_swatches()

    def pick_color(self, key):
        c = QColorDialog.getColor(QColor(self.colors[key]), self, "اختر اللون")
        if c.isValid():
            self.colors[key] = c.name()
            self.update_swatches()

    def show_logo(self, path):
        if path and Path(path).exists():
            pm = QPixmap(path)
            if not pm.isNull():
                self.logo_preview.setPixmap(pm.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.SmoothTransformation))
                return
        self.logo_preview.setText("بدون شعار")

    def pick_logo(self, *_):
        path, _f = QFileDialog.getOpenFileName(self, "اختيار الشعار", "",
                                               "صور (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not path:
            return
        if QPixmap(path).isNull():
            info(self, "تعذر قراءة هذه الصورة، اختر ملف صورة آخر.")
            return
        self.pending_logo = path
        self.show_logo(path)

    def remove_logo(self, *_):
        self.pending_logo = ""
        self.logo_preview.setText("بدون شعار")

    def save(self, *_):
        name = self.e_name.text().strip()
        if not name:
            info(self, "اسم الروضة مطلوب.")
            return
        logo = CFG["logo"]
        if self.pending_logo is not None:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            if self.pending_logo == "":
                logo = ""
                dest = None
            else:
                dest = APP_DIR / f"logo{Path(self.pending_logo).suffix.lower()}"
                if Path(self.pending_logo).resolve() != dest.resolve():
                    shutil.copy2(self.pending_logo, dest)
                logo = str(dest)
            for old in APP_DIR.glob("logo.*"):          # حذف الشعارات القديمة
                if dest is None or old.resolve() != dest.resolve():
                    try:
                        old.unlink()
                    except OSError:
                        pass
        values = {"kg_name": name, "address": self.e_addr.text().strip(),
                  "phone": self.e_phone.text().strip(),
                  "currency": self.e_cur.text().strip() or DEFAULTS["currency"],
                  "primary": self.colors["primary"], "sidebar": self.colors["sidebar"], "logo": logo}
        save_settings(values)
        CFG.update(values)
        self.pending_logo = None
        self.on_apply()
        info(self, "تم حفظ الإعدادات وتطبيقها ✔")


# ============================ النافذة الرئيسية ============================
def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix_white(h, ratio):
    return "#%02X%02X%02X" % tuple(int(v + (255 - v) * ratio) for v in _rgb(h))


def text_on(h):
    r, g, b = _rgb(h)
    return "#FFFFFF" if (0.299 * r + 0.587 * g + 0.114 * b) < 150 else "#2D3250"


STYLE_TEMPLATE = """
QWidget { color:#2D3250; font-size:14px; }
QMainWindow, #content { background:#F4F6FB; }
#sidebar { background:@SIDEBAR@; }
#sidebar QLabel { color:@ONSIDEBAR@; }
#sidebar QPushButton { color:@ONSIDEBAR@; background:transparent; border:none; text-align:right;
                       padding:12px 16px; border-radius:10px; font-size:16px; }
#sidebar QPushButton:hover { background:rgba(127,127,127,60); }
#sidebar QPushButton:checked { background:rgba(127,127,127,110); font-weight:bold; }
#title { font-size:28px; font-weight:bold; }
#muted { color:#7A819C; font-weight:600; }
#card { background:white; border-radius:14px; }
#bignum { font-size:32px; font-weight:bold; color:@PRIMARY@; }
QPushButton[kind="primary"], QPushButton[kind="secondary"],
QPushButton[kind="success"], QPushButton[kind="danger"] {
    color:white; border:none; border-radius:8px; padding:8px 16px; font-weight:600; }
QPushButton[kind="primary"] { background:@PRIMARY@; color:@ONPRIMARY@; }
QPushButton[kind="secondary"] { background:#7A819C; }
QPushButton[kind="success"] { background:#2FA66A; }
QPushButton[kind="danger"] { background:#E5484D; }
QLineEdit, QComboBox, QDateEdit, QPlainTextEdit {
    background:white; border:1px solid #D5DAE8; border-radius:8px; padding:6px 8px; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus { border:1px solid @PRIMARY@; }
QTableWidget { background:white; border:none; border-radius:14px;
               alternate-background-color:#F8F9FD; selection-background-color:@TINT2@;
               selection-color:#2D3250; }
QHeaderView::section { background:@TINT@; padding:8px; border:none; font-weight:bold; }
QScrollArea { border:none; background:transparent; }
"""


def build_style():
    return (STYLE_TEMPLATE
            .replace("@PRIMARY@", CFG["primary"])
            .replace("@ONPRIMARY@", text_on(CFG["primary"]))
            .replace("@SIDEBAR@", CFG["sidebar"])
            .replace("@ONSIDEBAR@", text_on(CFG["sidebar"]))
            .replace("@TINT@", mix_white(CFG["primary"], 0.88))
            .replace("@TINT2@", mix_white(CFG["primary"], 0.75)))




class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1320, 780)
        self.setMinimumSize(1050, 640)

        central = QWidget()
        central.setObjectName("content")
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(240)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 20, 12, 14)
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size:20px; font-weight:bold;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        sl.addWidget(self.logo_label)
        sl.addWidget(self.name_label)
        sl.addSpacing(16)

        self.stack = QStackedWidget()
        pages = [("🏠  الرئيسية", DashboardPage()), ("👶  الأطفال", ChildrenPage()),
                 ("👩‍🏫  المربون والعمال", StaffPage()), ("✅  الحضور والغياب", AttendancePage()),
                 ("🧾  الفواتير والدفعات", InvoicesPage()),
                 ("⚙️  الإعدادات والتخصيص", SettingsPage(self.apply_branding))]
        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, (text, page) in enumerate(pages):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            group.addButton(btn, i)
            sl.addWidget(btn)
            self.stack.addWidget(page)
        group.idClicked.connect(self.go)
        group.button(0).setChecked(True)
        sl.addStretch()
        backup = QPushButton("💾  نسخ احتياطي")
        backup.setCursor(Qt.CursorShape.PointingHandCursor)
        backup.clicked.connect(self.backup)
        sl.addWidget(backup)

        lay.addWidget(side)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.apply_branding(restyle=False)
        self.go(0)

    def apply_branding(self, restyle=True):
        """يطبّق الاسم والشعار والألوان الحالية على النافذة"""
        if restyle:
            QApplication.instance().setStyleSheet(build_style())
        self.setWindowTitle(f"{CFG['kg_name']} - تسيير الروضة")
        self.name_label.setText(CFG["kg_name"])
        pm = QPixmap(CFG["logo"]) if CFG["logo"] and Path(CFG["logo"]).exists() else QPixmap()
        if pm.isNull():
            self.logo_label.setText("🌈")
            self.logo_label.setStyleSheet("font-size:46px;")
        else:
            self.logo_label.setStyleSheet("")
            self.logo_label.setPixmap(pm.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))

    def go(self, index):
        self.stack.setCurrentIndex(index)
        self.stack.widget(index).refresh()

    def backup(self):
        default = f"backup-{datetime.now():%Y-%m-%d-%H%M}.db"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ نسخة احتياطية", default, "ملف قاعدة البيانات (*.db)")
        if path:
            shutil.copy2(DB_PATH, path)
            info(self, "تم حفظ النسخة الاحتياطية بنجاح ✔")

    def closeEvent(self, event):
        # نسخة احتياطية تلقائية يومية عند الإغلاق
        try:
            folder = DOCS_DIR / "Backups"
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(DB_PATH, folder / f"auto-{date.today().isoformat()}.db")
        except Exception:
            pass
        super().closeEvent(event)


def excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    print(text, file=sys.stderr)
    QMessageBox.critical(None, "خطأ غير متوقع", text[-1200:])


def main():
    sys.excepthook = excepthook
    init_db()
    load_settings()
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setFont(QFont("Segoe UI", 11))
    app.setStyleSheet(build_style())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
