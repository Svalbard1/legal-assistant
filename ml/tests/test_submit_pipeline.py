"""Регрессионные тесты платформенного пайплайна сабмита."""

from submit import solution


def test_system_prompt_requires_scope_control_and_keeps_source_line():
    prompt = solution.SYSTEM_PROMPT

    assert "Не добавляй сопутствующие условия" in prompt
    assert "ответь на каждую" in prompt
    assert '"Источник: <название основного документа>"' in prompt


def test_retrieval_query_uses_last_user_turn_for_standalone_question():
    dialogue = (
        "Пользователь: Какой гарантийный срок по П-17/2024?\n"
        "Ассистент: По какому поставщику уточнить?\n"
        "Пользователь: По договору ПТ-05/2023 какая гарантия на компьютеры?"
    )

    assert solution.retrieval_query(dialogue) == (
        "По договору ПТ-05/2023 какая гарантия на компьютеры?"
    )


def test_parse_dialogue_provides_one_query_and_user_only_entities():
    dialogue = (
        "Пользователь: Какой срок по договору А-08/2024?\n"
        "Ассистент: Возможно, 30 дней по пункту 9.9.\n"
        "Пользователь: А какой срок?"
    )

    context = solution.parse_dialogue(dialogue)

    assert context.raw_history == dialogue
    assert context.last_user_turn == "А какой срок?"
    assert context.retrieval_query.startswith("Какой срок по договору А-08/2024?")
    assert context.entities["document_ids"] == ["А-08/2024"]
    assert "9.9" not in context.entities["clauses"]
    assert "30 дней" not in context.retrieval_query
    assert context.history_recognized


def test_parse_dialogue_flags_unknown_role_format():
    context = solution.parse_dialogue(
        "User: Earlier question\nAssistant: untrusted previous answer\nUser: What date?"
    )

    assert not context.history_recognized
    assert context.retrieval_query == context.raw_history


def test_retrieval_query_inherits_topic_for_short_anaphora():
    dialogue = (
        "Пользователь: Мы арендуем склад у Северного Склада по договору А-08/2024. "
        "Как оформляется возврат помещения?\n"
        "Ассистент: Нужно проверить договор.\n"
        "Пользователь: А какой срок?"
    )

    query = solution.retrieval_query(dialogue)

    assert "А-08/2024" in query
    assert "возврат помещения" in query
    assert "А какой срок?" in query
    assert "Нужно проверить договор" not in query


def test_retrieval_query_does_not_inherit_topic_after_clear_topic_change():
    dialogue = (
        "Пользователь: Какой срок возврата склада по договору А-08/2024?\n"
        "Ассистент: Проверю условия.\n"
        "Пользователь: А по договору П-17/2024 какой срок приемки?"
    )

    assert solution.retrieval_query(dialogue) == (
        "А по договору П-17/2024 какой срок приемки?"
    )


def test_retrieval_query_keeps_explicit_id_and_restores_missing_topic():
    dialogue = (
        "Пользователь: Мы арендуем склад у «Северного Склада». Планируем съезжать.\n"
        "Ассистент: Подскажите номер договора, чтобы я мог проверить условия возврата помещения.\n"
        "Пользователь: А-08/2024. Можно просто сдать ключи или обязательно оформлять акт?"
    )

    query = solution.retrieval_query(dialogue)

    assert "А-08/2024" in query
    assert "Северного Склада" in query
    assert "Планируем съезжать" in query
    assert "обязательно оформлять акт" in query


def test_retrieval_query_does_not_append_old_counterparty_to_specific_new_question():
    dialogue = (
        "Пользователь: У ООО «Северный Склад» какие сроки возврата помещения?\n"
        "Ассистент: Проверю.\n"
        "Пользователь: «Альфа-Трейдинг», у них компьютеры покупали. На сколько гарантия?"
    )

    query = solution.retrieval_query(dialogue)

    assert query == "«Альфа-Трейдинг», у них компьютеры покупали. На сколько гарантия?"
    assert "Северный Склад" not in query


def test_followup_keeps_named_counterparty_and_identifier_after_clarification():
    dialogue = (
        "Пользователь: Подскажите гарантию по договору с «Альфой».\n"
        "Ассистент: Уточните, «Альфа-Трейд» или «Альфа-Трейдинг»?\n"
        "Пользователь: «Альфа-Трейдинг», у них компьютеры покупали. На сколько гарантия?"
    )

    query = solution.retrieval_query(dialogue)

    assert "Альфа-Трейдинг" in query
    assert "Подскажите гарантию по договору" not in query
    assert "Альфа-Трейд» или" not in query
    assert "компьютеры" in query


def test_affirmative_followup_can_use_confirmed_entity_not_assistant_answer():
    dialogue = (
        "Пользователь: Подписали новый договор, оригинал пока у меня.\n"
        "Ассистент: Вы про порядок передачи документов в ООО «Меридиан» после подписания?\n"
        "Пользователь: Да. В юротдел нужно отнести сразу или есть какой-то срок?"
    )

    query = solution.retrieval_query(dialogue)

    assert "новый договор" in query
    assert "срок" in query
    assert "Да." in query
    assert "Меридиан" in query


def test_affirmative_followup_query_does_not_copy_assistant_facts():
    dialogue = (
        "Пользователь: Подписали новый договор, оригинал пока у меня.\n"
        "Ассистент: Вы про порядок передачи документов в ООО «Меридиан» после подписания?\n"
        "Пользователь: Да. В юротдел нужно отнести сразу или есть какой-то срок?"
    )

    query = solution.retrieval_query(dialogue)

    assert "Меридиан" in query
    assert "новый договор" in query
    assert "юротдел" in query
    assert "ООО" not in query


def test_affirmative_followup_does_not_override_user_named_different_counterparty():
    dialogue = (
        "Пользователь: Подписали договор поставки с ООО «Альфа-Трейд».\n"
        "Ассистент: Вы про новый договор в ООО «Меридиан»?\n"
        "Пользователь: Да. Какая гарантия?"
    )

    query = solution.retrieval_query(dialogue)

    assert "Альфа-Трейд" in query
    assert "Меридиан" not in query


def test_unrecognized_dialogue_falls_back_to_original_question():
    dialogue = "User: Question from a format this parser does not recognize"

    assert solution.retrieval_query(dialogue) == dialogue


def test_tokenizer_keeps_negation_and_exact_legal_identifiers():
    tokens = solution._tokenize(
        "Не допускается по договору П-17/2024, ст. 70, п. 3.2"
    )

    assert "не" in tokens
    assert "допускается" in tokens
    assert {"п", "17", "2024", "ст", "70", "3", "2"}.issubset(tokens)


def test_bm25_uses_exact_document_id_from_filename_as_weak_signal():
    chunks = [
        {"file": "Договор П-17-2024.txt", "text": "Порядок поставки товара."},
        {"file": "Договор ПТ-05-2023.txt", "text": "Порядок поставки товара."},
    ]
    index = solution.BM25Index(chunks)

    assert index.search("условия договора П-17/2024", 2)[0][1] == 0


def test_name_rank_does_not_match_only_generic_counterparty_words():
    chunks = [
        {"file": "Договор Альфа-Трейд.txt", "text": "Поставка товара."},
        {"file": "Договор Альфа-Трейдинг.txt", "text": "Поставка товара."},
    ]

    assert solution.name_rank("условия Альфа", chunks, {}) == []


def test_normalized_query_keeps_negation_and_exact_legal_identifiers():
    raw = "Не допускается по договору П-17/2024, ст. 70, п. 3.2"
    query = solution._tokenize(solution.retrieval_query(raw))

    assert "не" in query
    assert {"17", "2024", "70", "3", "2"}.issubset(query)


def test_bm25_distinguishes_positive_and_negative_clauses():
    chunks = [
        {"file": "allow.txt", "text": "Предоплата допускается по соглашению сторон."},
        {"file": "deny.txt", "text": "Предоплата не допускается по договору."},
    ]
    index = solution.BM25Index(chunks)

    assert index.search("предоплата не допускается", 2)[0][1] == 1


def test_bm25_search_refuses_when_every_candidate_has_zero_score(monkeypatch):
    monkeypatch.setattr(solution, "USE_EMBEDDINGS", False)
    search, _ = solution.build_search([("law.txt", "Налоговая ставка.")], [])
    monkeypatch.setattr(solution, "llm_answer", lambda *_a, **_k: "не должен вызваться")

    result = solution.answer_one(
        "Вопрос о погоде", "совершенно не связанные слова", search, 0
    )

    assert result == solution.REFUSAL


def test_assemble_context_does_not_cut_a_norm_midway():
    first = {"file": "a.txt", "chunk_idx": 0, "text": "A" * 300}
    second = {"file": "b.txt", "chunk_idx": 0, "text": "B" * 300}

    context = solution.assemble_context([(first, 1.0), (second, 0.9)], max_chars=400)

    assert "A" * 300 in context
    assert "B" * 300 not in context


def test_search_reranks_wide_candidate_pool_before_context_cut(monkeypatch):
    chunks = [(f"doc-{i}.txt", f"Текст положения номер {i}.") for i in range(40)]
    monkeypatch.setattr(solution, "USE_EMBEDDINGS", True)
    monkeypatch.setattr(solution, "RERANKER_MODEL", "test-reranker")
    monkeypatch.setattr(solution, "CANDIDATE_K", 40)
    monkeypatch.setattr(solution, "CONTEXT_K", 5)
    monkeypatch.setattr(solution, "RERANKER_TOP_N", 40)
    monkeypatch.setattr(solution, "embed", lambda texts: [[1.0, 0.0] for _ in texts])
    rerank_call = {}

    def fake_rerank(query, documents, top_n):
        rerank_call.update(query=query, documents=documents, top_n=top_n)
        return [(i, 1.0 - i / 100) for i in (39, 0, 1, 2, 3)]

    monkeypatch.setattr(solution, "rerank", fake_rerank)
    search, _ = solution.build_search(chunks, [("q", "положение")])
    results, _mode = search("положение", 0)

    assert len(rerank_call["documents"]) == 40
    assert rerank_call["top_n"] == 40
    assert rerank_call["query"] == "положение"
    assert len(results) == 5
    expected_text = rerank_call["documents"][39].split("Фрагмент: ", 1)[1]
    assert results[0][0]["text"] == expected_text


def test_answer_one_searches_effective_question_and_expands_editions(monkeypatch):
    regulation_2025 = {
        "file": "Регламент согласования договоров ред 2025",
        "text": "Порог — 15 млн рублей.",
        "chunk_idx": 0,
    }
    regulation_2023 = {
        "file": "Регламент согласования договоров ред 2023 (утратил силу)",
        "text": "Порог — 10 млн рублей.",
        "chunk_idx": 1,
    }
    other = {"file": "Договор поставки П-17-2024", "text": "условия", "chunk_idx": 0}
    search_calls = []
    generation_calls = []

    def search(query, q_index):
        search_calls.append((query, q_index))
        return [(regulation_2025, 0.7), (other, 0.6), (other, 0.5),
                (regulation_2023, 0.4)], "embeddings"

    def generate(question, top, history_messages=None):
        generation_calls.append((question, top, history_messages))
        return "Ответ. Источник: регламент"

    monkeypatch.setattr(solution, "llm_answer", generate)
    dialogue = (
        "Пользователь: Договор на 12 млн рублей заключали в августе 2024 года.\n"
        "Ассистент: Проверю требования.\n"
        "Пользователь: Нужно ли было одобрение?"
    )

    answer = solution.answer_one(
        dialogue, solution.effective_question(dialogue), search, 4)

    assert answer == "Ответ. Источник: регламент"
    assert search_calls == [(
        "Договор на 12 млн рублей заключали в августе 2024 года. Нужно ли было одобрение?",
        4,
    )]
    context_files = [chunk["file"] for chunk, _score in generation_calls[0][1]]
    assert regulation_2023["file"] in context_files
    assert generation_calls[0][0] == dialogue
    assert generation_calls[0][2] == [
        {"role": "user", "content": "Договор на 12 млн рублей заключали в августе 2024 года."},
        {"role": "assistant", "content": "Проверю требования."},
    ]


def test_edition_companion_does_not_change_refusal_decision(monkeypatch):
    chunks = [
        ({"file": "Регламент ред 2025", "text": "2025", "chunk_idx": 0}, 0.29),
        ({"file": "Регламент ред 2023", "text": "2023", "chunk_idx": 1}, 0.28),
    ]
    monkeypatch.setattr(solution, "REFUSAL_THRESHOLD", 0.30)
    monkeypatch.setattr(
        solution, "llm_answer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("LLM must not run")),
    )

    result = solution.answer_one("Вопрос о регламенте", "Вопрос о регламенте",
                                 lambda _query, _idx: (chunks, "embeddings"), 0)

    assert result == solution.REFUSAL