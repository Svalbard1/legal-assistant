
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeout || 30000);

  try {
    const isFormData = options.body instanceof FormData;

    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method || "GET",
      headers: isFormData
        ? undefined
        : options.body
          ? { "Content-Type": "application/json" }
          : undefined,
      body: isFormData
        ? options.body
        : options.body
          ? JSON.stringify(options.body)
          : undefined,
      signal: controller.signal,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      const messages = {
        422: "Проверьте вопрос: от 3 до 2000 символов",
        404: "По запросу ничего не найдено — переформулируйте",
        503: "База знаний пуста — загрузите документы",
        502: "Сервис временно недоступен, попробуйте позже",
        504: "Сервис временно недоступен, попробуйте позже",
      };

      throw {
        code: response.status,
        message: messages[response.status] || "Произошла ошибка. Попробуйте ещё раз.",
      };
    }

    return data;
  } catch (error) {
    if (error.code && error.message) {
      throw error;
    }

    if (error.name === "AbortError") {
      throw {
        code: "TIMEOUT",
        message: "Сервер долго не отвечает. Попробуйте ещё раз.",
      };
    }

    throw {
      code: "NETWORK_ERROR",
      message: "Не удалось связаться с сервером. Проверьте подключение.",
    };
  } finally {
    clearTimeout(timeout);
  }
}

// Проверка состояния сервера
export function health() {
  return request("/health");
}

// Отправка вопроса
export function ask(question, top_k = 5) {
  if (question.length < 3 || question.length > 2000) {
    return Promise.reject({
      code: 422,
      message: "Проверьте вопрос: от 3 до 2000 символов",
    });
  }

  return request("/ask", {
    method: "POST",
    body: { question, top_k },
  });
}

// Загрузка документа
export function ingest(file) {
  const formData = new FormData();
  formData.append("file", file);

  return request("/ingest", {
    method: "POST",
    body: formData,
    timeout: 120000,
  });
}