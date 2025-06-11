# get-me-a-fucking-job

![Generated Image March 24, 2025 - 1_30AM png](https://github.com/user-attachments/assets/4659d23c-6f70-4eb2-8daf-dcb0fba7680e)

## Overview

**get-me-a-fucking-job** is an automated job search and resume analysis tool. It scrapes job postings from LinkedIn, analyzes your resume (PDF), extracts your skills using NLP, and matches you to the best job opportunities using both traditional ML and Google Gemini LLM for deep analysis. The project is designed for job seekers who want to maximize their chances of landing interviews by targeting the most relevant positions and understanding their fit.

## Features

- **Automated Job Scraping:** Uses Selenium and undetected-chromedriver to scrape jobs from LinkedIn based on predefined keywords.
- **Resume Parsing:** Extracts text and skills from your PDF resume using PyMuPDF and spaCy NLP.
- **Skill Matching:** Compares your skills to job descriptions using TF-IDF and cosine similarity.
- **LLM-Powered Analysis:** Uses Google Gemini (via API) to provide a deep, structured analysis of your fit for top jobs, including strengths, challenges, and recommendations.
- **Report Generation:** Outputs a detailed report of best-fit jobs and career insights.

## Directory Structure

```
.
├── backend/
│   ├── main.py           # Main analysis and matching logic
│   ├── scraper.py        # Job scraping logic
│   └── __pycache__/
├── chromedriver-mac-arm64/
│   ├── chromedriver      # ChromeDriver binary for Selenium
│   ├── LICENSE.chromedriver
│   └── THIRD_PARTY_NOTICES.chromedriver
├── templates/            # (Unused, placeholder for future frontend)
├── uploads/              # (Unused, placeholder for resume uploads)
├── analyze.py            # (Empty, placeholder)
└── README.md
```

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd get-me-a-fucking-job
```

### 2. Install Python dependencies

Create a `requirements.txt` with the following (or use your own virtual environment):

```txt
fitz
spacy
pandas
numpy
scikit-learn
python-dotenv
google-generativeai
selenium
undetected-chromedriver
bs4
```

Install dependencies:

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 3. ChromeDriver & Browser

- The project uses a pre-bundled ChromeDriver for Mac ARM64 (`chromedriver-mac-arm64/chromedriver`).
- It is configured to use Brave Browser by default. Update the `brave_path` in `backend/scraper.py` if you use a different browser or path.

### 4. Environment Variables

Create a `.env` file in the root directory with your Google Gemini API key:

```
GOOGLE_API_KEY=your_google_gemini_api_key
```

## Usage

### 1. Scrape Jobs

Run the scraper to fetch jobs and save them to `scraped_jobs.csv`:

```bash
cd backend
python scraper.py
```

### 2. Analyze Your Resume

Place your resume PDF in the project directory. Then run:

```bash
python main.py --resume your_resume.pdf
```

This will:

- Extract your skills
- Match you to jobs
- Run LLM analysis (if API key is set)
- Output a report of best-fit jobs and insights

## Customization

- **Keywords:** Edit the `keywords` list in `backend/scraper.py` to target different job titles.
- **Job Boards:** Add more job board URLs to the `job_boards` list in `backend/scraper.py`.
- **Skill Patterns:** Extend the `skill_patterns` in `main.py` for your domain.

## Dependencies

- Python 3.8+
- PyMuPDF (fitz)
- spaCy
- pandas, numpy, scikit-learn
- selenium, undetected-chromedriver, bs4
- google-generativeai
- python-dotenv

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

## License

See `chromedriver-mac-arm64/LICENSE.chromedriver` and `THIRD_PARTY_NOTICES.chromedriver` for ChromeDriver licensing. Project code is provided as-is for personal use.

## Disclaimer

This project is for educational and personal job search automation. Use responsibly and respect the terms of service of job boards.
