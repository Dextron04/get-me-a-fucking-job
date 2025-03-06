from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
import time

brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"

service = Service(executable_path="./chromedriver-mac-arm64/chromedriver")

# Configure options for Brave
options = webdriver.ChromeOptions()
options.binary_location = brave_path

# Create WebDriver instance
driver = webdriver.Chrome(service=service, options=options)

# Test by opening Google
driver.get("https://www.google.com")
print("Page Title:", driver.title)

driver.quit()
