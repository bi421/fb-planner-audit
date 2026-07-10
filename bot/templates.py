"""Messenger templates for fb-planner-audit."""
from typing import Any, Dict, List

WELCOME_CAROUSEL: Dict[str, Any] = {
    "attachment": {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": [
                {
                    "title": "Аудит",
                    "subtitle": "Фэйсбүүл хуудасны рекламыг шалгах",
                    "buttons": [{"type": "postback", "title": "Аудит", "payload": "AUDIT"}],
                },
                {
                    "title": "Төлбөр",
                    "subtitle": "PRO төлбөрийн төлөлжүүлэх",
                    "buttons": [{"type": "postback", "title": "Төлбөр", "payload": "PAY"}],
                },
                {
                    "title": "Төлөвлөгөө",
                    "subtitle": "Автомаркетингийн төлөвлөгөө авах",
                    "buttons": [{"type": "postback", "title": "Төлөвлөгөө", "payload": "PLAN"}],
                },
            ],
        },
    }
}

QUICK_REPLIES_AUDIT: List[Dict[str, Any]] = [
    {"content_type": "text", "title": "Болсон аудит", "payload": "audit_yes"},
    {"content_type": "text", "title": "Шинэ аудит", "payload": "audit_new"},
    {"content_type": "text", "title": "Төлбөр", "payload": "PAY"},
]

AUDIT_RESULT_TEMPLATE: Dict[str, Any] = {
    "attachment": {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": [
                {
                    "title": "Аудит үр дүн",
                    "subtitle": "Таны хуудас шалгагдлаа.",
                    "buttons": [{"type": "postback", "title": "Дахин шалгах", "payload": "AUDIT"}],
                }
            ],
        },
    }
}

PLAN_RESULT_TEMPLATE: Dict[str, Any] = {
    "attachment": {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": [
                {
                    "title": "Төлөвлөгөө бэлэн",
                    "subtitle": "30 хоногийн төлөвлөгөөг татаж авна уу.",
                    "buttons": [{"type": "postback", "title": "Дахин үүсгэх", "payload": "PLAN"}],
                }
            ],
        },
    }
}

PAYMENT_TEMPLATE: Dict[str, Any] = {
    "attachment": {
        "type": "template",
        "payload": {
            "template_type": "generic",
            "elements": [
                {
                    "title": "PRO хувилбар",
                    "subtitle": "$29/сая — бүх үйлчилгээтэй.",
                    "buttons": [{"type": "web_url", "title": "Төлбөр хийх", "url": "https://example.com/pay"}],
                }
            ],
        },
    }
}

ERROR_TEMPLATE: Dict[str, Any] = {
    "text": "Уучлаарай, алдаа гарлаа. Дахин оролдоно уу."
}
