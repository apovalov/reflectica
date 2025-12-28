"""Keyboard utilities for Telegram bot."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_event_type_keyboard() -> InlineKeyboardMarkup:
    """Get inline keyboard for selecting event type."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Reflection", callback_data="type_reflection"),
                InlineKeyboardButton(text="Mindform", callback_data="type_mindform"),
            ],
            [
                InlineKeyboardButton(text="Dream", callback_data="type_dream"),
                InlineKeyboardButton(text="Drawing", callback_data="type_drawing"),
            ],
            [InlineKeyboardButton(text="Other", callback_data="type_other")],
        ]
    )
    return keyboard

