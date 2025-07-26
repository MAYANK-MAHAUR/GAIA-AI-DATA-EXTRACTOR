import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from requests.exceptions import RequestException, Timeout, ConnectionError
import tempfile
import shutil

# --- NEW IMPORTS FOR SELENIUM ---
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException
# --- END NEW IMPORTS ---

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
GAIA_DOMAIN_URL = os.getenv("GAIA_DOMAIN_URL")
OPENAI_API_KEY_VAR = os.getenv("GAIA_API_KEY")

# Check if environment variables are actually loaded
if not GAIA_DOMAIN_URL:
    print("Error: GAIA_DOMAIN_URL environment variable is not set. Please set it in your .env file or shell.")
    exit(1)
if not OPENAI_API_KEY_VAR:
    print("Error: GAIA_API_KEY environment variable is not set. Please set it in your .env file or shell.")
    exit(1)

# Initialize OpenAI client to point to your Gaia Domain
client = OpenAI(
    base_url=f"{GAIA_DOMAIN_URL}/v1",
    api_key=OPENAI_API_KEY_VAR,
    timeout=90.0 # Increased timeout for potentially longer AI responses
)

# --- Universal System Prompt (Slightly adjusted for Q&A, but primarily for initial extraction) ---
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

# --- Function to Get Text from URL using Selenium ---
def get_text_from_url(url, max_bytes_to_read=10 * 1024 * 1024, retries=3, initial_timeout=20):
    """
    Fetches content from a URL using a headless browser (Selenium) to handle dynamic content,
    extracts readable text, and writes it to a temporary file.
    Returns the path to the temporary file, or None on failure.
    """
    temp_file_path = None
    driver = None # Initialize driver to None

    # Common headers for browser simulation
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # Create a temporary directory for the file
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, 'extracted_content.txt')

        # Configure Chrome options for headless mode and other settings
        chrome_options = Options()
        chrome_options.add_argument("--headless")  # Run Chrome in headless mode (without GUI)
        chrome_options.add_argument("--no-sandbox") # Required for some environments (e.g., Docker, Linux)
        chrome_options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
        chrome_options.add_argument("--window-size=1920,1080") # Set a consistent window size
        chrome_options.add_argument("--disable-gpu") # Often recommended for headless
        chrome_options.add_argument("--incognito") # Use incognito mode to prevent cookie/cache issues
        chrome_options.add_argument(f"user-agent={headers['User-Agent']}") # Set User-Agent
        chrome_options.add_argument("--log-level=3") # Suppress most console logs from Chrome itself

        # Optional: Specify path to chromedriver if it's not in your system's PATH
        # service = Service('C:/path/to/your/chromedriver.exe') # Uncomment and adjust this line if needed

        for attempt in range(retries):
            try:
                print(f"Attempt {attempt + 1}/{retries}: Fetching {url} with Selenium...")
                # Initialize WebDriver
                # If you uncommented 'service', pass it here: driver = webdriver.Chrome(service=service, options=chrome_options)
                driver = webdriver.Chrome(options=chrome_options) # Assumes chromedriver is in PATH

                driver.set_page_load_timeout(initial_timeout) # Set page load timeout for the initial GET request

                driver.get(url)

                # --- MODIFIED WebDriverWait Conditions ---
                # Wait for the presence of the <body> tag, which is a very basic indicator that
                # the HTML structure has loaded. For more complex dynamic sites, you might
                # still need to find a more specific element that indicates full content load.
                WebDriverWait(driver, initial_timeout * 2).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                print("Page content (body tag) found, proceeding to extract.")

                full_html_content = driver.page_source

                soup = BeautifulSoup(full_html_content, 'html.parser')

                # Existing cleaning logic, added 'noscript' tag
                for script_or_style in soup(['script', 'style', 'header', 'footer', 'nav', 'aside', 'noscript']):
                    script_or_style.decompose()

                text_content = soup.get_text(separator=' ', strip=True)
                text_content = ' '.join(text_content.split())

                # Limit text content size for temporary file if it's excessively large
                if len(text_content.encode('utf-8')) > max_bytes_to_read:
                    print(f"Warning: Extracted text content is large ({len(text_content.encode('utf-8')) / (1024*1024):.2f} MB), truncating for temp file.")
                    text_content = text_content[:max_bytes_to_read]

                # Write the cleaned text content to the temporary file
                with open(temp_file_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
                
                print(f"Extracted text written to temporary file: {temp_file_path}")
                return temp_file_path

            except TimeoutException:
                print(f"Attempt {attempt + 1}/{retries}: Page load or basic element (body) wait timed out for {url}. This might indicate a very slow site or a block.")
            except NoSuchElementException:
                print(f"Attempt {attempt + 1}/{retries}: Expected elements not found on the page for {url}. This should not happen for 'body' tag unless page is completely blank.")
            except WebDriverException as e:
                print(f"Attempt {attempt + 1}/{retries}: WebDriver error (e.g., Chrome not found, crash) for {url}: {e}")
                if "chrome not reachable" in str(e).lower():
                    print("Chrome browser not reachable. Ensure ChromeDriver is correctly installed and compatible with your Chrome version.")
                    break
            except Exception as e:
                print(f"An unexpected error occurred during fetching or parsing {url}: {e}")
                break
            finally:
                if driver:
                    driver.quit() # Ensure driver is closed after each attempt to prevent lingering processes

        print(f"Failed to fetch and process {url} after {retries} attempts.")
        return None

    finally:
        # The cleanup of the temporary directory is handled in the main block
        pass


# --- Function to Interact with Gaia AI Agent (Slightly modified to get full text to analyze) ---
def extract_info_with_gaia_agent(temp_file_path: str) -> tuple[dict, str]: # Now returns a tuple: (extracted_info_dict, full_text_content)
    """
    Reads text content from a temporary file and sends a slice to Gaia Domain's AI agent
    to extract structured information based on the universal prompt.
    Returns a tuple of (extracted_info_dict, full_text_content).
    """
    text_content = ""
    try:
        with open(temp_file_path, 'r', encoding='utf-8') as f:
            text_content = f.read() # Read the full content
    except FileNotFoundError:
        return {"error": f"Temporary file not found: {temp_file_path}"}, ""
    except Exception as e:
        return {"error": f"Error reading temporary file: {e}"}, ""

    if not text_content or len(text_content) < 50:
        return {"error": "Not enough meaningful text to analyze for AI extraction."}, text_content

    # Slice the text for the initial extraction prompt (LLM context window limit)
    user_message_extraction = f"Extract information from the following web page content:\n\n{text_content[:8000]}..."

    extracted_info_dict = {}
    try:
        chat_completion = client.chat.completions.create(
            model="Qwen2-0.5B-Instruct-Q5_K_M",
            messages=[
                {"role": "system", "content": UNIVERSAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_message_extraction},
            ],
            response_format={"type": "json_object"}
        )
        llm_response_content = chat_completion.choices[0].message.content
        extracted_info_dict = json.loads(llm_response_content)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from Gaia agent during extraction: {e}")
        print(f"LLM Raw Response: {llm_response_content}")
        extracted_info_dict = {"error": "Could not parse JSON response from AI agent. Check LLM output format."}
    except Exception as e:
        print(f"Error calling Gaia agent for initial extraction: {e}")
        extracted_info_dict = {"error": str(e)}
    
    return extracted_info_dict, text_content # Return both the extracted info and the full text

# --- Main execution block (MODIFIED for AI-Powered Q&A) ---
if __name__ == "__main__":
    print("--- Gaia Universal Smart Data Extractor ---")
    print(f"Connecting to Gaia Domain: {GAIA_DOMAIN_URL}")

    while True:
        user_url = input("\nEnter the URL to extract data from (or 'exit' to quit): ").strip()
        if user_url.lower() == 'exit':
            break
        if not user_url.startswith(('http://', 'https://')):
            print("Invalid URL. Please enter a URL starting with http:// or https://")
            continue

        temp_file_to_clean = None
        try:
            print(f"Attempting to fetch text from: {user_url}")
            temp_file_path = get_text_from_url(user_url)
            
            if temp_file_path:
                temp_file_to_clean = temp_file_path
                print("Text fetched and stored in temporary file. Sending to Gaia AI agent for universal extraction...")
                
                # Call the modified function which now returns both info and full text
                extracted_info, full_webpage_text = extract_info_with_gaia_agent(temp_file_path)
                
                print("\nExtracted Info:")
                print(json.dumps(extracted_info, indent=2))

                # --- AI-POWERED Q&A Functionality ---
                if extracted_info and "error" not in extracted_info and full_webpage_text:
                    print("\n--- AI-Powered Q&A about the webpage content (Type 'done' to finish Q&A) ---")
                    print("You can now ask ANY question based on the content of the page.")
                    
                    # Prepare the system message for Q&A context
                    qa_system_prompt = "You are a helpful assistant. Answer the user's question ONLY based on the provided webpage content. If the answer is not in the content, state that you cannot find it there."
                    
                    # Ensure the text slice for Q&A is within LLM limits (8000 chars)
                    # This is the actual text the AI will "read" for your questions.
                    qa_text_context = full_webpage_text[:8000] 

                    while True:
                        user_question = input("Your question: ").strip()
                        if user_question.lower() == 'done':
                            break

                        if not qa_text_context:
                            print("**AI Answer:** Error: No text content available for Q&A.")
                            break

                        # Construct the user message for the AI for Q&A
                        qa_user_message = f"Based on the following content, please answer the question:\n\nContent:\n{qa_text_context}\n\nQuestion: {user_question}"
                        
                        try:
                            qa_completion = client.chat.completions.create(
                                model="Qwen2-0.5B-Instruct-Q5_K_M", # Use the same model
                                messages=[
                                    {"role": "system", "content": qa_system_prompt},
                                    {"role": "user", "content": qa_user_message},
                                ],
                                # No response_format here, as we want free-form text answer
                            )
                            qa_answer = qa_completion.choices[0].message.content
                            print(f"**AI Answer:** {qa_answer}\n")
                        except Exception as e:
                            print(f"Error getting AI answer: {e}")
                            print("Please ensure your Gaia AI agent is running and accessible.")
                            break
                else:
                    print("Cannot start AI-Powered Q&A as there was an error in extraction or no valid text content was obtained.")
                # --- END OF AI-POWERED Q&A CODE ---

            else:
                print(f"Failed to get text from {user_url}.")

        finally:
            # Clean up the temporary directory and file
            if temp_file_to_clean and os.path.exists(os.path.dirname(temp_file_to_clean)):
                print(f"Cleaning up temporary directory: {os.path.dirname(temp_file_to_clean)}")
                shutil.rmtree(os.path.dirname(temp_file_to_clean))

    print("\n--- Script finished ---")