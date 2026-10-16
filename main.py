# -*- coding: utf-8 -*-
"""
تطبيق تسيير روضة أطفال - النسخة الاحترافية (3D + حماية بكلمة سر + تحكم كامل بالواجهة)
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
                               QTableWidgetItem, QVBoxLayout, QWidget, QGraphicsDropShadowEffect)

DEFAULTS = {
    "kg_name": "روضة البراعم الذكية",
    "address": "العنوان: الجزائر العاصمة",
    "phone": "الهاتف: 05 50 00 00 00",
    "currency": "دج",
    "primary": "#4F46E5",
    "sidebar": "#1E1B4B",
    "theme_mode": "Light",
    "app_password": "123",
    "logo": "",
}
CFG = dict(DEFAULTS)

APP_DIR = Path.home() / "AppData" / "Local" / "KindergartenAppPro"
if not (Path.home() / "AppData").exists():
    APP_DIR = Path.home() / ".kindergarten_app_pro"
DB_PATH = APP_DIR / "kindergarten_pro.db"
DOCS_DIR = Path.home() / "Documents" / "KindergartenAppPro"

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
    person_type TEXT NOT NULL,
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
    month TEXT NOT NULL,
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

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")

def parse_money(text):
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

def add_shadow(widget, blur=18, y_offset=4, alpha=30):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setXOffset(0)
    shadow.setYOffset(y_offset)
    shadow.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(shadow)

def make_table(headers):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(42)
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
    lb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(lb)
    if isinstance(widget, QLineEdit):
        widget.setAlignment(Qt.AlignmentFlag.AlignRight)
    layout.addWidget(widget)

def form_scroll(form):
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.Shape.NoFrame)
    sc.setWidget(form)
    sc.setFixedWidth(390)
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

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("تسجيل الدخول - نظام رياض الأطفال الاحترافي")
        self.setFixedSize(400, 260)
        self.setWindowFlags(Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.MSWindowsFixedSizeDialogHint)
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setSpacing(16)
        
        lbl_title = QLabel("🔐 بوابـة الدخـول الآمـنة")
        lbl_title.setStyleSheet("font-size:20px; font-weight:bold; color:#4F46E5;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_title)
        
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("أدخل كلمة سر التطبيق...")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pass_input.setStyleSheet("padding: 10px; border: 2px solid #CBD5E1; border-radius: 10px; font-size:15px;")
        self.pass_input.returnPressed.connect(self.check_password)
        lay.addWidget(self.pass_input)
        
        btn_login = QPushButton("دخول للنظام")
        btn_login.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_login.setStyleSheet("background:#4F46E5; color:white; font-weight:bold; padding:10px; border-radius:10px; font-size:15px;")
        btn_login.clicked.connect(self.check_password)
        lay.addWidget(btn_login)
        
        hint = QLabel("كلمة السر الافتراضية الأولى هي: 123")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)
        
        self.authenticated = False

    def check_password(self):
        saved_pass = CFG.get("app_password", "123")
        if self.pass_input.text() == saved_pass:
            self.authenticated = True
            self.accept()
        else:
            QMessageBox.warning(self, "خطأ", "كلمة السر غير صحيحة! حاول مرة أخرى.")
            self.pass_input.clear()

class DashboardPage(Page):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.addWidget(title("🏠 لوحة التحكم الرئيسية"))
        self.date_label = QLabel()
        self.date_label.setObjectName("muted")
        root.addWidget(self.date_label)
        root.addSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(20)
        self.nums = {}
        cards = [("children", "👶 الأطفال المسجلون النشطون"), ("staff", "👩‍🏫 المربون والعمال"),
                 ("present", "✅ أطفال حاضرون اليوم"), ("unpaid", "🧾 مستحقات مالية غير مسددة")]
        for col, (key, text) in enumerate(cards):
            card = QFrame()
            card.setObjectName("card3d")
            add_shadow(card, blur=22, y_offset=6, alpha=25)
            v = QVBoxLayout(card)
            v.setContentsMargins(20, 20, 20, 20)
            n = QLabel("0")
            n.setObjectName("bignum")
            lb = QLabel(text)
            lb.setObjectName("muted")
            v.addWidget(n)
            v.addWidget(lb)
            grid.addWidget(card, 0, col)
            self.nums[key] = n
        root.addLayout(grid)
        root.addSpacing(10)

        box = QFrame()
        box.setObjectName("card3d")
        add_shadow(box, blur=22, y_offset=6, alpha=25)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(24, 24, 24, 24)
        h = QLabel("📊 توزيع الأطفال حسب الأقسام التربوية")
        h.setStyleSheet("font-size:18px; font-weight:bold;")
        self.classes_label = QLabel()
        self.classes_label.setStyleSheet("font-size:15px; line-height: 1.6;")
        bl.addWidget(h)
        bl.addSpacing(8)
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
            f"🔹 {html.escape(r['cls'])}: <b style='color:{CFG['primary']}'>{r['n']} طفل</b>" for r in rows) or "لا يوجد أطفال مسجلون بعد")

class ChildrenPage(Page):
    HEADERS = ["الاسم الكامل", "العمر", "القسم", "الولي", "الهاتف", "الاشتراك", "نشط"]

    def __init__(self):
        super().__init__()
        self.current_id = None
        self.by_id = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)

        left = QVBoxLayout()
        left.addWidget(title("👶 إدارة تسطير وتواجد الأطفال"))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 بحث سريع بالاسم أو اسم الولي...")
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QCheckBox("إظهار غير النشطين")
        self.show_inactive.stateChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.show_inactive)
        left.addLayout(bar)
        
        table_container = QFrame()
        table_container.setObjectName("card3d")
        add_shadow(table_container, blur=18, y_offset=4, alpha=20)
        tl = QVBoxLayout(table_container)
        tl.setContentsMargins(12, 12, 12, 12)
        self.table = make_table(self.HEADERS)
        self.table.itemSelectionChanged.connect(self.on_select)
        tl.addWidget(self.table)
        left.addWidget(table_container, 1)
        root.addLayout(left, 1)

        form = QFrame()
        form.setObjectName("card3d")
        add_shadow(form, blur=22, y_offset=6, alpha=25)
        fl = QVBoxLayout(form)
        fl.setContentsMargins(20, 20, 20, 20)
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
        self.form_title.setText("تسجيل طفل جديد")
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
            info(self, "الاشتراك الشهري يجب أن يكون رقماً صحيحاً.")
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

class StaffPage(Page):
    HEADERS = ["الاسم الكامل", "الوظيفة", "الهاتف", "الراتب", "تاريخ التوظيف", "نشط"]

    def __init__(self):
        super().__init__()
        self.current_id = None
        self.by_id = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(20)

        left = QVBoxLayout()
        left.addWidget(title("👩‍🏫 المربون وطاقم العمال"))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 بحث بالاسم أو الوظيفة...")
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QCheckBox("إظهار غير النشطين")
        self.show_inactive.stateChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        bar.addWidget(self.show_inactive)
        left.addLayout(bar)
        
        tc = QFrame()
        tc.setObjectName("card3d")
        add_shadow(tc, blur=18, y_offset=4, alpha=20)
        tcl = QVBoxLayout(tc)
        tcl.setContentsMargins(12, 12, 12, 12)
        self.table = make_table(self.HEADERS)
        self.table.itemSelectionChanged.connect(self.on_select)
        tcl.addWidget(self.table)
        left.addWidget(tc, 1)
        root.addLayout(left, 1)

        form = QFrame()
        form.setObjectName("card3d")
        add_shadow(form, blur=22, y_offset=6, alpha=25)
        fl = QVBoxLayout(form)
        fl.setContentsMargins(20, 20, 20, 20)
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

class AttendancePage(Page):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(title("✅ متابعة الحضور والغياب اليومي"))

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

        tc = QFrame()
        tc.setObjectName("card3d")
        add_shadow(tc, blur=18, y_offset=4, alpha=20)
        tcl = QVBoxLayout(tc)
        tcl.setContentsMargins(12, 12, 12, 12)
        self.table = make_table(["الاسم", "القسم / الوظيفة", "حاضر", "ملاحظة (تأخر، مرض...)"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.itemChanged.connect(self.update_summary)
        tcl.addWidget(self.table)
        root.addWidget(tc, 1)

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
        info(self, "تم حفظ سجل الحضور بنجاح ✔")

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
<h2>فاتورة رسمية رقم: {e(inv['number'])}</h2>
<p>التاريخ: {fmt_date(inv['issue_date'])}</p>
<p>الطفل: {e(inv['child_name'])}</p>
<p>الولي: {e(inv['parent_name'] or '')}</p>
<p>الفترة الشهرية: {month}</p>
<br/>
<table dir="rtl" width="100%" cellspacing="0" cellpadding="6">
  <tr style="background-color:#EEEEEE;"><th align="right">البيان</th><th align="right">المبلغ</th></tr>
  <tr><td>{e(inv['description'] or '')}</td><td>{money(inv['amount'])} {cur}</td></tr>
</table>
<hr/>
<p><b>المجموع المطلوب:</b> {money(inv['amount'])} {cur}</p>
<p><b>المبلغ المدفوع:</b> {money(inv['paid'])} {cur}</p>
<p style="color:{color};"><b>المبلغ المتبقي:</b> {money(remaining)} {cur}</p>
<br/>
<p align="center" style="color:#777777;">نشكركم على ثقتكم الغالية</p>
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
        root.setSpacing(16)
        root.addWidget(title("🧾 الفواتير والاشتراكات المالية"))

        card = QFrame()
        card.setObjectName("card3d")
        add_shadow(card, blur=22, y_offset=6, alpha=25)
        cl = QHBoxLayout(card)
        cl.setContentsMargins(18, 18, 18, 18)
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

        tc = QFrame()
        tc.setObjectName("card3d")
        add_shadow(tc, blur=18, y_offset=4, alpha=20)
        tcl = QVBoxLayout(tc)
        tcl.setContentsMargins(12, 12, 12, 12)
        self.table = make_table(self.HEADERS)
        tcl.addWidget(self.table)
        root.addWidget(tc, 1)

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
            info(self, "اختر الطفل أولاً.")
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
            info(self, "أدخل المبلغ المدفوع بشكل صحيح.")
            return
        inv = self.full_invoice(iid)
        remaining = round(inv["amount"] - inv["paid"], 2)
        if amount > remaining:
            info(self, f"المبلغ المدفوع أكبر من المتبقي ({money(remaining)}).")
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

class SettingsPage(Page):
    PRESETS = [("نيلي عصري (3D)", "#4F46E5", "#1E1B4B"), ("أخضر زمردي", "#059669", "#064E3B"),
               ("برتقالي حماسي", "#EA580C", "#7C2D12"), ("وردي ملكي", "#DB2777", "#831843"),
               ("أزرق سماوي", "#0284C7", "#0C4A6E"), ("أحمر داكن", "#DC2626", "#7F1D1D")]

    def __init__(self, on_apply):
        super().__init__()
        self.on_apply = on_apply
        self.pending_logo = None
        self.colors = {"primary": CFG["primary"], "sidebar": CFG["sidebar"]}

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(title("⚙️ الإعدادات، الحماية، وتخصيص الواجهة بالكامل"))

        cols = QHBoxLayout()
        cols.setSpacing(20)

        c1 = QFrame()
        c1.setObjectName("card3d")
        add_shadow(c1, blur=22, y_offset=6, alpha=25)
        l1 = QVBoxLayout(c1)
        l1.setContentsMargins(20, 20, 20, 20)
        h1 = QLabel("بيانات الروضة، الحماية، والشعار")
        h1.setStyleSheet("font-size:18px; font-weight:bold;")
        l1.addWidget(h1)
        
        self.e_name, self.e_addr, self.e_phone, self.e_cur, self.e_pass = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Password)
        
        add_field(l1, "اسم الروضة", self.e_name)
        add_field(l1, "العنوان", self.e_addr)
        add_field(l1, "الهاتف", self.e_phone)
        add_field(l1, "العملة (تظهر في الفواتير)", self.e_cur)
        add_field(l1, "كلمة سر دخول التطبيق الجديدة", self.e_pass)
        l1.addSpacing(8)
        
        lb = QLabel("الشعار")
        lb.setObjectName("muted")
        l1.addWidget(lb)
        logo_row = QHBoxLayout()
        self.logo_preview = QLabel("بدون شعار")
        self.logo_preview.setFixedSize(100, 100)
        self.logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_preview.setStyleSheet("border:2px dashed #CBD5E1; border-radius:12px; color:#64748B; background:#F8FAFC;")
        logo_btns = QVBoxLayout()
        logo_btns.addWidget(button("🖼 اختيار شعار...", "primary", self.pick_logo))
        logo_btns.addWidget(button("✖ إزالة الشعار", "secondary", self.remove_logo))
        logo_btns.addStretch()
        logo_row.addWidget(self.logo_preview)
        logo_row.addLayout(logo_btns)
        logo_row.addStretch()
        l1.addLayout(logo_row)
        l1.addStretch()
        cols.addWidget(c1, 1)

        c2 = QFrame()
        c2.setObjectName("card3d")
        add_shadow(c2, blur=22, y_offset=6, alpha=25)
        l2 = QVBoxLayout(c2)
        l2.setContentsMargins(20, 20, 20, 20)
        h2 = QLabel("التحكم الكامل بالواجهة والألوان (3D Theme)")
        h2.setStyleSheet("font-size:18px; font-weight:bold;")
        l2.addWidget(h2)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["نهاري (Light)", "ليلي مظلم (Dark)"])
        add_field(l2, "وضع العرض (ليلي / نهاري)", self.theme_combo)
        
        self.btn_primary, self.btn_sidebar = QPushButton(), QPushButton()
        for b in (self.btn_primary, self.btn_sidebar):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_primary.clicked.connect(lambda _=False: self.pick_color("primary"))
        self.btn_sidebar.clicked.connect(lambda _=False: self.pick_color("sidebar"))
        
        add_field(l2, "اللون الرئيسي البارز", self.btn_primary)
        add_field(l2, "لون الشريط الجانبي الفاخر", self.btn_sidebar)
        l2.addSpacing(10)
        
        lp = QLabel("قوالب ألوان جاهزة بلمسة ثلاثية الأبعاد")
        lp.setObjectName("muted")
        l2.addWidget(lp)
        
        grid = QGridLayout()
        for i, (name, p, s) in enumerate(self.PRESETS):
            b = QPushButton(name)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {s}, stop:1 {p});"
                            "color:white; border:none; border-radius:10px; padding:10px; font-weight:bold;")
            b.clicked.connect(lambda _=False, p=p, s=s: self.set_colors(p, s))
            grid.addWidget(b, i // 3, i % 3)
        l2.addLayout(grid)
        l2.addSpacing(6)
        l2.addWidget(button("↩ استعادة الافتراضيات", "secondary",
                            lambda: self.set_colors(DEFAULTS["primary"], DEFAULTS["sidebar"])))
        l2.addStretch()
        cols.addWidget(c2, 1)
        root.addLayout(cols, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(button("💾 حفظ وتطبيق كافة التغييرات فورا", "success", self.save))
        bottom.addStretch()
        root.addLayout(bottom)

        self.refresh()

    def refresh(self, *_):
        self.pending_logo = None
        self.e_name.setText(CFG["kg_name"])
        self.e_addr.setText(CFG["address"])
        self.e_phone.setText(CFG["phone"])
        self.e_cur.setText(CFG["currency"])
        self.e_pass.setText(CFG.get("app_password", "123"))
        self.theme_combo.setCurrentIndex(0 if CFG.get("theme_mode", "Light") == "Light" else 1)
        self.colors = {"primary": CFG["primary"], "sidebar": CFG["sidebar"]}
        self.update_swatches()
        self.show_logo(CFG["logo"])

    def update_swatches(self):
        for key, btn in (("primary", self.btn_primary), ("sidebar", self.btn_sidebar)):
            col = self.colors[key]
            btn.setText(f"{col.upper()}   (اضغط لتغيير اللون)")
            btn.setStyleSheet(f"background:{col}; color:#FFFFFF; border:1px solid #CBD5E1; "
                              "border-radius:10px; padding:10px; font-weight:bold;")

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
                self.logo_preview.setPixmap(pm.scaled(90, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                                      Qt.TransformationMode.SmoothTransformation))
                return
        self.logo_preview.setText("بدون شعار")

    def pick_logo(self, *_):
        path, _f = QFileDialog.getOpenFileName(self, "اختيار الشعار", "", "صور (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        if QPixmap(path).isNull():
            info(self, "تعذر قراءة الصورة.")
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
        new_pass = self.e_pass.text().strip()
        if not new_pass:
            info(self, "كلمة السر لا يمكن أن تكون فارغة.")
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
                
        theme_mode = "Light" if self.theme_combo.currentIndex() == 0 else "Dark"
        
        values = {
            "kg_name": name, 
            "address": self.e_addr.text().strip(),
            "phone": self.e_phone.text().strip(),
            "currency": self.e_cur.text().strip() or DEFAULTS["currency"],
            "app_password": new_pass,
            "theme_mode": theme_mode,
            "primary": self.colors["primary"], 
            "sidebar": self.colors["sidebar"], 
            "logo": logo
        }
        save_settings(values)
        CFG.update(values)
        self.pending_logo = None
        self.on_apply()
        info(self, "تم حفظ الإعدادات وتطبيق الثيم والحماية بنجاح ✔")

def build_style():
    is_dark = CFG.get("theme_mode", "Light") == "Dark"
    
    bg_main = "#0F172A" if is_dark else "#F1F5F9"
    bg_card = "#1E293B" if is_dark else "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:1 #F8FAFC)"
    text_color = "#F8FAFC" if is_dark else "#1E293B"
    muted_color = "#94A3B8" if is_dark else "#64748B"
    border_color = "#334155" if is_dark else "#E2E8F0"
    table_alt = "#1E293B" if is_dark else "#F8FAFC"
    
    primary = CFG["primary"]
    sidebar = CFG["sidebar"]

    return f"""
QWidget {{ color:{text_color}; font-size:14px; font-family: 'Segoe UI', Tahoma, sans-serif; }}
QMainWindow, #content {{ background:{bg_main}; }}

#sidebar {{ 
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {sidebar}, stop:1 #0F172A); 
    border-left: 2px solid rgba(255, 255, 255, 15);
}}
#sidebar QLabel {{ color:#FFFFFF; }}
#sidebar QPushButton {{ 
    color:#FFFFFF; background:transparent; border:none; text-align:right;
    padding:14px 18px; border-radius:12px; font-size:15px; font-weight:600; 
    margin: 3px 8px;
}}
#sidebar QPushButton:hover {{ background:rgba(255, 255, 255, 30); }}
#sidebar QPushButton:checked {{ 
    background:{primary}; color:#FFFFFF; font-weight:bold; 
}}

#title {{ font-size:26px; font-weight:bold; color:{text_color}; }}
#muted {{ color:{muted_color}; font-weight:600; font-size:13px; }}

#card3d {{ 
    background: {bg_card};
    border: 1px solid {border_color}; 
    border-radius:16px; 
}}

#bignum {{ font-size:34px; font-weight:bold; color:{primary}; }}

QPushButton[kind="primary"], QPushButton[kind="secondary"],
QPushButton[kind="success"], QPushButton[kind="danger"] {{
    color:white; border:none; border-radius:10px; padding:10px 18px; font-weight:bold; font-size:14px;
}}
QPushButton[kind="primary"] {{ background:{primary}; }}
QPushButton[kind="secondary"] {{ background:#64748B; }}
QPushButton[kind="success"] {{ background:#059669; }}
QPushButton[kind="danger"] {{ background:#DC2626; }}

QLineEdit, QComboBox, QDateEdit, QPlainTextEdit {{
    background:{"#1E293B" if is_dark else "#FFFFFF"}; border:2px solid {border_color}; border-radius:10px; padding:8px 12px; font-size:14px; color:{text_color};
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QPlainTextEdit:focus {{ 
    border:2px solid {primary}; 
}}

QTableWidget {{ 
    background:{"#1E293B" if is_dark else "#FFFFFF"}; border:none; border-radius:14px;
    alternate-background-color:{table_alt}; selection-background-color:{primary};
    selection-color:#FFFFFF; gridline-color: {border_color}; color:{text_color};
}}
QHeaderView::section {{ 
    background:{primary}; color:#FFFFFF; padding:10px; border:none; font-weight:bold; border-radius: 4px;
}}
QScrollArea {{ border:none; background:transparent; }}
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(1360, 800)
        self.setMinimumSize(1100, 680)

        central = QWidget()
        central.setObjectName("content")
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(260)
        add_shadow(side, blur=30, y_offset=0, alpha=50)
        
        sl = QVBoxLayout(side)
        sl.setContentsMargins(12, 24, 12, 16)
        
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel()
        self.name_label.setStyleSheet("font-size:18px; font-weight:bold; margin-top:8px; color:white;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setWordWrap(True)
        
        sl.addWidget(self.logo_label)
        sl.addWidget(self.name_label)
        sl.addSpacing(20)

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
        
        backup = QPushButton("💾  نسخ احتياطي فوري")
        backup.setCursor(Qt.CursorShape.PointingHandCursor)
        backup.clicked.connect(self.backup)
        sl.addWidget(backup)

        lay.addWidget(side)
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.apply_branding(restyle=False)
        self.go(0)

    def apply_branding(self, restyle=True):
        if restyle:
            QApplication.instance().setStyleSheet(build_style())
        self.setWindowTitle(f"{CFG['kg_name']} - النسخة الاحترافية الآمنة")
        self.name_label.setText(CFG["kg_name"])
        pm = QPixmap(CFG["logo"]) if CFG["logo"] and Path(CFG["logo"]).exists() else QPixmap()
        if pm.isNull():
            self.logo_label.setText("🌈")
            self.logo_label.setStyleSheet("font-size:52px;")
        else:
            self.logo_label.setStyleSheet("")
            self.logo_label.setPixmap(pm.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))

    def go(self, index):
        self.stack.setCurrentIndex(index)
        self.stack.widget(index).refresh()

    def backup(self):
        default = f"backup-pro-{datetime.now():%Y-%m-%d-%H%M}.db"
        path, _ = QFileDialog.getSaveFileName(self, "حفظ نسخة احتياطية", default, "ملف قاعدة البيانات (*.db)")
        if path:
            shutil.copy2(DB_PATH, path)
            info(self, "تم حفظ النسخة الاحتياطية بنجاح ✔")

    def closeEvent(self, event):
        try:
            folder = DOCS_DIR / "Backups"
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(DB_PATH, folder / f"auto-pro-{date.today().isoformat()}.db")
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
    
    login = LoginDialog()
    if login.exec() != QDialog.DialogCode.Accepted or not login.authenticated:
        sys.exit(0)
        
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()