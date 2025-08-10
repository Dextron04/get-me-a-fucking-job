from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import pandas as pd
import time
import undetected_chromedriver as uc
from concurrent.futures import ThreadPoolExecutor
import os
import logging
from selenium.common.exceptions import WebDriverException
import subprocess

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

# Optional: respect HEADLESS or DEBUG env vars
HEADLESS = os.getenv("HEADLESS", "false").lower() in ["1", "true", "yes"]
DEBUG_MODE = os.getenv("SCRAPER_DEBUG", "false").lower() in ["1", "true", "yes"]

# service = Service(executable_path="./chromedriver-mac-arm64/chromedriver")  # Not needed with undetected_chromedriver

# Job boards & keywords
job_boards = [
    "https://www.linkedin.com/jobs/search?keywords={keyword}&location=&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
]

keywords = ["software engineer", "software engineer intern", "software developer"]

all_jobs = []

from threading import Lock
lock = Lock()

BASE_DIR = os.path.dirname(__file__)
OUTPUT_CSV = os.path.join(BASE_DIR, 'scraped_jobs.csv')


def build_options():
    opts = uc.ChromeOptions()
    if os.path.exists(brave_path):
        opts.binary_location = brave_path
    else:
        logging.warning("Brave browser not found at %s. Falling back to system Chrome.", brave_path)
    if HEADLESS:
        # Brave headless flags (Chromium based)
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
    # General stability flags
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-infobars")
    opts.add_argument("--start-maximized")
    # Strong user agent to reduce blocking
    opts.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    return opts


def safe_get_text(driver, css_selector):
    try:
        el = driver.find_element(By.CSS_SELECTOR, css_selector)
        return el.text.strip()
    except Exception:
        return ""


def safe_get_attr(element, css_selector, attr):
    try:
        el = element.find_element(By.CSS_SELECTOR, css_selector)
        return el.get_attribute(attr)
    except Exception:
        return ""


def close_linkedin_modal(driver):
    try:
        # Wait briefly for any modal; LinkedIn sometimes uses artdeco-dismiss on button
        modal_close_selectors = [
            "button[aria-label='Dismiss']",
            "button[data-control-name='close']",
            "button.artdeco-modal__dismiss"
        ]
        for sel in modal_close_selectors:
            buttons = driver.find_elements(By.CSS_SELECTOR, sel)
            if buttons:
                buttons[0].click()
                logging.info("Closed pop-up (selector: %s)", sel)
                time.sleep(1)
                return
    except Exception as e:
        logging.debug("No modal closed: %s", e)


def detect_browser_major():
    path = brave_path if os.path.exists(brave_path) else None
    try:
        if path:
            proc = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            out = proc.stdout.strip() or proc.stderr.strip()
            # Expected like: 'Brave Browser 138.0.7204.168'
            for token in out.split():
                if token[0].isdigit():
                    major = int(token.split('.')[0])
                    return major
    except Exception as e:
        logging.debug("Browser version detect failed: %s", e)
    return None


def scrape_jobs(url):
    options = build_options()
    browser_major = detect_browser_major()
    logging.info("Initializing browser for %s (detected major=%s)", url, browser_major)
    try:
        if browser_major:
            try:
                driver = uc.Chrome(options=options, version_main=browser_major)
            except WebDriverException as e:
                logging.warning("Version-pinned launch failed (%s). Retrying without pin...", e)
                driver = uc.Chrome(options=options)
        else:
            driver = uc.Chrome(options=options)
    except WebDriverException as e:
        logging.error("Failed to start browser for %s: %s", url, e)
        return
    except Exception as e:
        logging.error("Unexpected error launching browser for %s: %s", url, e)
        return
    driver.set_page_load_timeout(60)
    logging.info(f"Scraping {url}")
    try:
        driver.get(url)
    except Exception as e:
        logging.error("Failed to load %s: %s", url, e)
        driver.quit()
        return

    # Allow dynamic content load
    time.sleep(2)
    close_linkedin_modal(driver)

    jobs_collected = 0

    try:
        wait = WebDriverWait(driver, 15)
        job_cards = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.base-card")))
    except Exception:
        logging.warning("No job cards found for %s (url now: %s)", url, driver.current_url)
        if DEBUG_MODE:
            debug_file = os.path.join(BASE_DIR, 'last_failed_page.html')
            with open(debug_file, 'w') as f:
                f.write(driver.page_source)
            logging.info("Saved debug HTML to %s", debug_file)
        driver.quit()
        return

    for idx, card in enumerate(job_cards):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            time.sleep(0.5)
            card.click()
            # Wait for description panel
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.show-more-less-html__markup"))
                )
            except Exception:
                pass
            page_html = driver.page_source
            soup = BeautifulSoup(page_html, "html.parser")

            title = safe_get_text(card, "h3.base-search-card__title")
            link = safe_get_attr(card, "a.base-card__full-link", "href")
            company = safe_get_text(card, "h4.base-search-card__subtitle")
            location = safe_get_text(card, "span.job-search-card__location")
            desc_div = soup.find("div", class_="show-more-less-html__markup")
            description = desc_div.get_text(" ", strip=True) if desc_div else "Description not available"

            if not title:
                continue

            with lock:
                all_jobs.append({
                    "title": title,
                    "link": link,
                    "company": company,
                    "location": location,
                    "description": description,
                    "source": "LinkedIn"
                })
            jobs_collected += 1
        except Exception as e:
            logging.debug("Error processing card %d: %s", idx, e)
            continue

    logging.info("Collected %d jobs from %s", jobs_collected, url)

    if not DEBUG_MODE:
        driver.quit()
    else:
        logging.info("DEBUG mode active: browser left open. Close it manually when done.")


def get_csv_file():
    # Reset global list each run
    global all_jobs
    all_jobs = []

    urls = [board.format(keyword=keyword.replace(" ", "%20")) for board in job_boards for keyword in keywords]
    logging.info("Starting scrape for %d URLs", len(urls))

    with ThreadPoolExecutor(max_workers=min(3, len(urls))) as executor:
        # Force iteration to surface exceptions raised in threads
        list(executor.map(scrape_jobs, urls))

    if not all_jobs:
        logging.warning("No jobs collected. LinkedIn may have blocked access or layout changed.")
    else:
        df = pd.DataFrame(all_jobs)
        df.drop_duplicates(subset=["link"], inplace=True)
        df.to_csv(OUTPUT_CSV, index=False)
        logging.info("Saved %d unique jobs to %s", len(df), OUTPUT_CSV)

    return all_jobs


if __name__ == "__main__":
    get_csv_file()
