

# THIS IS THE GUI VERSION.(CLI RECOMMENDED)

# FOR ERRORS PLEASE REFER TO ERRORS_FIX.txt

# MAKE SURE YOU USE A PUBLIC WEBSITE THAT DONT REQUIRE AUTHENTICATION.

# REMEMBER TO DELETE HISTORY WHEN USING NEW LINK

import customtkinter as ctk
import os
import json
import time
import threading
import logging
import validators
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from tkinter import messagebox, filedialog
from retry import retry
import tempfile
from datetime import datetime
from PIL import Image, ImageTk 



load_dotenv()
GAIA_DOMAIN_URL = os.getenv("GAIA_DOMAIN_URL")
OPENAI_API_KEY = os.getenv("GAIA_API_KEY")
MODEL_NAME = os.getenv("MODEL")
MAX_BYTES = 100 * 1024 * 1024
RETRIES = 3
TIMEOUT = 20
API_RETRIES = 3
APP_VERSION = "1.0.0"

OPENAI_CLIENT = OpenAI(base_url=f"{GAIA_DOMAIN_URL}/v1", api_key=OPENAI_API_KEY, timeout=90.0)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

UNIVERSAL_PROMPT = """
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

QA_SYSTEM_PROMPT = """
You are a highly intelligent, insightful, and adaptable AI assistant of *GAIANET*(made by gaia, by gaia, of gaia). Based on the provided webpage content, answer the user's question. If a direct answer isn't present, use your intelligence to infer, evaluate, or provide a reasoned assessment based on the information and implications of the text. This includes subjective qualities or potential 'ratings' if the content describes features that support such an assessment. Always ensure your response is logically derived from and consistent with the provided content. If an answer truly cannot be formed, state so professionally.
"""

def fetch_page_text(url: str, driver_service: Service, max_bytes: int = MAX_BYTES, retries: int = RETRIES, timeout: int = TIMEOUT) -> str | None:
    ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    opts = Options()
    for arg in ("--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--log-level=3"):
        opts.add_argument(arg)
    opts.add_argument(f"user-agent={ua}")

    for attempt in range(1, retries + 1):
        try:
            driver = webdriver.Chrome(service=driver_service, options=opts)
            driver.set_page_load_timeout(timeout)
            driver.get(url)
            WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            for tag in soup(["script", "style", "header", "footer", "nav", "aside", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator=' ', strip=True)
            text = " ".join(text.split())
            if len(text.encode('utf-8')) > max_bytes:
                text = text[:max_bytes]
            with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.txt') as f:
                f.write(text)
                return f.name
        except Exception as e:
            logger.error("Fetch attempt #%d failed: %s", attempt, e)
        finally:
            if driver:
                driver.quit()
    return None


@retry(OpenAIError, tries=API_RETRIES, delay=1, backoff=2)
def extract_structure(file_path: str) -> dict | None:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        logger.info("Sending %d characters to AI for JSON extraction", len(text[:15000]))
        resp = OPENAI_CLIENT.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": UNIVERSAL_PROMPT},
                {"role": "user", "content": f"{text[:15000]}"},
            ],
            response_format={"type": "json_object"}
        )
        data = json.loads(resp.choices[0].message.content)
        if not isinstance(data, dict) or "main_content_type" not in data:
            logger.error("Invalid JSON structure from AI: %s", data)
            return None
        logger.info("Successfully extracted JSON structure")
        return data
    except (OpenAIError, json.JSONDecodeError) as e:
        logger.error("Extraction error: %s", e)
        return None

@retry(OpenAIError, tries=API_RETRIES, delay=1, backoff=2)
def answer_question(context: str, question: str) -> str:
    try:
        prompt = f"{context[:15000]}\n\nQuestion: {question}"
        logger.info("Sending Q&A request with question: %s", question[:50])
        resp = OPENAI_CLIENT.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": QA_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        logger.info("Received Q&A response")
        return resp.choices[0].message.content.strip()
    except OpenAIError as e:
        logger.error("Q&A error: %s", e)
        return f"Error: Failed to get answer from AI - {str(e)}"
    

class GAIAApp(ctk.CTk):
    def __init__(self):
        super().__init__() 
        self.title("GAIA 🤖 Data Extractor")
        self.geometry("1000x800")
        self._history = []
        self._temp_files = []  
        self._lock = threading.Lock()
        self.page_text = ""
        self._last_action = "None"
        self._timer_running = False
        self._timer_thread = None
        self.setup_ui()
        self.extract_btn.configure(command=self.on_extract)
        self.clear_btn.configure(command=self.clear_fields)
        self.ask_btn.configure(command=self.on_ask)
        self.history_clear_btn.configure(command=self.clear_history)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)


    def setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        bg_image = Image.open("./gaia_background.jpg").resize((1920, 1080))
        self.bg_img = ctk.CTkImage(light_image=bg_image, dark_image=bg_image, size=(1920, 1080))
        bg_label = ctk.CTkLabel(self, image=self.bg_img, text="")
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        bg_label.lower()
        top_frame = ctk.CTkFrame(self, fg_color="#05020F")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        top_frame.grid_columnconfigure(0, weight=1)
        logo_image = Image.open("./Gaia_Logo_light.png").resize((150, 50))
        self.logo_img = ctk.CTkImage(light_image=logo_image, dark_image=logo_image, size=(150, 50))
        ctk.CTkLabel(top_frame, image=self.logo_img, text="").pack(side="left", padx=10)
        ctk.CTkLabel(top_frame, text="Data Extractor", font=ctk.CTkFont("Arial", 14), text_color="#cccccc").pack(side="left")
        self.tabview = ctk.CTkTabview(self, fg_color="#05020F", segmented_button_selected_color="#00b7eb")
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.tabview.add("Extract")
        self.tabview.add("Q&A")
        self.tabview.add("History")
        self.status_lbl = ctk.CTkLabel(self.tabview.tab("Extract"), text="", text_color="#cccccc")
        self.timer_lbl = ctk.CTkLabel(self.tabview.tab("Extract"), text="Elapsed: 0s (expected: 30sec)", text_color="#cccccc")
        self.progress_bar = ctk.CTkProgressBar(self.tabview.tab("Extract"), mode="indeterminate", width=300)
        self.q_status_lbl = ctk.CTkLabel(self.tabview.tab("Q&A"), text="", text_color="#cccccc")
        self.q_timer_lbl = ctk.CTkLabel(self.tabview.tab("Q&A"), text="Elapsed: 0s (expected: 30sec)", text_color="#cccccc")
        self.q_progress_bar = ctk.CTkProgressBar(self.tabview.tab("Q&A"), mode="indeterminate", width=300)
        self.build_extract_tab()
        self.build_qa_tab()
        self.build_history_tab()
        status_bar = ctk.CTkFrame(self, fg_color="#1c1f26")
        status_bar.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.status_bar_lbl = ctk.CTkLabel(
            status_bar,
            text=f"Version {APP_VERSION} | Last Action: {self._last_action}",
            font=ctk.CTkFont("Arial", 12),
            text_color="#cccccc"
        )
        self.status_bar_lbl.pack(side="left", padx=10)


    def build_extract_tab(self):
        frm = self.tabview.tab("Extract")
        frm.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frm, text="Enter a webpage URL to extract data:", font=ctk.CTkFont("Arial", 14), text_color="#cccccc")\
            .grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self.url_entry = ctk.CTkEntry(frm, width=700, placeholder_text="e.g., https://gaianet.ai",
                                      corner_radius=10, fg_color="#1c1f26", text_color="#ffffff")
        self.url_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        btn_frame = ctk.CTkFrame(frm, fg_color="#1c1f26")
        btn_frame.grid(row=2, column=0, pady=5)
        self.extract_btn = ctk.CTkButton(btn_frame, text="🔍 Start Extraction", fg_color="#00b7eb", hover_color="#0099cc")
        self.extract_btn.pack(side="left", padx=5)
        self.clear_btn = ctk.CTkButton(btn_frame, text="🧹 Clear", fg_color="#ff5555", hover_color="#cc4444")
        self.clear_btn.pack(side="left", padx=5)

        ctk.CTkLabel(frm, text="⚙️ Structured JSON Output:", font=ctk.CTkFont("Arial", 14), text_color="#cccccc")\
            .grid(row=3, column=0, sticky="w", padx=10, pady=(10, 0))

        self.json_box = ctk.CTkTextbox(frm, width=800, height=300, wrap="none",
                                       fg_color="#1c1f26", text_color="#00ffcc", scrollbar_button_color="#00b7eb")
        self.json_box.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")

        self.status_lbl.grid(row=5, column=0, pady=5, sticky="w")
        self.progress_bar.grid(row=6, column=0, pady=5, sticky="ew")
        self.timer_lbl.grid(row=7, column=0, pady=5, sticky="ew")
        self.progress_bar.grid_remove()  
        self.timer_lbl.grid_remove()    


    def build_qa_tab(self):
        frm = self.tabview.tab("Q&A")
        frm.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frm, text="Ask a question about the extracted content:", font=ctk.CTkFont("Arial", 14), text_color="#cccccc")\
            .grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self.q_entry = ctk.CTkEntry(frm, width=700, placeholder_text="e.g., What is the main topic?",
                                    corner_radius=10, fg_color="#1c1f26", text_color="#ffffff")
        self.q_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.ask_btn = ctk.CTkButton(frm, text="💬 Get Answer", fg_color="#00b7eb", hover_color="#0099cc")
        self.ask_btn.grid(row=2, column=0, pady=5)

        ctk.CTkLabel(frm, text="📥 Answer:", font=ctk.CTkFont("Arial", 14), text_color="#cccccc")\
            .grid(row=3, column=0, sticky="w", padx=10, pady=(10, 0))

        self.ans_box = ctk.CTkTextbox(frm, width=800, height=300, wrap="word",
                                      fg_color="#1c1f26", text_color="#d0ffd0", scrollbar_button_color="#00b7eb")
        self.ans_box.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")

        self.q_status_lbl.grid(row=5, column=0, pady=5, sticky="w")
        self.q_progress_bar.grid(row=6, column=0, pady=5, sticky="ew")
        self.q_timer_lbl.grid(row=7, column=0, pady=5, sticky="ew")
        self.q_progress_bar.grid_remove() 
        self.q_timer_lbl.grid_remove()    



    def build_history_tab(self):
        frm = self.tabview.tab("History")
        frm.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frm, text="Extraction History", font=ctk.CTkFont("Arial", 14), text_color="#cccccc")\
            .grid(row=0, column=0, sticky="w", padx=10, pady=(10, 0))

        self.history_box = ctk.CTkTextbox(frm, width=800, height=400, wrap="none",
                                          fg_color="#1c1f26", text_color="#ffffff", scrollbar_button_color="#00b7eb")
        self.history_box.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        self.history_clear_btn = ctk.CTkButton(frm, text="🗑️ Clear History", fg_color="#ff5555", hover_color="#cc4444")
        self.history_clear_btn.grid(row=2, column=0, pady=5)



    def update_history(self):
        self.history_box.delete("1.0", "end")
        if not self._history:
            self.history_box.insert("1.0", "No extraction history yet.")
            return
        for idx, (url, data) in enumerate(self._history, 1):
            self.history_box.insert("end", f"--- Extraction {idx} ---\nURL: {url}\nJSON:\n{json.dumps(data, indent=2)}\n\n")



    def clear_history(self):
        if not messagebox.askyesno("Confirm Clear", "Are you sure you want to clear the extraction history?"):
            return
        self._history.clear()
        self.update_history()
        self._last_action = "Cleared history"
        self.status_bar_lbl.configure(text=f"Version {APP_VERSION} | Last Action: {self._last_action}")


    def set_status(self, msg: str, tab: str = "Extract"):
        self._last_action = msg or "None"
        self.status_bar_lbl.configure(text=f"Version {APP_VERSION} | Last Action: {self._last_action}")
        if tab == "Extract":
            self.status_lbl.configure(text=msg)
            self.status_lbl.update()
        else:
            self.q_status_lbl.configure(text=msg)
            self.q_status_lbl.update()


    def start_timer(self, tab: str = "Extract"):
        self._timer_running = True
        start_time = time.time()
        def update_timer():
            while self._timer_running:
                elapsed = int(time.time() - start_time)
                if tab == "Extract":
                    self.timer_lbl.configure(text=f"Elapsed: {elapsed}s (expected: 30s)")
                    self.timer_lbl.update()
                else:
                    self.q_timer_lbl.configure(text=f"Elapsed: {elapsed}s (expected: 30s)")
                    self.q_timer_lbl.update()
                time.sleep(1)
        self._timer_thread = threading.Thread(target=update_timer, daemon=True)
        self._timer_thread.start()



    def stop_timer(self, tab: str = "Extract"):
        self._timer_running = False
        if self._timer_thread:
            self._timer_thread.join(timeout=1)
        if tab == "Extract":
            self.timer_lbl.configure(text="Elapsed: 0s")
            self.timer_lbl.grid_remove()
            self.progress_bar.grid_remove()
        else:
            self.q_timer_lbl.configure(text="Elapsed: 0s")
            self.q_timer_lbl.grid_remove()
            self.q_progress_bar.grid_remove()


    def cleanup_temp_files(self):
        for tmp in self._temp_files:
            if os.path.exists(tmp):
                os.remove(tmp)
                logger.info("Cleaned up temporary file: %s", tmp)
        self._temp_files.clear()


    def on_closing(self):
        self.cleanup_temp_files()
        self.destroy()


    def on_extract(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Invalid Input", "Please enter a URL.")
            return
        if not validators.url(url) or any(x in url.lower() for x in ["localhost", "file://"]):
            messagebox.showwarning("Invalid URL", "Enter a valid URL starting with http:// or https://.")
            return
        self.extract_btn.configure(state="disabled")
        self.clear_btn.configure(state="disabled")
        self.json_box.delete("1.0", "end")
        self.set_status("Installing chromedriver…")
        self.progress_bar.grid(row=6, column=0, pady=5, sticky="ew")
        self.progress_bar.start()
        self.timer_lbl.grid(row=7, column=0, pady=5, sticky="ew")
        self.start_timer()
        threading.Thread(target=self.do_extract, args=(url,), daemon=True).start()


    def do_extract(self, url):
        tmp = None
        try:
            svc = Service(ChromeDriverManager().install())
            self.set_status("Fetching page…")
            tmp = fetch_page_text(url, svc)
            if not tmp:
                raise RuntimeError("Failed to fetch page text after retries.")
            self.set_status("Extracting JSON…")
            self._temp_files.append(tmp)
            data = extract_structure(tmp)
            with self._lock:
                self.page_text = open(tmp, encoding="utf-8").read() if tmp else ""
            if data:
                self.json_box.insert("1.0", json.dumps(data, indent=2))
                self._history.append((url, data))
                self.update_history()
            else:
                self.json_box.insert("1.0", "Error: No data extracted")
                raise RuntimeError("No valid data extracted from AI")
            self._last_action = f"Extracted data from {url}"
        except Exception as e:
            self.json_box.insert("1.0", f"Error: {e}")
            logger.error("Extraction error for %s: %s", url, e)
            messagebox.showerror("Error", f"Failed to extract data: {str(e)}")
        finally:
            self.extract_btn.configure(state="normal")
            self.clear_btn.configure(state="normal")
            self.set_status("")
            self.stop_timer()

    def clear_fields(self):
        if not messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all fields?"):
            return
        self.url_entry.delete(0, "end")
        self.json_box.delete("1.0", "end")
        self.q_entry.delete(0, "end")
        self.ans_box.delete("1.0", "end")
        with self._lock:
            self.page_text = ""
        self._last_action = "Cleared fields"
        self.status_bar_lbl.configure(text=f"Version {APP_VERSION} | Last Action: {self._last_action}")
        self.set_status("")
        self.set_status("", tab="Q&A")

    def on_ask(self):
        q = self.q_entry.get().strip()
        if not q:
            messagebox.showwarning("Invalid Input", "Please enter a question.")
            return
        if not self.page_text:
            messagebox.showwarning("Missing Data", "Extract a webpage first.")
            return
        self.ask_btn.configure(state="disabled")
        self.ans_box.delete("1.0", "end")
        self.set_status("Querying AI…", tab="Q&A")
        self.q_progress_bar.grid(row=6, column=0, pady=5, sticky="ew")
        self.q_progress_bar.start()
        self.q_timer_lbl.grid(row=7, column=0, pady=5, sticky="ew")
        self.start_timer(tab="Q&A")
        threading.Thread(target=self.do_ask, args=(q,), daemon=True).start()

    def do_ask(self, question):
        try:
            ans = answer_question(self.page_text, question)
            self.ans_box.insert("1.0", ans)
            self._last_action = f"Answered question: {question[:30]}..."
        except Exception as e:
            self.ans_box.insert("1.0", f"Error: {e}")
            logger.error("Q&A error: %s", e)
            messagebox.showerror("Error", f"Failed to get answer: {str(e)}")
        finally:
            self.ask_btn.configure(state="normal")
            self.set_status("", tab="Q&A")
            self.stop_timer(tab="Q&A")
            self.status_bar_lbl.configure(text=f"Version {APP_VERSION} | Last Action: {self._last_action}")

if __name__ == "__main__":
    app = GAIAApp()
    app.mainloop()