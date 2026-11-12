
from uuid import UUID

import pytest

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models import ChatSession, Message, MessageSource


@pytest.mark.asyncio
async def test_create_session(db_session):
    """Проверяет создание и сохранение диалога."""

    chat_session = ChatSession(
        title="Тестовый диалог"
    )

    db_session.add(chat_session)
    await db_session.flush()

    # Проверяем генерацию UUID.
    assert isinstance(chat_session.id, UUID)

    # Проверяем название диалога.
    assert chat_session.title == "Тестовый диалог"

    # Получаем диалог из базы данных.
    result = await db_session.execute(
        select(ChatSession).where(
            ChatSession.id == chat_session.id
        )
    )

    saved_session = result.scalar_one()

    assert saved_session.id == chat_session.id
    assert saved_session.title == "Тестовый диалог"

    # Проверяем автоматическое заполнение дат.
    assert saved_session.created_at is not None
    assert saved_session.updated_at is not None


@pytest.mark.asyncio
async def test_create_message_for_session(db_session):
    """Проверяет создание сообщения и его связь с диалогом."""

    # Создаём диалог.
    chat_session = ChatSession(
        title="Диалог для тестирования сообщения"
    )

    db_session.add(chat_session)
    await db_session.flush()

    # Создаём сообщение пользователя.
    message = Message(
        session_id=chat_session.id,
        role="user",
        content="Здравствуйте!",
    )

    db_session.add(message)
    await db_session.flush()

    # Проверяем UUID сообщения.
    assert isinstance(message.id, UUID)

    # Получаем сообщение из базы.
    result = await db_session.execute(
        select(Message).where(
            Message.id == message.id
        )
    )

    saved_message = result.scalar_one()

    # Проверяем содержимое сообщения.
    assert saved_message.content == "Здравствуйте!"
    assert saved_message.role == "user"

    # Проверяем связь с диалогом.
    assert saved_message.session_id == chat_session.id

    # Проверяем дату создания.
    assert saved_message.created_at is not None


@pytest.mark.asyncio
async def test_create_message_source(db_session):
    """Проверяет создание источника и его связь с сообщением."""

    # Создаём диалог.
    chat_session = ChatSession(
        title="Проверка источников"
    )

    db_session.add(chat_session)
    await db_session.flush()

    # Создаём ответ ассистента.
    message = Message(
        session_id=chat_session.id,
        role="assistant",
        content=(
            "Согласно документу, заявление "
            "рассматривается в установленный срок."
        ),
    )

    db_session.add(message)
    await db_session.flush()

    # Создаём источник для ответа.
    source = MessageSource(
        message_id=message.id,
        position=1,
        file="regulations.pdf",
        text=(
            "Заявление рассматривается "
            "в течение установленного срока."
        ),
        score=0.95,
        page=3,
    )

    db_session.add(source)
    await db_session.flush()

    # Проверяем UUID источника.
    assert isinstance(source.id, UUID)

    # Получаем источник из PostgreSQL.
    result = await db_session.execute(
        select(MessageSource).where(
            MessageSource.id == source.id
        )
    )

    saved_source = result.scalar_one()

    # Проверяем содержимое источника.
    assert saved_source.file == "regulations.pdf"
    assert (
        saved_source.text
        == "Заявление рассматривается в течение установленного срока."
    )
    assert saved_source.score == 0.95
    assert saved_source.page == 3
    assert saved_source.position == 1

    # Проверяем связь с сообщением.
    assert saved_source.message_id == message.id


@pytest.mark.asyncio
async def test_message_rejects_invalid_role(db_session):
    """Проверяет запрет недопустимой роли сообщения."""

    chat_session = ChatSession(
        title="Проверка ограничения роли"
    )

    db_session.add(chat_session)
    await db_session.flush()

    message = Message(
        session_id=chat_session.id,
        role="admin",
        content="Недопустимая роль",
    )

    db_session.add(message)

    # PostgreSQL должна отклонить запись.
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_message_source_rejects_zero_position(db_session):
    """Проверяет запрет нулевой позиции источника."""

    chat_session = ChatSession(
        title="Проверка позиции источника"
    )

    db_session.add(chat_session)
    await db_session.flush()

    message = Message(
        session_id=chat_session.id,
        role="assistant",
        content="Ответ ассистента",
    )

    db_session.add(message)
    await db_session.flush()

    source = MessageSource(
        message_id=message.id,
        position=0,
        file="regulations.pdf",
        text="Текст источника",
        score=0.9,
        page=1,
    )

    db_session.add(source)

    # PostgreSQL должна отклонить позицию 0.
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_delete_session_cascades_to_messages_and_sources(db_session):
    """Проверяет каскадное удаление на стороне PostgreSQL."""

    # Создаём диалог.
    chat_session = ChatSession(
        title="Проверка каскадного удаления"
    )

    db_session.add(chat_session)
    await db_session.flush()

    # Создаём сообщение ассистента.
    message = Message(
        session_id=chat_session.id,
        role="assistant",
        content="Ответ с источником",
    )

    db_session.add(message)
    await db_session.flush()

    # Создаём источник сообщения.
    source = MessageSource(
        message_id=message.id,
        position=1,
        file="law.pdf",
        text="Фрагмент документа",
        score=0.95,
        page=5,
    )

    db_session.add(source)
    await db_session.flush()

    # Удаляем диалог напрямую через SQL DELETE.
    # Это позволяет проверить именно ON DELETE CASCADE в PostgreSQL.
    await db_session.execute(
        delete(ChatSession)
        .where(ChatSession.id == chat_session.id)
        .execution_options(synchronize_session=False)
    )

    # Проверяем, что сообщение автоматически удалилось.
    message_result = await db_session.execute(
        select(Message.id).where(
            Message.id == message.id
        )
    )

    assert message_result.scalar_one_or_none() is None

    # Проверяем, что источник тоже автоматически удалился.
    source_result = await db_session.execute(
        select(MessageSource.id).where(
            MessageSource.id == source.id
        )
    )

    assert source_result.scalar_one_or_none() is None
