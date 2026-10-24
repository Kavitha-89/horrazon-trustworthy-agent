
import re

ALLOWED_SELLER_IDS = {40218, 40219, 40220, 40221}


def user_explicitly_requests_message(user_question):
    """Only the user's own message can authorize a seller message."""
    if not isinstance(user_question, str):
        return False

    question = user_question.casefold()

    # Require a direct request to send a WhatsApp message.
    action_phrases = (
        "send a whatsapp message",
        "send whatsapp message",
        "message the seller on whatsapp",
        "send the seller a whatsapp",
    )

    return any(phrase in question for phrase in action_phrases)


def authorize_seller_message(user_question, seller_id, message):
    """Validate user intent and arguments before allowing a message."""
    if not user_explicitly_requests_message(user_question):
        return False, "No explicit WhatsApp request from the user."

    if isinstance(seller_id, bool) or not isinstance(seller_id, int):
        return False, "Seller ID must be an integer."

    if seller_id not in ALLOWED_SELLER_IDS:
        return False, "Seller ID is not allow-listed."

    if not isinstance(message, str) or not message.strip():
        return False, "Message must not be empty."

    if len(message) > 1000:
        return False, "Message exceeds the 1000-character limit."

    return True, "Authorized by explicit user request."
