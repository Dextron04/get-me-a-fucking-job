from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
import time
import undetected_chromedriver as uc

brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

service = Service(executable_path="./chromedriver-mac-arm64/chromedriver")

# Configure options for Brave
options = uc.ChromeOptions()
options.binary_location = brave_path

# Create WebDriver instance
driver = uc.Chrome(options=options)

# Define job boards and keywords
# These are the fuckers that I really wanna flip over with this
job_boards = [
    # "https://www.indeed.com/jobs?q={keyword}&l=",
    # "https://www.monster.com/jobs/search?q={keyword}&where=",
    # "https://www.glassdoor.com/Job/jobs.htm?sc.keyword={keyword}",
    "https://www.linkedin.com/jobs/search?keywords={keyword}&location=&trk=public_jobs_jobs-search-bar_search-submit&position=1&pageNum=0"
]

keywords = ["software engineer", "software engineer intern", "software developer", "web developer", "web developer intern", "network engineer", "network engineer intern"]

all_jobs = []

for board in job_boards:
    for keyword in keywords:
        url = board.format(keyword=keyword)
        print(f"Scraping {url}...")
        driver.get(url)
        time.sleep(3)

        soup = BeautifulSoup(driver.page_source, "html.parser")

                # Extract jobs based on site structure
        if "indeed.com" in url:
            job_cards = soup.find_all("div", class_="job_seen_beacon")
            for card in job_cards:
                title = card.find("h2").get_text(strip=True)
                link = "https://www.indeed.com" + card.find("a")["href"]
                description = card.find("div", class_="job-snippet").get_text(strip=True) if card.find("div", class_="job-snippet") else ""
                all_jobs.append({"title": title, "link": link, "description": description, "source": "Indeed"})

        # elif "monster.com" in url:
        #     job_cards = soup.find_all("section", class_="card-content")
        #     for card in job_cards:
        #         title = card.find("h2").get_text(strip=True)
        #         link = card.find("a")["href"]
        #         description = card.find("div", class_="summary").get_text(strip=True) if card.find("div", class_="summary") else ""
        #         all_jobs.append({"title": title, "link": link, "description": description, "source": "Monster"})

        # elif "glassdoor.com" in url:
        #     job_cards = soup.find_all("li", class_="react-job-listing")
        #     for card in job_cards:
        #         title = card.find("a", class_="jobLink").get_text(strip=True)
        #         link = "https://www.glassdoor.com" + card.find("a", class_="jobLink")["href"]
        #         description = card.find("div", class_="jobDesc").get_text(strip=True) if card.find("div", class_="jobDesc") else ""
        #         all_jobs.append({"title": title, "link": link, "description": description, "source": "Glassdoor"})

        elif "linkedin.com" in url:
            job_cards = driver.find_elements(By.CSS_SELECTOR, "div.base-card")
            for card in job_cards:
                try:
                    # Click on each job card to load the description
                    card.click()
                    time.sleep(2)  # Wait for the description to load

                    # Extract details
                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    title = card.find_element(By.CSS_SELECTOR, "h3.base-search-card__title").text.strip()
                    link = card.find_element(By.CSS_SELECTOR, "a.base-card__full-link").get_attribute("href")
                    company = card.find_element(By.CSS_SELECTOR, "h4.base-search-card__subtitle").text.strip() if card.find_element(By.CSS_SELECTOR, "h4.base-search-card__subtitle") else ""
                    location = card.find_element(By.CSS_SELECTOR, "span.job-search-card__location").text.strip() if card.find_element(By.CSS_SELECTOR, "span.job-search-card__location") else ""
                    
                    # Extract full job description
                    description = soup.find("div", class_="show-more-less-html__markup").get_text(strip=True) if soup.find("div", class_="show-more-less-html__markup") else "Description not available"
                    
                    # Append to all_jobs list
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

# Save jobs to CSV
df = pd.DataFrame(all_jobs)
df.to_csv("scraped_jobs.csv", index=False)
print("Jobs saved to scraped_jobs.csv")
