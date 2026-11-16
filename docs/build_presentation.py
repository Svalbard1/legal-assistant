"""Сборка PDF-презентации из векторных элементов ReportLab."""

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.lib.utils import ImageReader


ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).with_name("presentation.pdf")
W, H = 960, 540
NAVY = HexColor("#071B3F")
NAVY2 = HexColor("#102B59")
ORANGE = HexColor("#FF6A1A")
BLUE = HexColor("#3E75D8")
PALE = HexColor("#EEF3FB")
INK = HexColor("#14243D")
MUTED = HexColor("#60718A")
GREEN = HexColor("#1B9A78")
LINE = HexColor("#DCE5F1")

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))

c = canvas.Canvas(str(OUT), pagesize=(W, H), pageCompression=1)
c.setTitle("Legal Assistant — презентация решения")
c.setAuthor("Команда Legal Assistant")


def rect(x, y, w, h, fill, stroke=None, radius=12):
    c.setFillColor(fill)
    c.setStrokeColor(stroke or fill)
    c.roundRect(x, H - y - h, w, h, radius, fill=1, stroke=bool(stroke))


def text(x, y, value, size=14, color=INK, bold=False):
    c.setFillColor(color)
    c.setFont("DejaVu-Bold" if bold else "DejaVu", size)
    c.drawString(x, H - y - size, value)


def paragraph(x, y, value, width, size=14, color=INK, leading=None, bold=False, max_lines=None):
    leading = leading or size * 1.42
    font = "DejaVu-Bold" if bold else "DejaVu"
    lines = simpleSplit(value, font, size, width)
    if max_lines:
        lines = lines[:max_lines]
    for i, line in enumerate(lines):
        text(x, y + i * leading, line, size, color, bold)
    return y + len(lines) * leading


def bullet(x, y, value, width, size=14, color=INK, accent=ORANGE, leading=19):
    c.setFillColor(accent)
    c.circle(x + 4, H - y - 9, 3.2, fill=1, stroke=0)
    return paragraph(x + 16, y, value, width - 16, size, color, leading)


def base(n, section, title, subtitle=None):
    c.setFillColor(white)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(ORANGE)
    c.roundRect(50, H - 34, 9, 9, 2, fill=1, stroke=0)
    text(68, 27, section.upper(), 10, MUTED, True)
    paragraph(50, 57, title, 855, 28, NAVY, 33, True, 2)
    if subtitle:
        paragraph(50, 125, subtitle, 820, 14, MUTED, 20)
    c.setStrokeColor(LINE)
    c.line(50, 32, 910, 32)
    text(50, 514, "LEGAL ASSISTANT · Hack&Change 2026", 8, MUTED)
    c.setFont("DejaVu-Bold", 9)
    c.setFillColor(MUTED)
    c.drawRightString(910, H - 523, f"{n:02d} / 10")


def card(x, y, w, h, title, body, fill=PALE, eyebrow=None, body_size=13):
    rect(x, y, w, h, fill, radius=13)
    yy = y + 18
    if eyebrow:
        text(x + 17, yy, eyebrow.upper(), 9, ORANGE, True)
        yy += 20
    title_lines = simpleSplit(title, "DejaVu-Bold", 16, w - 34)
    paragraph(x + 17, yy, title, w - 34, 16, NAVY if fill != NAVY else white, 20, True)
    yy += len(title_lines) * 20 + 10
    paragraph(x + 17, yy, body, w - 34, body_size, MUTED if fill != NAVY else HexColor("#D6E2F4"), body_size * 1.42)


def finish():
    c.showPage()


# 1 — Cover and expert check path.
c.setFillColor(NAVY)
c.rect(0, 0, W, H, fill=1, stroke=0)
c.setFillColor(NAVY2)
c.circle(850, 430, 250, fill=1, stroke=0)
c.setStrokeColor(HexColor("#38547D"))
for r in (100, 150, 200):
    c.circle(850, 430, r, fill=0, stroke=1)
c.setFillColor(ORANGE)
c.roundRect(50, H - 45, 10, 10, 3, fill=1, stroke=0)
text(68, 35, "HACK&CHANGE 2026 · РЕШЕНИЕ КОМАНДЫ", 10, HexColor("#C4D1E7"), True)
paragraph(50, 82, "Юридический ответ\nначинается с источника", 720, 38, white, 46, True)
c.setFillColor(ORANGE)
c.roundRect(50, H - 192, 58, 6, 3, fill=1, stroke=0)
paragraph(50, 211, "Legal Assistant — RAG-ассистент для поиска по договорам и регламентам с проверяемыми фрагментами-основаниями.", 670, 17, HexColor("#D6E2F4"), 24)
text(50, 287, "РЕПОЗИТОРИЙ", 9, HexColor("#AFC0DA"), True)
text(50, 303, "github.com/Svalbard1/legal-assistant", 13, HexColor("#FFD0B2"), True)
c.linkURL("https://github.com/Svalbard1/legal-assistant", (50, H - 325, 410, H - 300), relative=0, thickness=0)
text(50, 328, "ПУБЛИЧНЫЙ ДЕМО-САЙТ", 9, HexColor("#AFC0DA"), True)
text(50, 345, "Не развёрнут · запуск локально через Docker", 12, white)
rect(50, 379, 735, 106, HexColor("#102B59"), HexColor("#38547D"), 12)
text(68, 393, "ПОРЯДОК ПРОВЕРКИ ЭКСПЕРТОМ", 10, ORANGE, True)
paragraph(68, 414, "1. cp .env.example .env  →  docker compose up --build -d\n2. Открыть localhost:5173 → «Документы» → загрузить разрешённый документ\n3. Вернуться в чат → задать вопрос → раскрыть источник и сверить фрагмент", 700, 12, white, 18)
text(50, 496, "Срез проекта · 16 ноября 2026 · база кейса не включена в публичную поставку", 9, HexColor("#B9C8DF"))
text(890, 515, "01 / 10", 9, HexColor("#B9C8DF"), True)
finish()

# 2 — Problem.
base(2, "01 · проблема", "Юристу нужен не «текст от ИИ», а проверяемое основание", "В договоре важны точная редакция, пункт и контекст. Уверенный, но неподтверждённый ответ создаёт риск.")
card(50, 205, 270, 220, "Долго искать вручную", "Условия разбросаны по файлам, редакциям и формулировкам. Важно не пропустить нужный пункт.", PALE, "Проблема")
card(345, 205, 270, 220, "Красивый ответ не равен верному", "Обычный чат-бот может звучать уверенно, но без первоисточника факт и применимость трудно проверить.", PALE, "Риск")
rect(640, 205, 270, 220, NAVY, radius=13)
text(660, 224, "КРИТЕРИЙ РЕШЕНИЯ", 9, ORANGE, True)
paragraph(660, 252, "Ответ с опорой на фрагмент", 225, 18, white, 24, True)
paragraph(660, 330, "Если оснований нет — система не маскирует пробел догадкой.", 225, 12, HexColor("#D6E2F4"), 17)
finish()

# 3 — Solution.
base(3, "02 · решение", "Сначала найти доказательство, затем сформулировать ответ", "Ответ формируется по найденным фрагментам; источники показываются рядом с результатом.")
steps = [(50,"Документ","PDF · DOCX · TXT · MD"),(270,"Разбор","чанки ~400 симв.\nперекрытие 50"),(490,"Поиск","bge-m3 + BM25\nслияние рангов"),(710,"Результат","ответ + источники\nили отказ по порогу")]
for i,(x,title,sub) in enumerate(steps):
    rect(x, 205, 190, 112, PALE if i != 3 else HexColor("#E9F4F1"), radius=13)
    text(x+16, 224, f"0{i+1}", 10, ORANGE, True)
    text(x+16, 245, title, 17, NAVY, True)
    paragraph(x+16, 274, sub, 158, 12, MUTED, 16)
    if i < 3: text(x+196, 246, "→", 20, ORANGE, True)
card(50, 344, 410, 112, "Чем отличается от обычного чата", "Вопрос сопоставляется с загруженными документами; рядом с ответом можно проверить найденные фрагменты.", white, "Осознанный выбор", 12)
card(480, 344, 430, 112, "Работа без внешней LLM", "Stub-режим возвращает детерминированную выжимку источников. Генерацию можно подключить отдельно.", white, "Надёжная деградация", 12)
finish()

# 4 — UI screenshots.
base(4, "03 · продуктовый сценарий", "Документ загружается в UI; чат и база документов — в одном интерфейсе")
screenshots = [
    (50, ROOT / "docs/assets/ui-chat.png", "ЧАТ · НОВЫЙ ДИАЛОГ", "Показан стартовый экран; ответ и источники появятся после вопроса."),
    (500, ROOT / "docs/assets/ui-documents.png", "ДОКУМЕНТЫ · СОСТОЯНИЕ ТЕСТОВОГО СТЕНДА", "На снимке: один файл проиндексирован, у второго ошибка индексации."),
]
for x, path, label, caption in screenshots:
    rect(x, 158, 410, 230, HexColor("#F3F6FB"), LINE, 12)
    c.saveState()
    clip = c.beginPath()
    clip.roundRect(x + 7, H - 158 - 230 + 7, 396, 216, 8)
    c.clipPath(clip, stroke=0)
    c.drawImage(ImageReader(str(path)), x + 7, H - 158 - 230 + 7,
                width=396, height=216, preserveAspectRatio=True, anchor="c")
    c.restoreState()
    text(x + 2, 400, label, 9, BLUE, True)
    paragraph(x + 2, 418, caption, 402, 10, MUTED, 14)
paragraph(50, 470, "Скриншоты интерфейса сняты с локального стенда; на экране документов видны и успешная, и неуспешная индексация.", 850, 10, INK, 14)
finish()

# 5 — Architecture.
base(5, "04 · архитектура", "Сервисы разделены по ответственности; retrieval работает локально")
nodes=[(50,"БРАУЗЕР","React · Nginx\n:5173"),(350,"BACKEND API","FastAPI · :8000\nдиалоги, документы"),(650,"ML / RAG API","FastAPI · :8002 host\n:8001 Compose")]
for x,t,b in nodes:
    rect(x, 176, 240, 90, PALE, radius=12); text(x+18,192,t,11,ORANGE,True); paragraph(x+18,216,b,205,13,NAVY,18,True)
text(304, 207, "→", 24, ORANGE, True); text(604, 207, "→", 24, ORANGE, True)
card(50, 300, 260, 145, "Qdrant embedded", "Индекс в persistent volume; ML запускается одним процессом из-за файловой блокировки.", white, "Поиск")
card(350, 300, 260, 145, "PostgreSQL", "Сессии, реплики и метаданные документов. Схема БД применяется через Alembic.", white, "История")
card(650, 300, 260, 145, "LLM — опционально", "По умолчанию stub. Внешний OpenAI-совместимый API подключается через env.", white, "Генерация")
text(50, 468, "Compose: PostgreSQL → миграции → Backend; также ML API и Frontend в Nginx.", 11, MUTED)
finish()

# 6 — quality eval.
base(6, "05 · качество retrieval", "На 27 тестовых вопросах recall@3 сохранён, MRR вырос", "Контрольный eval: sample-корпус · BAAI/bge-m3 · чанк 400 / overlap 50")
def bar(x,y,label,value,ratio,color):
    text(x,y,label,12,MUTED); c.setFont("DejaVu-Bold",12); c.setFillColor(NAVY); c.drawRightString(x+390,H-y-12,value)
    rect(x,y+24,390,13,HexColor("#E9EEF5"),radius=6); rect(x,y+24,390*ratio,13,color,radius=6)
bar(70,190,"Recall@3 · baseline","92,6%",.926,BLUE)
bar(70,247,"Recall@3 · текущий","92,6%",.926,ORANGE)
bar(70,304,"MRR · baseline","0,844",.844,BLUE)
bar(70,361,"MRR · текущий","0,865",.865,ORANGE)
rect(560, 190, 330, 105, NAVY, radius=14)
text(585, 212, "+0,021", 32, white, True)
paragraph(585, 258, "изменение MRR: 0,844 → 0,865", 285, 12, HexColor("#D6E2F4"), 17)
rect(560, 312, 330, 93, PALE, radius=14)
text(585, 330, "27 вопросов", 21, NAVY, True)
paragraph(585, 364, "Оценивали retrieval, не истинность генерации.", 280, 12, MUTED, 17)
text(70, 444, "Eval-критерий — попадание чанка в top-k по файлу/ключевым словам; это не оценка юридической точности.", 10, MUTED)
finish()

# 7 — choice table.
base(7, "06 · инженерный выбор", "Компактный чанк закрыл промах и сократил передаваемый контекст")
cols=[50,280,410,520,650,910]
headers=["ВАРИАНТ","RECALL@3","MRR","КОНТЕКСТ","РЕШЕНИЕ"]
rect(50, 170, 860, 38, NAVY, radius=7)
for i,h in enumerate(headers): text(cols[i]+10,182,h,9,white,True)
rows=[("500 / 50","94,4%","0,931","1 525 симв.","baseline"),("400 / 50","100,0%","0,935","1 238 симв.","выбрали"),("600 / 50","94,4%","0,875","1 793 симв.","не выбрали")]
for j,row in enumerate(rows):
    y=208+j*47
    if j==1: rect(50,y,860,44,HexColor("#FFF3EB"),radius=0)
    for i,val in enumerate(row): text(cols[i]+10,y+13,val,11,NAVY if j==1 else INK,j==1)
    c.setStrokeColor(LINE); c.line(50,H-y-44,910,H-y-44)
card(50, 375, 405, 86, "Вывод на этом тесте", "400/50 повысил Recall@3 с 94,4% до 100% и сократил контекст на ~19% относительно 500/50.", PALE, "", 11)
card(475, 375, 435, 86, "Отвергнутая альтернатива", "Структурные заголовки не подняли Recall@3, но снизили MRR и Recall@1.", PALE, "")
text(50, 472, "Отдельный сравнительный прогон из ML-аудита; набор и методика отличаются от контрольного eval предыдущего слайда.", 9, MUTED)
finish()

# 8 — boundaries, tests.
base(8, "07 · надёжность", "Слабый поиск или сбой модели не должны превращаться в выдуманный факт")
left=["Пустой индекс → API просит загрузить документы.","Слабый dense-score → отказ; unit-тест проверяет отказ и сохранение источников.","Внешняя LLM недоступна → fallback на выжимку фрагментов.","ML недоступен → Backend сообщает 502/504."]
for i,item in enumerate(left): bullet(60,174+i*49,item,400,12,INK,ORANGE,16)
rect(520, 165, 370, 255, PALE, radius=14)
text(545, 186, "ЛОКАЛЬНАЯ ПРОВЕРКА", 10, ORANGE, True)
text(545, 222, "76", 31, NAVY, True); paragraph(610,228,"ML tests: unit + API smoke",235,12,MUTED,17)
text(545, 275, "RUFF ✓", 19, NAVY, True); paragraph(680,280,"линтер ML",160,12,MUTED,17)
text(545, 326, "UI ✓", 19, NAVY, True); paragraph(630,331,"Frontend lint и build",220,12,MUTED,17)
paragraph(545, 371, "Тесты сервиса используют fake encoder; это не end-to-end оценка реальной модели.", 310, 10, MUTED, 14)
text(60, 430, "Ограничение: локальный порог score не надёжно разделяет ловушки и релевантные вопросы; качество отказов требует отдельной оценки.", 9, MUTED)
finish()

# 9 — value.
base(9, "08 · ценность и пилот", "Потенциальная ценность — сократить путь до пункта, сохранив контроль юриста")
card(50, 175, 410, 230, "Пользователю", "Быстрее найти условие\nПроверить фрагмент в первоисточнике\nПродолжить диалог с историей", NAVY, "Польза")
card(485, 175, 425, 230, "Бизнесу: измерить в пилоте", "Время до релевантного пункта\nДоля ответов с подтверждённым источником\nКорректные отказы вне корпуса\nДоля ручной эскалации", PALE, "Метрики")
text(50, 430, "План: теневой пилот → разметка юристами → сравнение с текущим процессом → контролируемый запуск.", 13, NAVY, True)
text(50, 463, "Сокращение времени — гипотеза для измерения, а не уже достигнутый результат.", 10, MUTED)
finish()

# 10 — status.
base(10, "09 · статус и следующие шаги", "Основной путь работает локально; до пилота нужны эксплуатационные контроли")
rect(50, 163, 415, 284, HexColor("#E9F4F1"), radius=13)
text(72, 183, "УЖЕ РЕАЛИЗОВАНО", 10, GREEN, True)
for i,item in enumerate(["Индексация документов и поиск.","Источники в ответах, сессии и история.","React UI, PostgreSQL и миграции.","Docker Compose всего стека.","Автономный ZIP-сабмит платформы."]): bullet(72,214+i*42,item,370,12,INK,GREEN,16)
rect(490, 163, 420, 284, PALE, radius=13)
text(512, 183, "ОГРАНИЧЕНИЯ / РАЗВИТИЕ", 10, ORANGE, True)
for i,item in enumerate(["Нет публичного demo; корпус кейса не включён в публичную поставку.","Демо-стенд показывает и успешную, и неуспешную индексацию; ошибки видны в UI.","Нет auth/ролей и production-наблюдаемости.","Далее: оценка отказов на размеченном корпусе, аудит доступа, пилот."]): bullet(512,214+i*49,item,370,12,INK,ORANGE,16)
paragraph(50, 464, "Проверка: README → Docker Compose → localhost:5173 → «Документы» → загрузить ml/data/sample/пример.txt → спросить о неустойке → сверить источник.", 850, 11, MUTED, 16)
finish()

c.save()
print(f"Created {OUT} ({OUT.stat().st_size:,} bytes)")