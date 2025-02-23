import os
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем значения API-ключа и токенов из переменных окружения
HUGGING_FACE_API_KEY = os.getenv("HUGGING_FACE_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Проверка на наличие переменных окружения
if not HUGGING_FACE_API_KEY or not BOT_TOKEN or not CHAT_ID:
    print("❌ Отсутствуют необходимые переменные окружения.")
    exit()

# URLs
CRYPTO_NEWS_URL = "https://crypto.news/"

# Получаем последнюю новость
def get_latest_news():
    response = requests.get(CRYPTO_NEWS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    news_list = soup.find(class_='home-latest-news__list')

    if not news_list:
        print("❌ Не удалось найти новости!")
        return None  

    news_element = news_list.find('a', class_='home-latest-news__item home-latest-news-item')
    return news_element['href'] if news_element else None

# Получаем текст новости и картинку (без заголовка)
def get_news_content_and_image(link):
    response = requests.get(link, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')
    content_element = soup.find(class_='post-detail__content blocks')

    if not content_element:
        print("⚠️ Контент не найден!")
        return "", None

    for unwanted in content_element.find_all(class_=['cn-block-related-link', 'token-badge-container']):
        unwanted.decompose()

    content = content_element.get_text(separator=' ', strip=True)

    # Получаем URL изображения
    img_url = get_image_url(soup)

    # Получаем заголовок
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else "Заголовок не найден"

    return content, img_url, title

# Получаем URL изображения
def get_image_url(soup):
    # Если изображение представлено через <img>
    img_tag = soup.find('img', class_='post-detail__image wp-post-image')
    if img_tag:
        return img_tag['src']
    
    # Если изображение представлено через <picture>
    picture_tag = soup.find('picture', class_='post-detail__image wp-post-image')
    if picture_tag:
        # Проверяем, если есть source с форматом .webp
        source_tag = picture_tag.find('source', type='image/webp')
        if source_tag:
            return source_tag['srcset']
        
        # В противном случае берем <img> из тега <picture>
        img_tag = picture_tag.find('img')
        if img_tag:
            return img_tag['src']
    
    # Если изображение не найдено, возвращаем None
    return None

# Переводим заголовок с помощью Google Translate
def translate_title(title):
    return GoogleTranslator(source="auto", target="ru").translate(title)

# Анализируем текст через ИИ и переводим на русский (не ограничиваем длину текста)
def analyze_text(text):
    prompt = f"Please summarize the following news article in a clear and concise manner, highlighting the main points and keeping the context intact: {text}"
    payload = {"inputs": prompt, "parameters": {"max_length": 1000, "temperature": 0.5}}
    response = requests.post("https://api-inference.huggingface.co/models/facebook/bart-large-cnn", headers={"Authorization": f"Bearer {HUGGING_FACE_API_KEY}"}, json=payload)

    if response.status_code == 200 and response.json():
        summary = response.json()[0].get("summary_text", "⚠️ Ошибка анализа")
    else:
        summary = "⚠️ Ошибка анализа"

    return GoogleTranslator(source="en", target="ru").translate(summary)

# Обрезка изображения
def crop_image(img_url):
    img_response = requests.get(img_url)
    img = Image.open(BytesIO(img_response.content))

    # Обрезаем изображение снизу на 100 пикселей
    width, height = img.size
    img_cropped = img.crop((0, 0, width, height - 100))

    # Сохраняем в память
    img_io = BytesIO()
    img_cropped.save(img_io, format="JPEG")
    img_io.seek(0)
    
    return img_io

# Отправка поста в Telegram (с жирным заголовком, без эмодзи в тексте)
def send_telegram_post(translated_title, summary, img_url, news_link):
    message = f"*{translated_title}*\n\n{summary}\n\n🔗 Источник: {news_link}"  # Добавлена ссылка на источник

    # Если есть изображение, отправляем его с текстом в одном сообщении
    if img_url:
        img_io = crop_image(img_url)
        send_photo_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"

        response = requests.post(send_photo_url, data={
            'chat_id': CHAT_ID,
            'caption': message,
            'parse_mode': 'Markdown'
        }, files={'photo': ('cropped.jpg', img_io, 'image/jpeg')})

        if response.status_code == 200:
            print("✅ Пост отправлен в Telegram!")
        else:
            print(f"❌ Ошибка при отправке поста: {response.text}")
    else:
        send_message_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        response = requests.post(send_message_url, data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        })

        if response.status_code == 200:
            print("✅ Сообщение отправлено!")
        else:
            print(f"❌ Ошибка при отправке сообщения: {response.text}")


# Основной процесс
news_link = get_latest_news()

if news_link:
    news_content, img_url, title = get_news_content_and_image(news_link)
    translated_title = translate_title(title)  # Переводим заголовок
    summary = analyze_text(news_content)  # Анализируем полный текст новости

    print(f"🌍 Последняя новость:\n🔗 {news_link}")
    print(f"📢 Заголовок: {translated_title}")
    print(f"📜 Анализ: {summary}")

    # Отправляем в Telegram
    send_telegram_post(translated_title, summary, img_url, news_link)
else:
    print("❌ Не удалось получить новость.")
