# STREAMLIT VERSION (SOMETIMES HALLUCINATIONS RETRY IN THIS CASE)

# run by (streamlit run app.py)
import streamlit as st
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

GAIA_DOMAIN_URL = os.getenv("GAIA_DOMAIN_URL")
OPENAI_API_KEY = os.getenv("GAIA_API_KEY")
model = os.getenv("MODEL")

if not GAIA_DOMAIN_URL or not OPENAI_API_KEY or not model:
    st.error("⚠ Missing GAIA_DOMAIN_URL, GAIA_API_KEY, or MODEL in your .env file!")
    st.stop()

client = OpenAI(
    base_url=f"{GAIA_DOMAIN_URL}/v1",
    api_key=OPENAI_API_KEY,
    timeout=90.0
)

UNIVERSAL_SYSTEM_PROMPT = """ """


st.markdown("""
<style>
.extracted-box {
    background-color: #f8f9fa;
    border: 1px solid #ddd;
    padding: 1rem;
    border-radius: 8px;
    font-size: 0.95rem;
    color: #333;
}
</style>
""", unsafe_allow_html=True)


def get_text_from_url(url, service_obj, max_bytes_to_read=100 * 1024 * 1024, retries=3, initial_timeout=20):
    temp_dir = tempfile.mkdtemp()
    temp_file_path = os.path.join(temp_dir, 'extracted_content.txt')

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91 Safari/537.36'
    }

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
        try:
            driver = webdriver.Chrome(service=service_obj, options=chrome_options)
            driver.set_page_load_timeout(initial_timeout)
            driver.get(url)

            WebDriverWait(driver, initial_timeout * 2).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            soup = BeautifulSoup(driver.page_source, 'html.parser')

            for tag in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'noscript']):
                tag.decompose()

            text_content = ' '.join(soup.get_text(separator=' ', strip=True).split())

            if len(text_content.encode('utf-8')) > max_bytes_to_read:
                text_content = text_content[:max_bytes_to_read]

            with open(temp_file_path, 'w', encoding='utf-8') as f:
                f.write(text_content)

            return temp_file_path
        except Exception as e:
            if attempt == retries - 1:
                st.error(f"❌ Failed to fetch content after {retries} attempts: {e}")
                return None
        finally:
            if 'driver' in locals():
                driver.quit()
    return None

def safe_chat_completion(messages, response_format=None):
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=response_format
        )
        return completion
    except Exception as e:
        st.error(f"❌ API request failed: {e}")
        return None

def extract_info_with_gaia_agent(temp_file_path: str):
    with open(temp_file_path, 'r', encoding='utf-8') as f:
        text_content = f.read()

    user_message_extraction = f"Extract information from the following web page content:\n\n{text_content[:8000]}..."

    completion = safe_chat_completion(
        [
            {"role": "system", "content": UNIVERSAL_SYSTEM_PROMPT},
            {"role": "user", "content": user_message_extraction},
        ],
        response_format=None
    )

    if not completion:
        return None, None

    llm_response_content = completion.choices[0].message.content or ""

    try:
        extracted_info_dict = json.loads(llm_response_content)
        return extracted_info_dict, text_content
    except json.JSONDecodeError:
        return llm_response_content.strip(), text_content


st.title("✨ DOBBY 🤖 : Smart Webpage Q/A")

if "service" not in st.session_state:
    try:
        chrome_driver_path = ChromeDriverManager().install()
        st.session_state.service = Service(chrome_driver_path)
    except Exception as e:
        st.error(f"Error installing Chrome Driver: {e}")
        st.stop()

for key in ["full_text", "extracted_info", "temp_file_path"]:
    if key not in st.session_state:
        st.session_state[key] = None

tab1, tab2 = st.tabs(["📄 Extraction", "💬 AI Q&A"])

with tab1:
    url = st.text_input("Enter the URL to extract data from", placeholder="https://example.com")
    if st.button("Extract Information"):
        if not url.startswith(('http://', 'https://')):
            st.error("Please enter a valid URL starting with http:// or https://")
        else:
            with st.spinner("Fetching and processing webpage..."):
                temp_file_path = get_text_from_url(url, st.session_state.service)
                if temp_file_path:
                    st.session_state.temp_file_path = temp_file_path
                    extracted_info, full_webpage_text = extract_info_with_gaia_agent(temp_file_path)
                    st.session_state.extracted_info = extracted_info
                    st.session_state.full_text = full_webpage_text
                else:
                    st.error("Failed to retrieve content from the URL.")

    if st.session_state.extracted_info:
        st.subheader("Extracted Content")
        with st.container():
            if isinstance(st.session_state.extracted_info, dict):
                st.markdown(f"<div class='extracted-box'>{json.dumps(st.session_state.extracted_info, indent=2)}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='extracted-box'>{st.session_state.extracted_info}</div>", unsafe_allow_html=True)

with tab2:
    if not st.session_state.full_text:
        st.info("Please extract content first in the 'Extraction' tab.")
    else:
        question = st.text_input("Ask a question about the webpage content", placeholder="Type your question here...")
        if st.button("Get Answer"):
            qa_system_prompt = "You are a highly intelligent AI assistant...  Answer in unfiltered and funny way also..."
            qa_text_context = st.session_state.full_text[:15000]
            qa_user_message = f"Based on the following content, please answer the question:\n\nContent:\n{qa_text_context}\n\nQuestion: {question}"

            with st.spinner("Thinking..."):
                completion = safe_chat_completion(
                    [
                        {"role": "system", "content": qa_system_prompt},
                        {"role": "user", "content": qa_user_message},
                    ]
                )

                if completion:
                    answer = completion.choices[0].message.content or ""
                    st.markdown(answer)
