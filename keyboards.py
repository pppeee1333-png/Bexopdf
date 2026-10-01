from telegram import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    KeyboardButton,
)

PRIMARY = "primary"
SUCCESS = "success"
DANGER = "danger"


# ============================================================
# القائمة الرئيسية
# ============================================================

MAIN_MENU = ReplyKeyboardMarkup([
    [
        KeyboardButton("📎 دمج PDF", style=PRIMARY),
        KeyboardButton("🖼️ صور لـ PDF", style=PRIMARY),
    ],
    [
        KeyboardButton("📸 استخراج صور", style=PRIMARY),
        KeyboardButton("🔢 ترقيم الصفحات", style=PRIMARY),
    ],
    [
        KeyboardButton("✂️ تقسيم", style=PRIMARY),
        KeyboardButton("🗑️ حذف صفحات", style=DANGER),
    ],
    [
        KeyboardButton("📉 ضغط", style=PRIMARY),
        KeyboardButton("🔒 حماية", style=PRIMARY),
    ],
    [
        KeyboardButton("🔓 إزالة الحماية", style=DANGER),
    ],
], resize_keyboard=True)


# ============================================================
# لوحة الإدارة
# ============================================================

ADMIN_MENU = ReplyKeyboardMarkup([
    [
        KeyboardButton("👑 لوحة التحكم", style=PRIMARY),
    ]
], resize_keyboard=True)


# ============================================================
# قائمة العملية
# ============================================================

ACTION_MENU = ReplyKeyboardMarkup([
    [
        KeyboardButton("✅ إنهاء العملية", style=SUCCESS),
        KeyboardButton("➕ إضافة ملفات أخرى", style=PRIMARY),
    ],
    [
        KeyboardButton("❌ إلغاء", style=DANGER),
    ],
], resize_keyboard=True)


# ============================================================
# أزرار عامة
# ============================================================

CANCEL_BTN = InlineKeyboardMarkup([
    [
        InlineKeyboardButton(
            "❌ إلغاء",
            callback_data="cancel",
            style=DANGER,
        )
    ]
])


BACK_BTN = InlineKeyboardMarkup([
    [
        InlineKeyboardButton(
            "⬅️ رجوع",
            callback_data="back",
            style=PRIMARY,
        )
    ]
])


# ============================================================
# 📉 مستويات ضغط PDF
# ============================================================

def compression_levels_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📱 Screen — 72 DPI",
                callback_data="compress_screen",
                style=PRIMARY,
            )
        ],
        [
            InlineKeyboardButton(
                "📖 E-book — 150 DPI",
                callback_data="compress_ebook",
                style=PRIMARY,
            )
        ],
        [
            InlineKeyboardButton(
                "🖨️ Printer — 300 DPI",
                callback_data="compress_printer",
                style=SUCCESS,
            )
        ],
        [
            InlineKeyboardButton(
                "❌ إلغاء",
                callback_data="cancel",
                style=DANGER,
            )
        ],
    ])
