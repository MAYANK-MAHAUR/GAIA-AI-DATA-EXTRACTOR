import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
import tempfile
import shutil
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

# --- Configuration ---
GAIA_DOMAIN_URL = os.getenv("GAIA_DOMAIN_URL")
OPENAI_API_KEY = os.getenv("GAIA_API_KEY")
model = os.getenv("MODEL")

client = OpenAI(
    base_url=f"{GAIA_DOMAIN_URL}/v1",
    api_key=OPENAI_API_KEY,
    timeout=90.0
)

UNIVERSAL_SYSTEM_PROMPT = """
You are a highly intelligent and versatile AI assistant. Your primary task is to extract relevant information from any given web page text content and return it in a structured JSON format.

Analyze the provided text to determine its primary nature (e.g., news article, blog post, product page, general informational page, research paper, etc.).

Based on the content, identify and extract the most relevant and prominent information.
Prioritize extracting common fields like:
- **title**: The main title of the page or content.
- **summary**: A concise 2-4 sentence overview of the page's main topic or purpose.
- **main_content_type**: Classify the page's primary content type (e.g., "article", "product listing", "informational page", "blog post", "FAQ", "documentation", "recipe").
- **author** (if applicable): The author's name for articles or blogs.
- **publication_date** (if applicable): The date the content was published (YYYY-MM-DD format if possible).
- **product_name** (if applicable and a product page): The name of the product.
- **price** (if applicable and a product page): The current price of the product, including currency symbol (e.g., "$199.99"). If a price range is found, pick the lowest.
- **currency** (if applicable and a product page): The currency of the product price (e.g., "USD", "INR", "EUR").
- **availability** (if applicable and a product page): Product stock status (e.g., "In Stock", "Out of Stock", "Limited Stock").
- **rating** (if applicable and a product page): The average rating of the product (e.g., "4.5 out of 5 stars").
- **number_of_reviews** (if applicable and a product page): The total number of reviews for the product.
- **key_details** (if applicable): A short list (3-5 items) of the most important facts, features, or takeaways, depending on the content type.

If a field is not applicable or cannot be found, omit it from the JSON or set its value to null (e.g., "author": null).
Ensure the output is always a valid JSON object.

Example for an Article:
{
  "title": "The Future of AI in Healthcare",
  "summary": "AI is rapidly transforming healthcare, from diagnostics to personalized treatment plans. This article explores the current applications and future potential of AI technologies in the medical field, highlighting ethical considerations and challenges.",
  "main_content_type": "article",
  "author": "Dr. Jane Doe",
  "publication_date": "2025-07-26",
  "key_details": [
    "AI improves diagnostic accuracy",
    "Personalized treatment with AI",
    "Ethical challenges in AI healthcare"
  ]
}

Example for a Product Page:
{
  "title": "XYZ Smartwatch Pro - Advanced Fitness Tracker",
  "summary": "The XYZ Smartwatch Pro offers comprehensive fitness tracking, long battery life, and smart notifications. It's designed for active individuals seeking a blend of style and cutting-edge technology.",
  "main_content_type": "product listing",
  "product_name": "XYZ Smartwatch Pro",
  "price": "$299.99",
  "currency": "USD",
  "availability": "In Stock",
  "rating": "4.7 out of 5 stars",
  "number_of_reviews": 1250,
  "key_details": [
    "Heart rate monitoring",
    "GPS tracking",
    "5-day battery life",
    "Water resistant"
  ]
}

Example for a General Informational Page (e.g., Wikipedia):
{
  "title": "India",
  "summary": "India is a vast South Asian country known for its diverse geography, rich history and vibrant culture. It is the world's most populous country and a major economic power.",
  "main_content_type": "informational page",
  "key_details": [
    "Second largest population globally",
    "Diverse cultural heritage",
    "Major emerging economy"
  ]
}
"""

def get_text_from_url(url, max_bytes_to_read=100 * 1024 * 1024, retries=3, initial_timeout=20):
    temp_file_path = None
    driver = None

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, 'extracted_content.txt')

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--incognito")
    chrome_options.add_argument(f"user-agent={headers['User-Agent']}")
    chrome_options.add_argument("--log-level=3")

    for attempt in range(retries):
        print(f"GAIA 🤖 : Attempt {attempt + 1}/{retries}: Fetching {url} with Selenium... ⏳")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        driver.set_page_load_timeout(initial_timeout)
        driver.get(url)

        WebDriverWait(driver, initial_timeout * 2).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        print("GAIA 🤖 : Page content (body tag) found, proceeding to extract. ✅")

        full_html_content = driver.page_source

        soup = BeautifulSoup(full_html_content, 'html.parser')

        for script_or_style in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'noscript']):
            script_or_style.decompose()

        text_content = soup.get_text(separator=' ', strip=True)
        text_content = ' '.join(text_content.split())

        if len(text_content.encode('utf-8')) > max_bytes_to_read:
            print(f"GAIA 🤖 : Warning: Extracted text content is large ({len(text_content.encode('utf-8')) / (1024*1024):.2f} MB), truncating for temp file. ✂️")
            text_content = text_content[:max_bytes_to_read]

        with open(temp_file_path, 'w', encoding='utf-8') as f:
            f.write(text_content)

        print(f"GAIA 🤖 : Extracted text written to temporary file: {temp_file_path} 📝")
        driver.quit()
        return temp_file_path

    return None

def extract_info_with_gaia_agent(temp_file_path: str) -> tuple[dict, str]:
    with open(temp_file_path, 'r', encoding='utf-8') as f:
        text_content = f.read()

    user_message_extraction = f"Extract information from the following web page content:\n\n{text_content[:8000]}..."

    chat_completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": UNIVERSAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_message_extraction},
        ],
        response_format={"type": "json_object"}
    )
    llm_response_content = chat_completion.choices[0].message.content
    extracted_info_dict = json.loads(llm_response_content)

    return extracted_info_dict, text_content

if __name__ == "__main__":
    print("========================================================")
    print("✨ GAIA 🤖 : Universal Smart Data Extractor Initiated ✨")
    print(f"GAIA 🤖 : Connecting to Gaia Domain... 🌐")
    print("========================================================")

    while True:
        user_url = input("YOU 🙋 : Enter the URL to extract data from (or 'exit' to quit): ").strip()
        print("========================================================")
        if user_url.lower() == 'exit':
            print("GAIA 🤖 : Exiting the program. Goodbye! 👋")
            print("========================================================")
            break
        if not user_url.startswith(('http://', 'https://')):
            print("GAIA 🤖 : Invalid URL. Please enter a URL starting with http:// or https:// 🔗")
            print("========================================================")
            continue

        temp_file_to_clean = None
        try:
            print(f"GAIA 🤖 : Attempting to fetch text from: {user_url} 🚀")
            temp_file_path = get_text_from_url(user_url)

            print("========================================================")
            if temp_file_path:
                temp_file_to_clean = temp_file_path
                print("GAIA 🤖 : Text fetched and stored in temporary file. Sending to Gaia AI agent for universal extraction... 🧠")

                extracted_info, full_webpage_text = extract_info_with_gaia_agent(temp_file_path)

                print("\n========================================================")
                print("✨ GAIA 🤖 : Extracted Information: ✨")
                print("========================================================")
                print(json.dumps(extracted_info, indent=2))
                print("========================================================")

                if extracted_info and "error" not in extracted_info and full_webpage_text:
                    print("\n========================================================")
                    print("🗣️ GAIA 🤖 : AI-Powered Q&A about the webpage content (Type 'done' to finish Q&A) 💬")
                    print("GAIA 🤖 : You can now ask ANY question based on the content of the page. 🤔")
                    print("========================================================")


                    qa_system_prompt = "You are a helpful assistant. Answer the user's question ONLY based on the provided webpage content. If the answer is not in the content, state that you cannot find it there."
                    qa_text_context = full_webpage_text[:8000]

                    while True:
                        user_question = input("YOU ❓ : Your question: ").strip()
                        print("========================================================")
                        if user_question.lower() == 'done':
                            print("GAIA 🤖 : Ending Q&A session. Returning to main menu. ➡️")
                            print("========================================================")
                            break

                        if not qa_text_context:
                            print("GAIA 🤖 : Error: No text content available for Q&A. 🚫")
                            print("========================================================")
                            break


                        qa_user_message = f"Based on the following content, please answer the question:\n\nContent:\n{qa_text_context}\n\nQuestion: {user_question}"

                        try:
                            qa_completion = client.chat.completions.create(
                                model=model,
                                messages=[
                                    {"role": "system", "content": qa_system_prompt},
                                    {"role": "user", "content": qa_user_message},
                                ],
                            )
                            qa_answer = qa_completion.choices[0].message.content
                            print(f"GAIA 💡 : **AI Answer:** {qa_answer}\n")
                            print("========================================================")
                        except Exception as e:
                            print(f"GAIA 🤖 : Error getting AI answer: {e} ❗")
                            print(f"GAIA 🤖 : Please ensure your Gaia AI agent is running and accessible: {e} 🖥️") # Added error detail
                            print("========================================================")
                            break
                else:
                    print("GAIA 🤖 : Cannot start AI-Powered Q&A as there was an error in extraction or no valid text content was obtained. 😕")
                    print("========================================================")

            else:
                print(f"GAIA 🤖 : Failed to get text from {user_url}. 😔")
                print("========================================================")

        finally:
            if temp_file_to_clean and os.path.exists(os.path.dirname(temp_file_to_clean)):
                print(f"GAIA 🤖 : Cleaning up temporary directory: {os.path.dirname(temp_file_to_clean)} 🧹")
                shutil.rmtree(os.path.dirname(temp_file_to_clean))
            print("========================================================")

    print("\n--- Script finished ---")