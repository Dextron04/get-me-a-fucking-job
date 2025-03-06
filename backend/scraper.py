from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
import time
import undetected_chromedriver as uc
from concurrent.futures import ThreadPoolExecutor

brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

service = Service(executable_path="./chromedriver-mac-arm64/chromedriver")

# Configure options for Brave
options = uc.ChromeOptions()
options.binary_location = brave_path

# Create WebDriver instance
# driver = uc.Chrome(options=options)

# Define job boards and keywords
# These are the fuckers that I really wanna flip over with this
job_boards = [
    # "https://www.indeed.com/jobs?q={keyword}&l=",
    # "https://www.monster.com/jobs/search?q={keyword}&where=",
    # "https://www.glassdoor.com/Job/jobs.htm?sc.keyword={keyword}",
    "https://www.linkedin.com/jobs/search?keywords={keyword}&location=&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
]

keywords = ["software engineer", "software engineer intern", "software developer"]

all_jobs = []

# Thread-safe lock for shared data
from threading import Lock
lock = Lock()

# Function to scrape jobs for a given URL
def scrape_jobs(url):
    # Configure options for Brave
    options = uc.ChromeOptions()
    options.binary_location = brave_path
    driver = uc.Chrome(options=options)

    print(f"Scraping {url}...")
    driver.get(url)
    time.sleep(3)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Close pop-up if it appears
    time.sleep(5)  # Wait for the pop-up to appear
    try:
        # Use a more specific XPath based on the button's class and aria-label
        close_button = driver.find_element(By.XPATH, "//button[contains(@class, 'modal__dismiss') and @aria-label='Dismiss']")
        close_button.click()
        print("Closed LinkedIn pop-up using class and aria-label based XPath.")
        time.sleep(2)  # Wait for the pop-up to close
    except Exception as e:
        print(f"No pop-up found or error occurred: {e}")

    if "linkedin.com" in url:
        job_cards = driver.find_elements(By.CSS_SELECTOR, "div.base-card")
        for card in job_cards:
            try:
                card.click()
                time.sleep(2)  # Wait for the description to load

                # Extract details
                soup = BeautifulSoup(driver.page_source, "html.parser")
                title = card.find_element(By.CSS_SELECTOR, "h3.base-search-card__title").text.strip()
                link = card.find_element(By.CSS_SELECTOR, "a.base-card__full-link").get_attribute("href")
                company = card.find_element(By.CSS_SELECTOR, "h4.base-search-card__subtitle").text.strip() if card.find_element(By.CSS_SELECTOR, "h4.base-search-card__subtitle") else ""
                location = card.find_element(By.CSS_SELECTOR, "span.job-search-card__location").text.strip() if card.find_element(By.CSS_SELECTOR, "span.job-search-card__location") else ""
                description = soup.find("div", class_="show-more-less-html__markup").get_text(strip=True) if soup.find("div", class_="show-more-less-html__markup") else "Description not available"

                # Thread-safe access to all_jobs list
                with lock:
                    all_jobs.append({
                        "title": title,
                        "link": link,
                        "company": company,
                        "location": location,
                        "description": description,
                        "source": "LinkedIn"
                    })
            except Exception as e:
                print(f"Error extracting LinkedIn job: {e}")
                continue
    driver.quit()


def get_csv_file():
    # Create a list of URLs to scrape
    urls = [board.format(keyword=keyword) for board in job_boards for keyword in keywords]

    # Use ThreadPoolExecutor to manage concurrent threads
    with ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(scrape_jobs, urls)

    # Save jobs to CSV
    df = pd.DataFrame(all_jobs)
    df.to_csv("scraped_jobs.csv", index=False)
    print("Jobs saved to scraped_jobs.csv")

if __name__ == "__main__":
    get_csv_file()
