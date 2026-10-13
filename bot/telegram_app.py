"""Standalone Telegram bot entry point for the same audit engine.

Configure TELEGRAM_BOT_TOKEN in Render and run:
python -m bot.telegram_app
"""
from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from core.audit import audit_creative
from core.precheck import check_quota_and_scan

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Сайн байна уу! Facebook зарын текстээ илгээгээд бодлогын эрсдэлийн урьдчилсан шалгалт хийнэ үү. "
            "Үнэгүй багц 5 шалгалттай. Энэ нь Meta зөвшөөрөх баталгаа биш."
        )


async def audit_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if not message or not user or not message.text:
        return
    user_id = f"telegram:{user.id}"
    try:
        result = check_quota_and_scan(user_id, message.text)
        if result.get("status") == "paid_required":
            await message.reply_text("Үнэгүй 5 шалгалтын эрх дууссан. Үргэлжлүүлэхийн тулд веб апп дээр Starter эсвэл Agency багцаа сонгоно уу.")
            return
        report = audit_creative(message.text)
        findings = report["failed_rules"]
        lines = [
            f"Эрсдэлийн түвшин: {report['risk_level']}",
            f"Оноо: {report['score']}/100",
            f"Илэрсэн асуудал: {len(findings)}",
        ]
        for item in findings[:8]:
            lines.append(f"• {item.get('matched_text') or item['rule']}: {item.get('suggestion', '')}")
        lines.append("Анхааруулга: Энэ нь автомат урьдчилсан шалгалт бөгөөд Meta-ийн зөвшөөрлийг баталгаажуулахгүй.")
        await message.reply_text("\n".join(lines))
    except Exception:
        logger.exception("Telegram audit failed")
        await message.reply_text("Шалгалт түр амжилтгүй боллоо. Дахин оролдоно уу.")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, audit_message))
    logger.info("Starting Telegram audit bot")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
