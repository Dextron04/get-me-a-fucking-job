from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re
import pandas as pd
import time
import random
import undetected_chromedriver as uc
from concurrent.futures import ThreadPoolExecutor
import os
import logging
from selenium.common.exceptions import WebDriverException
import subprocess
from selenium.webdriver.common.keys import Keys

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

# Optional: respect HEADLESS or DEBUG env vars
HEADLESS = os.getenv("HEADLESS", "false").lower() in ["1", "true", "yes"]
DEBUG_MODE = os.getenv("SCRAPER_DEBUG", "false").lower() in ["1", "true", "yes"]
# Scrolling / pagination tuning (env overridable)
MAX_SCROLL_ATTEMPTS = int(os.getenv("MAX_SCROLL_ATTEMPTS", "60"))  # per page
SCROLL_STAGNATION_LIMIT = int(os.getenv("SCROLL_STAGNATION_LIMIT", "4"))  # consecutive no-growth scrolls
SCROLL_MIN_DELAY = float(os.getenv("SCROLL_MIN_DELAY", "0.6"))
SCROLL_MAX_DELAY = float(os.getenv("SCROLL_MAX_DELAY", "1.4"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "50"))  # hard safety cap per keyword
# Concurrency defaults to number of keywords unless explicitly set
_kw_conc_env = os.getenv("KEYWORD_CONCURRENCY")
KEYWORD_CONCURRENCY = int(_kw_conc_env) if _kw_conc_env else 0  # 0 means auto = len(keywords)
FAST_WRITE = os.getenv("FAST_WRITE", "false").lower() in ("1", "true", "yes")  # write after each page

# service = Service(executable_path="./chromedriver-mac-arm64/chromedriver")  # Not needed with undetected_chromedriver

# Job boards & keywords
job_boards = [
    # We will append pagination params (&start=OFFSET or &pageNum=N) dynamically
    "https://www.linkedin.com/jobs/search?keywords={keyword}&location=&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
]

keywords = ["software engineer", "software engineer intern", "software developer"]

all_jobs = []

from threading import Lock
lock = Lock()

# Base paths
BASE_DIR = os.path.dirname(__file__)
OUTPUT_CSV = os.path.join(BASE_DIR, 'scraped_jobs.csv')
OUTPUT_TMP = os.path.join(BASE_DIR, 'scraped_jobs_partial.csv')


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
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-background-timer-throttling")
    opts.add_argument("--disable-client-side-phishing-detection")
    opts.add_argument("--disable-default-apps")
    opts.add_argument("--disable-features=Translate,SafeBrowsing")
    opts.add_argument("--disable-popup-blocking")
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
        selectors = [
            "button[aria-label='Dismiss']",
            "button[aria-label='Close']",
            "button.artdeco-modal__dismiss",
            "button[data-test-modal-close-btn]",
            "div[role='dialog'] button[aria-label='Dismiss']",
            "div[role='dialog'] button[aria-label='Close']"
        ]
        dismissed = False
        for sel in selectors:
            buttons = driver.find_elements(By.CSS_SELECTOR, sel)
            if buttons:
                try:
                    buttons[0].click()
                    time.sleep(0.3)
                    dismissed = True
                    break
                except Exception:
                    pass
        # Cookie consent / GDPR banners common selectors
        consent_selectors = [
            "button[data-control-name='accept']",
            "button.artdeco-global-alert-action__confirm-button",
            "button[aria-label='Accept cookies']",
            "button[data-test-global-alert-accept']"
        ]
        for sel in consent_selectors:
            try:
                btns = driver.find_elements(By.CSS_SELECTOR, sel)
                if btns:
                    btns[0].click()
                    time.sleep(0.2)
            except Exception:
                pass
        if not dismissed:
            try:
                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                time.sleep(0.2)
            except Exception:
                pass
        if driver.find_elements(By.CSS_SELECTOR, "div[role='dialog'], .artdeco-modal, .authentication-outlet"):
            driver.execute_script("document.querySelectorAll('[role=\\'dialog\\'], .artdeco-modal, .authentication-outlet, .overlay, .modal-overlay, .artdeco-modal-overlay').forEach(e=>e.remove());")
            time.sleep(0.2)
    except Exception:
        pass


def detect_browser_major():
    path = brave_path if os.path.exists(brave_path) else None
    try:
        if path:
            proc = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            out = proc.stdout.strip() or proc.stderr.strip()
            for token in out.split():
                if token and token[0].isdigit():
                    return int(token.split('.')[0])
    except Exception:
        pass
    return None

def _init_driver(url: str):
    """Initialize undetected Chrome driver with resilience."""
    options = build_options()
    browser_major = detect_browser_major()
    logging.info("Initializing browser for %s (detected major=%s)", url, browser_major)
    try:
        if browser_major:
            try:
                return uc.Chrome(options=options, version_main=browser_major)
            except WebDriverException as e:
                logging.warning("Version-pinned launch failed (%s). Retrying without pin...", e)
                return uc.Chrome(options=options)
        return uc.Chrome(options=options)
    except Exception as e:
        logging.error("Failed launching browser: %s", e)
        return None


def _scroll_to_load_all_jobs(driver):
    """Scroll the page incrementally to trigger dynamic job list loading."""
    stagnation = 0
    last_count = 0
    for attempt in range(1, MAX_SCROLL_ATTEMPTS + 1):
        close_linkedin_modal(driver)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(SCROLL_MIN_DELAY, SCROLL_MAX_DELAY))
        cards = driver.find_elements(By.CSS_SELECTOR, "div.base-card")
        count = len(cards)
        if count == last_count:
            stagnation += 1
        else:
            stagnation = 0
            last_count = count
        if attempt % 10 == 0:
            logging.info("Scroll attempt %d: loaded %d cards", attempt, count)
        if stagnation >= SCROLL_STAGNATION_LIMIT:
            break
    return driver.find_elements(By.CSS_SELECTOR, "div.base-card")


def _extract_cards(driver, page_url: str):
    """Extract job data from all currently loaded cards."""
    jobs_collected = 0
    job_cards = driver.find_elements(By.CSS_SELECTOR, "div.base-card")
    for idx, card in enumerate(job_cards):
        try:
            close_linkedin_modal(driver)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
            time.sleep(random.uniform(0.2, 0.55))
            try:
                card.click()
            except Exception:
                pass
            try:
                WebDriverWait(driver, 6).until(
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
                    "source": "LinkedIn",
                    "page_url": page_url
                })
            jobs_collected += 1
        except Exception as e:
            logging.debug("Error processing card %d: %s", idx, e)
            continue
    return jobs_collected


def scrape_jobs(base_url: str, keyword: str):
    """Paginate & scroll through LinkedIn job results for a keyword using a single browser instance."""
    driver = _init_driver(base_url)
    if not driver:
        return 0
    driver.set_page_load_timeout(60)
    seen_links = set()
    total_new = 0
    try:
        for page in range(MAX_PAGES):
            offset = page * 25
            if "start=" in base_url:
                page_url = re.sub(r"start=\d+", f"start={offset}", base_url)
            else:
                page_url = base_url
                page_url = re.sub(r"pageNum=\d+", f"pageNum={page}", page_url)
                if 'start=' not in page_url:
                    page_url = f"{page_url}&start={offset}"
            logging.info("[KW=%s] Page %d -> %s", keyword, page + 1, page_url)
            try:
                driver.get(page_url)
                logging.info("[KW=%s] Loaded URL current_url=%s", keyword, driver.current_url)
            except Exception as e:
                logging.error("Page load failed (%s): %s", page_url, e)
                break
            time.sleep(random.uniform(1.0, 2.0))
            close_linkedin_modal(driver)
            # Debug dump early if no cards yet and DEBUG_MODE
            if DEBUG_MODE:
                try:
                    with open(os.path.join(BASE_DIR, f'debug_{keyword}_page{page+1}.html'), 'w') as f:
                        f.write(driver.page_source)
                except Exception:
                    pass
            try:
                WebDriverWait(driver, 12).until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.base-card"))
                )
            except Exception:
                logging.info("No results on page %d for '%s' (stopping)", page + 1, keyword)
                break
            _scroll_to_load_all_jobs(driver)
            before_count = len(all_jobs)
            added = _extract_cards(driver, page_url)
            logging.info("[KW=%s] Extract attempt page %d: added_raw=%d total_all_jobs=%d", keyword, page + 1, added, len(all_jobs))
            if added:
                unique_buffer = []
                with lock:
                    for job in all_jobs:
                        link = job.get("link")
                        if link and link not in seen_links:
                            seen_links.add(link)
                            unique_buffer.append(job)
                with lock:
                    all_jobs.clear()
                    all_jobs.extend(unique_buffer)
            after_count = len(all_jobs)
            page_new = after_count - before_count
            total_new += max(0, page_new)
            logging.info("[KW=%s] Page %d: +%d (unique total %d)", keyword, page + 1, page_new, len(all_jobs))
            if page_new == 0:
                logging.info("Stagnated (no new jobs) on page %d for '%s' -> stop", page + 1, keyword)
                break
            # Incremental write for fast feedback
            if FAST_WRITE and page_new > 0:
                _safe_write_csv(partial=True)
    finally:
        if not DEBUG_MODE:
            try:
                driver.quit()
            except Exception:
                pass
        else:
            logging.info("DEBUG_MODE: browser left open for keyword '%s'", keyword)
    return total_new


def _safe_write_csv(partial: bool = False):
    """Thread-safe CSV write. If partial=True writes to temp file; else final output."""
    with lock:
        if not all_jobs:
            return
        df = pd.DataFrame(all_jobs)
        df.drop_duplicates(subset=["link"], inplace=True)
        target = OUTPUT_TMP if partial else OUTPUT_CSV
        df.to_csv(target, index=False)
        logging.info("Wrote %d jobs to %s", len(df), os.path.basename(target))


def get_csv_file():
    # Reset global list each run
    global all_jobs
    all_jobs = []

    # Auto concurrency determination
    effective_conc = KEYWORD_CONCURRENCY if KEYWORD_CONCURRENCY > 0 else len(keywords)
    logging.info("Starting scrape for %d keywords (concurrency=%d, max_pages=%d, fast_write=%s)",
                 len(keywords), effective_conc, MAX_PAGES, FAST_WRITE)

    def run_keyword(kw: str):
        total_for_kw = 0
        for board in job_boards:
            base = board.format(keyword=kw.replace(" ", "%20"))
            new_count = scrape_jobs(base, kw)
            total_for_kw += new_count
        logging.info("[KW=%s] Finished with %d new jobs (cumulative global=%d)", kw, total_for_kw, len(all_jobs))

    if effective_conc > 1:
        with ThreadPoolExecutor(max_workers=effective_conc) as executor:
            list(executor.map(run_keyword, keywords))
    else:
        for kw in keywords:
            run_keyword(kw)

    if not all_jobs:
        logging.warning("No jobs collected. LinkedIn may have blocked access or layout changed.")
    else:
        df = pd.DataFrame(all_jobs)
        before = len(df)
        df.drop_duplicates(subset=["link"], inplace=True)
        deduped = len(df)
        df.to_csv(OUTPUT_CSV, index=False)
        logging.info("Saved %d unique jobs (removed %d duplicates) to %s", deduped, before - deduped, OUTPUT_CSV)

    return all_jobs


if __name__ == "__main__":
    get_csv_file()
