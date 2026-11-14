
import { useEffect, useState } from 'react'
import { health, ask, ingest } from './api'
import './App.css'

// СПИСОК ИСТОЧНИКОВ
function SourcesList({ sources }) {
  const [showAll, setShowAll] = useState(false)

  if (!Array.isArray(sources) || sources.length === 0) {
    return null
  }

  const sortedSources = [...sources].sort(
    (a, b) => (b.score || 0) - (a.score || 0)
  )

  const visibleSources = showAll
    ? sortedSources
    : sortedSources.slice(0, 3)

  return (
    <div className="sources">
      <div className="sources-heading">
        <strong>▤ Источники ({sources.length})</strong>
      </div>

      {visibleSources.map((source, index) => (
        <details className="source-card" key={index}>
          <summary>
            <div className="source-info">
              <strong>{source.file || 'Документ'}</strong>

              <small>
                {source.page ? `Стр. ${source.page} · ` : ''}
                Релевантность: {Math.round((source.score || 0) * 100)}%
              </small>
            </div>

            <span>⌄</span>
          </summary>

          <div className="source-text">
            {source.text}
          </div>
        </details>
      ))}

      {sources.length > 3 && (
        <button
          className="show-sources"
          onClick={() => setShowAll(!showAll)}
        >
          {showAll
            ? 'Скрыть'
            : `Показать все (${sources.length})`}
        </button>
      )}
    </div>
  )
}

function App() {
  const [serviceStatus, setServiceStatus] = useState('checking')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [uploadError, setUploadError] = useState('')
  async function handleFileChange(event) {
  const file = event.target.files?.[0]

  if (!file) return

  setUploadError('')

  const allowedExtensions = ['pdf', 'docx', 'txt', 'md']
  const extension = file.name.split('.').pop().toLowerCase()

  if (!allowedExtensions.includes(extension)) {
    setUploadError('Поддерживаются только PDF, DOCX, TXT и MD.')
    event.target.value = ''
    return
  }

  const maxSize = 25 * 1024 * 1024

  if (file.size > maxSize) {
    setUploadError('Файл больше 25 МБ. Выберите файл меньшего размера.')
    event.target.value = ''
    return
  }

  if (isUploading) {
    event.target.value = ''
    return
  }

  setIsUploading(true)

  try {
    const result = await ingest(file)

    setUploadedFiles((previousFiles) => [
      {
        filename: result.filename,
        chunks: result.chunks,
      },
      ...previousFiles.filter(
        (item) => item.filename !== result.filename
      ),
    ])
  } catch (error) {
    if (error.code === 400) {
      setUploadError('Формат не поддерживается или в файле не найден текст.')
    } else if (error.code === 413) {
      setUploadError('Файл больше 25 МБ.')
    } else {
      setUploadError(error.message || 'Не удалось загрузить документ.')
    }
  } finally {
    setIsUploading(false)
    event.target.value = ''
  }
}
  // ПРОВЕРКА СОСТОЯНИЯ СЕРВЕРА
  useEffect(() => {
    health()
      .then(() => setServiceStatus('online'))
      .catch(() => setServiceStatus('offline'))
  }, [])

  // ОТПРАВКА ВОПРОСА
  async function handleSend() {
    const text = question.trim()

    if (!text || isLoading) return

    if (text.length < 3 || text.length > 2000) {
      alert('Вопрос должен содержать от 3 до 2000 символов')
      return
    }

    setMessages((prev) => [
      ...prev,
      { role: 'user', content: text },
    ])

    setQuestion('')
    setIsLoading(true)

    try {
      const result = await ask(text)

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: result.answer,
          sources: result.sources || [],
          took_ms: result.took_ms,
          llm: result.llm,
        },
      ])
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: error.message || 'Не удалось получить ответ',
          isError: true,
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="app">

      {/* ЛЕВАЯ ПАНЕЛЬ */}
      <aside className="sidebar">

      <div className="brand">
         <div className="brand-mark">
           <img src="/psb-logo.png" alt="Логотип" />
        </div>
      </div>

        <nav className="sidebar-nav">
          <button className="new-chat">
            <span>＋</span> Новый чат
          </button>

        <button className="nav-item">
  <span className="nav-icon">◷</span>
  <span>История</span>
</button>

<button className="nav-item">
  <span className="nav-icon">▱</span>
  <span>Документы</span>
</button>

<button className="nav-item">
  <span className="nav-icon">⚙</span>
  <span>Настройки</span>
</button>
        </nav>

        {/* КАРТОЧКА СОЛА ГУДМАНА И ПРОФИЛЬ */}
        <div className="sidebar-bottom">

          <div className="saul-card">
            <img src="/saul-goodman.png" alt="Сол Гудман" />
          </div>

        <div className="profile">
          <div className="profile-avatar">Ю</div>

         <div className="profile-info">
            <strong>Юридический отдел</strong>
            <span>Демо-режим</span>
          </div>

         <button className="logout-button" title="Выйти" aria-label="Выйти">
            ⇥
          </button>
        </div>

        </div>
      </aside>

      {/* ОСНОВНАЯ ОБЛАСТЬ */}
      <main className="workspace">

        {/* ВЕРХНЯЯ ПАНЕЛЬ */}
        <header className="topbar">
          <input
            className="global-search"
            type="text"
            placeholder="Поиск по чатам и документам..."
          />

          <div className="topbar-actions">
  <div className={`status ${serviceStatus}`}>
    <span className="status-dot"></span>

    {serviceStatus === 'checking'
      ? 'Проверяем сервис...'
      : serviceStatus === 'online'
        ? 'Сервис доступен'
        : 'Сервис недоступен'}
  </div>

  <button className="theme-toggle" aria-label="Переключить тему">
    ☼
  </button>
</div>
        </header>

        {/* ДВЕ КОЛОНКИ */}
        <div className="content-layout">

          {/* СПИСОК ЧАТОВ */}
          <aside className="chats-panel">

            <div className="chats-heading">
              <h2>Чаты</h2>
              <span>☷</span>
            </div>

            <div className="chat-list">

              <button className="chat-item active">
                <span className="chat-icon">▤</span>
                <span className="chat-info">
                  <strong>Неустойка по договору</strong>
                  <small>В договоре предусмотрена...</small>
                </span>
                <span className="chat-time">14:32</span>
              </button>

              <button className="chat-item">
                <span className="chat-icon">▤</span>
                <span className="chat-info">
                  <strong>Сроки оплаты</strong>
                  <small>Оплата производится в течение...</small>
                </span>
                <span className="chat-time">Вчера</span>
              </button>

              <button className="chat-item">
                <span className="chat-icon">▤</span>
                <span className="chat-info">
                  <strong>Ответственность сторон</strong>
                  <small>Стороны несут ответственность...</small>
                </span>
                <span className="chat-time">Вчера</span>
              </button>

            </div>

            {/* ЗАГРУЗКА ДОКУМЕНТА */}
            <label
              className={`upload-card ${isUploading ? 'uploading' : ''}`}
              aria-disabled={isUploading}
              style={{ cursor: isUploading ? 'wait' : 'pointer' }}
            >
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md"
                onChange={handleFileChange}
                disabled={isUploading}
                style={{ display: 'none' }}
            />

            <div className="upload-icon">
              {isUploading ? '⏳' : '▤'}
            </div>

            <div className="upload-text">
              <strong>
                {isUploading ? 'Обработка документа...' : 'Загрузите документ'}
              </strong>

               <span>
                {isUploading
                  ? 'Пожалуйста, подождите'
                  : 'PDF, DOCX, TXT, MD · до 25 МБ'}
              </span>
            </div>

            <span className="upload-arrow">
              {isUploading ? '...' : '›'}
            </span>
          </label>

          {uploadError && (
            <div className="upload-error">
              {uploadError}
            </div>
          )}

{uploadedFiles.map((file, index) => (
  <div className="uploaded-file" key={`${file.filename}-${index}`}>
    <strong>✓ Проиндексировано: {file.filename}</strong>
    <span>{file.chunks} фрагментов</span>
  </div>
))}

          </aside>

          {/* ОКНО ПЕРЕПИСКИ */}
          <section className="conversation">

            <header className="conversation-header">
              <div className="conversation-title">
                <div className="conversation-icon">⚖</div>
                <h2>Неустойка по договору</h2>
                <button className="edit-title-button" aria-label="Изменить название чата">
                  ✎
                </button>
              </div>

              <span className="demo-badge">ⓘ Демо-режим</span>
            </header>

            {/* СООБЩЕНИЯ */}
            <div className="messages">

              {/* ПРИВЕТСТВИЕ, ЕСЛИ СООБЩЕНИЙ ЕЩЁ НЕТ */}
              {messages.length === 0 && (
                <div className="assistant-message">
                  <div className="assistant-avatar">⚖</div>

                  <div className="answer-card">
                    <p>
                      Здравствуйте! Я юридический помощник ПСБ.
                      Задайте вопрос, и я помогу найти информацию
                      в загруженных документах.
                    </p>
                  </div>
                </div>
              )}

              {/* ИСТОРИЯ СООБЩЕНИЙ */}
              {messages.map((message, index) => (
                <div key={index}>

                  {message.role === 'user' ? (

                    <div className="user-message">
                      {message.content}
                    </div>

                  ) : (

                    <div className="assistant-message">
                      <div className="assistant-avatar">⚖</div>

                      <div className="answer-card">

                        <p>{message.content}</p>

                        {/* ПОМЕТКА ДЕМО-РЕЖИМА */}
                        {message.llm === 'stub' && (
                          <div className="demo-badge">
                            Демо-режим: ответ собран из найденных фрагментов,
                            не сгенерирован нейросетью
                          </div>
                        )}

                        {/* ИСТОЧНИКИ ОТВЕТА */}
                        <SourcesList sources={message.sources} />

                        {/* ВРЕМЯ ОТВЕТА */}
                        {message.took_ms !== undefined && (
                          <div className="answer-footer">
                            <span>
                              ◷ Ответ за {(message.took_ms / 1000).toFixed(1)} сек.
                            </span>
                          </div>
                        )}

                      </div>
                    </div>

                  )}

                </div>
              ))}

              {/* ИНДИКАТОР ЗАГРУЗКИ */}
              {isLoading && (
                <div className="assistant-message">
                  <div className="assistant-avatar">⚖</div>
                  <div className="answer-card">
                    <p>Ищу информацию в документах...</p>
                  </div>
                </div>
              )}

            </div>

            {/* ПОЛЕ ВВОДА И ПРИМЕРЫ ВОПРОСОВ */}
            <div className="conversation-bottom">

              <div className="message-input">
                <span>⌁</span>

                <input
                  type="text"
                  placeholder="Введите ваш юридический вопрос..."
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      handleSend()
                    }
                  }}
                  disabled={isLoading}
                />

                <button
                  className="send-button"
                  onClick={handleSend}
                  disabled={isLoading || !question.trim()}
                >
                  ➤
                </button>
              </div>

              <div className="question-suggestions">
               <span>ϟ Примеры вопросов:</span>

                <button onClick={() => setQuestion('Какая неустойка за просрочку?')}>
                  Какая неустойка за просрочку?
                </button>

                <button onClick={() => setQuestion('Сроки оплаты по договору?')}>
                   Сроки оплаты по договору?
                </button>

                <button onClick={() => setQuestion('Как расторгнуть договор?')}>
                  Как расторгнуть договор?
                </button>
              </div>

            </div>

          </section>
        </div>

        {/* ПРЕДУПРЕЖДЕНИЕ */}
        <footer className="safety-note">
          ⓘ Проверяйте ответы по первоисточникам.
          Прототип не заменяет юридическую экспертизу.
        </footer>

      </main>
    </div>
  )
}

export default App